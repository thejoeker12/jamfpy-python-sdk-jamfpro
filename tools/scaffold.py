"""Scaffold an endpoint from the API schemas: its class, its wiring in ``client.py``, its unit tests and a live spec.

``python -m tools.scaffold --api pro --path /v1/things [--name <ClassName>] [--root <repo>] [--dry-run]``;
``make scaffold API=<api> PATH=<path> [NAME=<ClassName>]`` wraps it. The schema is read through ``tools.schemas``, from
``<root>/api_schemas``. The path picks one of four shapes:

- Classic simple: ``<path>/id/{id}`` exists; a ``ClassicEndpoint`` subclass appended to ``clc_endpoints.py``.
- Classic composite: other id-style siblings (``/accounts/userid/{id}``); a ``clc_endpoints_<slug>.py`` module with a
  bare-``Endpoint`` parent and one child per sibling, as in ``clc_endpoints_accounts.py``.
- Pro CRUD: ``<path>/{id}`` exists; ``ProEndpoint``, or exactly the capability mixins the verbs back (``ProGetAll`` only
  when the collection GET is paginated).
- Pro action: no ``{id}`` sibling, POST (and at most GET); a bare ``Endpoint`` with one ``send`` method.

Anything else is refused with one line on stderr, and nothing is written. Every file is computed first and then written
together; a write that fails puts back the files already written. COVERAGE.md is left to ``make coverage-doc``.
"""
# One module on purpose: the generated code's templates live next to the rules that pick them, which outgrows
# pylint's 500-line default.
# pylint: disable=too-many-lines

import argparse
import ast
import keyword
import os
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tools.schemas import APIS, REF_KEY, Schema, SchemaError, load_classic, load_pro, operations, path, paths, resolve

REPO_ROOT = Path(__file__).resolve().parent.parent

CLIENT = Path("jamfpy/client/client.py")
API_MODULE = Path("jamfpy/client/api.py")
ENDPOINTS = Path("jamfpy/endpoints")
CLC_MODULE = ENDPOINTS / "clc_endpoints.py"
CLC_TEST = Path("tests/clc_endpoints_test.py")
CONTRACT_TEST = Path("tests/contract_test.py")
LIVE_TESTS = {"classic": Path("tests/integration/clc_resources_live_test.py"), "pro": Path("tests/integration/pro_resources_live_test.py")}
API_CLASSES = {"classic": "ClassicAPI", "pro": "ProAPI"}

# The Pro capability mixins in ProEndpoint's order, keyed by the (path, verb) that backs each.
PRO_MIXINS = (
    ("collection", "get", "ProGetAll", "get_all"),
    ("item", "get", "ProGetById", "get_by_id"),
    ("collection", "post", "ProCreate", "create"),
    ("item", "put", "ProUpdateById", "update_by_id"),
    ("item", "delete", "ProDeleteById", "delete_by_id"),
)
# What ClassicEndpoint and the composite children send, so a Classic path that lacks any of these is refused.
CLASSIC_ITEM_VERBS = ("delete", "get", "post", "put")
# The methods run_classic_lifecycle / run_pro_lifecycle call; a live spec is only added when the endpoint has them all.
LIFECYCLE_METHODS = ("create", "get_by_id", "update_by_id", "delete_by_id")
JSON_TYPES = ("application/json",)
XML_TYPES = ("application/xml", "text/xml")
FILL_IN = 'lambda n: pytest.fail("fill in the builders")'
# pylint's max-line-length in .pylintrc: a longer generated import is wrapped in parentheses.
MAX_LINE = 150

_PARAM = re.compile(r"\{([^}/]+)\}")
_PRO_PATH = re.compile(r"/v(\d+)(/.+)")
_PASCAL = re.compile(r"[A-Z][A-Za-z0-9]*")
# A capital that ends an acronym (MDMCommands) or follows a lower-case letter or digit starts a new word.
_WORD_BREAK = re.compile(r"(?<=[A-Za-z0-9])(?=[A-Z][a-z])|(?<=[a-z0-9])(?=[A-Z])")


class ScaffoldError(Exception):
    """The scaffolder refuses a path or cannot write. The message is one line, fit for the CLI."""


@dataclass(frozen=True)
class Child:
    """One sub-endpoint of a Classic composite, from one id-style sibling path."""

    attr: str
    class_name: str
    by_id_uri: str
    by_name_uri: str | None


@dataclass(frozen=True)
class Plan:
    """What the schema says to generate for one path; ``render`` turns it into file contents."""

    api: str
    path: str
    shape: str
    uri: str
    slug: str
    class_name: str
    attr: str
    name: str
    version: str | None = None
    mixins: tuple[str, ...] = ()
    methods: tuple[str, ...] = ()
    children: tuple[Child, ...] = ()
    unmapped: tuple[str, ...] = ()
    named: bool = False
    unpaginated: bool = False

    @property
    def endpoint_count(self) -> int:
        """How many endpoints the contract test discovers for this plan: the parent and each child."""
        return 1 + len(self.children)

    @property
    def has_lifecycle(self) -> bool:
        """Whether the live lifecycle runners can drive it (create, read, update, delete by id)."""
        if self.shape == "Classic composite":
            return True
        return all(method in self.methods for method in LIFECYCLE_METHODS)

    def summary(self) -> str:
        """One line naming the shape and what it is built from."""
        if self.shape == "Pro CRUD":
            base = "ProEndpoint" if len(self.mixins) == len(PRO_MIXINS) else ", ".join(self.mixins)
            detail = f"{self.class_name}({base}): {', '.join(self.methods)}"
        elif self.shape == "Classic composite":
            detail = f"{self.class_name}(Endpoint) with {', '.join(f'.{child.attr}' for child in self.children)}"
        elif self.shape == "Pro action":
            detail = f"{self.class_name}(Endpoint): send"
        else:
            detail = f"{self.class_name}(ClassicEndpoint)"
        unmapped = f"; no method for {', '.join(self.unmapped)}" if self.unmapped else ""
        return f"shape: {self.shape} -> {detail}{unmapped}"

    def next_steps(self) -> list[str]:
        """The ``next:`` lines for the CLI: what the agent still has to do or decide by hand."""
        if self.has_lifecycle:
            lines = [f"next: fill in the live builders in {LIVE_TESTS[self.api]}; review _name ({self.name!r}) and the docstrings"]
        else:
            lines = [f"next: no live spec (the lifecycle needs {', '.join(LIFECYCLE_METHODS)}); review _name ({self.name!r}) and the docstrings"]
        # The endpoints that get no spec: a composite's parent (only its children get one) and anything the lifecycle runners can't drive.
        if self.children or not self.has_lifecycle:
            who = f"{self.api}.{self.attr}" + (" (the parent; only its children get live specs)" if self.children else "")
            lines.append(
                f'next: make coverage-doc will refuse {who} until it has a reason: add "{self.attr}": "<why it has no live spec>" '
                f"to LIVE_NOT_COVERED in {LIVE_TESTS[self.api]}"
            )
        if self.unpaginated:
            lines.append(f"next: GET {self.path} is not paginated (an array or another shape), so there is no get_all; write one by hand if needed")
        if self.children:
            lines.append(
                "next: the children's get_all returns the whole collection; override it like clc_endpoints_accounts.py if the resource needs slicing"
            )
        # A Classic path is usually a run-together word and a Pro slug with no break may be one: the path alone cannot tell.
        if not self.named and (self.api == "classic" or "_" not in self.slug):
            lines.append(
                f"next: names come from the path alone (class {self.class_name}, attribute {self.attr}); for a multi-word resource "
                "use NAME=<PascalCaseName> instead (undo this run first if it wrote)"
            )
        return lines


# Classification


def load_schema(api: str, root: Path) -> Schema:
    """The schema of the repo at ``root`` (Pro with its supplement), through ``tools.schemas``."""
    folder = root / "api_schemas"
    return load_pro(folder) if api == "pro" else load_classic(folder)


def classify(api: str, key: str, schema: Schema, name: str | None = None) -> Plan:
    """The plan for ``key``, or ``ScaffoldError`` naming the rule that refuses it. Reads only the schema.

    ``name`` is a PascalCase class name that replaces the one derived from the path; the attribute, the Pro module and the
    Pro ``_name`` follow it in snake_case. A Classic ``_name`` stays path-derived, as it is Jamf's own key.
    """
    if api not in APIS:
        raise ScaffoldError(f"unknown API {api!r}: expected one of {', '.join(APIS)}")
    try:
        described = path(api, key, schema=schema)
    except SchemaError as exc:
        raise ScaffoldError(f"refused: {exc}") from exc
    known = dict(paths(api, schema=schema))
    version: str | None = None
    uri = key
    if api == "pro":
        match = _PRO_PATH.fullmatch(key)
        if match is None:
            raise ScaffoldError(f"refused: {key} has no /v<n> version prefix, so there is no _version to set")
        version, uri = match[1], match[2]
    _check_parameters(api, key, known)
    words = _words(uri.strip("/").split("/"))
    path_slug = "_".join(words)
    if name is None:
        class_name, slug = "".join(word.capitalize() for word in words), path_slug
    else:
        if not _PASCAL.fullmatch(name):
            raise ScaffoldError(f"refused: NAME={name} is not a PascalCase class name (a capital, then letters and digits)")
        class_name, slug = name, _WORD_BREAK.sub("_", name).lower()
    if not slug.isidentifier() or keyword.iskeyword(slug) or not class_name.isidentifier() or keyword.iskeyword(class_name):
        raise ScaffoldError(f"refused: cannot derive a Python name from {key if name is None else f'NAME={name}'} (got {slug!r})")
    common = {"api": api, "path": key, "uri": uri, "slug": slug, "class_name": class_name, "attr": slug, "named": name is not None}
    if api == "pro":
        return _classify_pro(described, known, schema, version or "", common)
    return _classify_classic(known, schema, common, path_slug)


def _check_parameters(api: str, key: str, known: Mapping[str, list[str]]) -> None:
    """The endpoint may have one path parameter, named ``id``, and only in its by-id sibling, never in ``key`` itself."""
    own = [(name, key) for name in _PARAM.findall(key)]
    bases = [key, key + "/id"] if api == "classic" else [key]
    siblings = [(name, item) for item in known for base in bases if (name := _direct_param(base, item)) is not None]
    if len(own) + min(len(siblings), 1) > 1:
        listed = ", ".join(f"{{{name}}}" for name, _ in own + siblings)
        raise ScaffoldError(f"refused: {key} has more than one path parameter ({listed})")
    for name, where in own + siblings:
        if name != "id":
            raise ScaffoldError(f"refused: path parameter {{{name}}} in {where} is not named id")
    if own:
        raise ScaffoldError(f"refused: {key} has a path parameter of its own; scaffold a collection path (an endpoint's _uri has none)")


def _direct_param(base: str, item: str) -> str | None:
    """The parameter name when ``item`` is ``base`` plus one ``{param}`` segment, else ``None``."""
    match = re.fullmatch(re.escape(base) + r"/\{([^}/]+)\}", item)
    return match[1] if match else None


def _words(segments: Sequence[str]) -> list[str]:
    words: list[str] = []
    for segment in segments:
        spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "-", segment)
        words += [word.lower() for word in re.split(r"[-_.]+", spaced) if word]
    return words


def _classify_pro(described: Schema, known: Mapping[str, list[str]], schema: Schema, version: str, common: dict[str, Any]) -> Plan:
    key = common["path"]
    item_key = f"{key}/{{id}}"
    collection = set(known[key])
    item = set(known.get(item_key, []))
    if item_key in known:
        chosen = [(mixin, method) for where, verb, mixin, method in PRO_MIXINS if verb in (collection if where == "collection" else item)]
        if not chosen:
            raise ScaffoldError(
                f"refused: no shape rule matches {key} ({_verbs(collection)}) and {item_key} ({_verbs(item)}): "
                "Pro CRUD needs GET or POST on the collection or GET, PUT or DELETE by id"
            )
        # get_all pages with page/page-size, so a collection GET that doesn't page cannot back it.
        unpaginated = any(method == "get_all" for _, method in chosen) and not _paginated(described, schema, key)
        if unpaginated:
            chosen = [(mixin, method) for mixin, method in chosen if method != "get_all"]
            if not chosen:
                raise ScaffoldError(
                    f"refused: no shape rule matches {key} ({_verbs(collection)}) and {item_key} ({_verbs(item)}): "
                    "the collection GET is not paginated, so there is no get_all, and no other verb backs a method"
                )
        methods = tuple(method for _, method in chosen)
        if "create" in methods:
            _check_bodies("pro", [(key, described)], {"post"})
        if "update_by_id" in methods:
            _check_bodies("pro", [(item_key, path("pro", item_key, schema=schema))], {"put"})
        unmapped = [f"{v.upper()} {key}" for v in sorted(collection - {"get", "post"})]
        unmapped += [f"{v.upper()} {item_key}" for v in sorted(item - {"get", "put", "delete"})]
        return Plan(
            shape="Pro CRUD", version=version, name=common["slug"], mixins=tuple(mixin for mixin, _ in chosen), methods=methods,
            unmapped=tuple(unmapped), unpaginated=unpaginated, **common,
        )
    if "post" in collection and collection <= {"get", "post"}:
        _check_bodies("pro", [(key, described)], {"post"})
        return Plan(shape="Pro action", version=version, name=common["slug"], methods=("send",), **common)
    raise ScaffoldError(
        f"refused: no shape rule matches {key} ({_verbs(collection)}) with no {{id}} sibling: "
        "the Pro action shape needs POST, and at most GET besides"
    )


def _paginated(described: Schema, schema: Schema, key: str) -> bool:
    """Whether the collection GET is paginated, so ``ProGetAll`` can back a ``get_all``.

    It is when it declares ``page`` and ``page-size`` query parameters, or its 200 response is an object with ``totalCount``
    and ``results`` properties. ``tools.schemas.path`` resolves the parameters but not the responses, so the response is
    resolved here with ``resolve``.
    """
    get = described["methods"].get("get", {})
    if {"page", "page-size"} <= {param.get("name") for param in get.get("parameters", []) if param.get("in") == "query"}:
        return True
    response = resolve(((operations(schema["paths"][key]).get("get") or {}).get("responses") or {}).get("200"), schema)
    content = response.get("content") if isinstance(response, dict) else None
    for media in content.values() if isinstance(content, dict) else []:
        body = media.get("schema") if isinstance(media, dict) else None
        properties = body.get("properties") if isinstance(body, dict) else None
        if isinstance(properties, dict) and {"totalCount", "results"} <= properties.keys():
            return True
    return False


def _classify_classic(known: Mapping[str, list[str]], schema: Schema, common: dict[str, Any], path_slug: str) -> Plan:
    key = common["path"]
    collection = set(known[key])
    # A NAME= override renames the class and attribute, not Jamf's key, which _name has to match.
    name = _classic_name(schema, key) or path_slug
    id_path = f"{key}/id/{{id}}"
    if id_path in known:
        _require_verbs(key, collection, id_path, set(known[id_path]), "Classic simple (ClassicEndpoint)")
        _check_bodies("classic", [(id_path, path("classic", id_path, schema=schema))], {"post", "put"})
        return Plan(shape="Classic simple", name=name, methods=("get_all", "get_by_id", "update_by_id", "create", "delete_by_id"), **common)
    id_style = sorted(item for item in known if (m := re.fullmatch(re.escape(key) + r"/([^/{}]+)/\{id\}", item)) and m[1] != "id")
    if not id_style:
        raise ScaffoldError(
            f"refused: no shape rule matches {key} ({_verbs(collection)}): Classic needs {id_path} (simple) "
            f"or id-style siblings such as {key}/<thing>id/{{id}} (composite)"
        )
    children: list[Child] = []
    for sibling in id_style:
        _require_verbs(key, collection, sibling, set(known[sibling]), "Classic composite")
        _check_bodies("classic", [(sibling, path("classic", sibling, schema=schema))], {"post", "put"})
        segment = sibling.rsplit("/", 2)[1]
        stem = segment[:-2] if segment.endswith("id") and len(segment) > 2 else segment
        words = _words([stem])
        by_name = next((item.rsplit("/", 1)[0] for item in known if re.fullmatch(re.escape(f"{key}/{stem}name") + r"/\{[^}/]+\}", item)), None)
        children.append(Child(
            attr="_".join(words) + "s",
            class_name=common["class_name"] + "".join(word.capitalize() for word in words) + "s",
            by_id_uri=sibling.rsplit("/", 1)[0],
            by_name_uri=by_name,
        ))
    if len({child.attr for child in children}) != len(children):
        raise ScaffoldError(f"refused: the id-style siblings of {key} give clashing child names")
    return Plan(shape="Classic composite", name=name, methods=("get_all",), children=tuple(children), **common)


def _require_verbs(key: str, collection: set[str], item_key: str, item: set[str], shape: str) -> None:
    if "get" not in collection or not set(CLASSIC_ITEM_VERBS) <= item:
        raise ScaffoldError(
            f"refused: no shape rule matches {key} ({_verbs(collection)}) and {item_key} ({_verbs(item)}): {shape} needs GET "
            f"on the collection and {' '.join(v.upper() for v in CLASSIC_ITEM_VERBS)} by id"
        )


def _verbs(verbs: set[str]) -> str:
    return " ".join(sorted(verb.upper() for verb in verbs)) or "no verbs"


def _check_bodies(api: str, described: Sequence[tuple[str, Schema]], verbs: set[str]) -> None:
    """Refuse a multipart or binary body, or one that is not JSON (Pro) / XML (Classic), on the verbs the endpoint sends."""
    wanted = JSON_TYPES if api == "pro" else XML_TYPES
    for key, item in described:
        for verb, operation in item["methods"].items():
            body = operation.get("requestBody")
            if verb not in verbs or body is None:
                continue
            types = [str(t).split(";", maxsplit=1)[0].strip().lower() for t in body["contentTypes"]]
            body_schema = body.get("schema", {})
            binary = isinstance(body_schema, dict) and body_schema.get("format") == "binary"
            odd = [t for t in types if t.startswith("multipart/") or t == "application/octet-stream"]
            if odd or binary:
                raise ScaffoldError(f"refused: {verb.upper()} {key} takes a multipart or binary body ({', '.join(odd or types)})")
            if not any(t in wanted for t in types):
                kind = "JSON" if api == "pro" else "XML"
                raise ScaffoldError(f"refused: {verb.upper()} {key} takes {', '.join(types) or 'no content type'}, not {kind}")


def _classic_name(schema: Schema, key: str) -> str | None:
    """Jamf's JSON top-level key, when the collection GET's 200 response names one (a single property or a definition)."""
    get = operations(schema["paths"][key]).get("get") or {}
    response = (get.get("responses") or {}).get("200") or {}
    found = resolve(response.get("schema"), schema) if isinstance(response, dict) else None
    if not isinstance(found, dict):
        return None
    properties = found.get("properties")
    if isinstance(properties, dict) and len(properties) == 1:
        return "_".join(_words([next(iter(properties))]))
    ref = found.get(REF_KEY)
    return "_".join(_words([ref.rsplit("/", 1)[-1]])) if isinstance(ref, str) else None


# Rendering


def render(plan: Plan, root: Path) -> dict[Path, str]:
    """Every file the plan writes or changes (relative path to its full new text), in the order they are generated.

    Refuses when the endpoint already exists: its attribute on the API, its class, a class already wrapping the same
    URI, its module, its test module, or its live spec.
    """
    _check_not_wrapped(plan, root)
    client = _read(root, CLIENT)
    attrs = _api_attributes(client, _read(root, API_MODULE), API_CLASSES[plan.api])
    if plan.attr in attrs:
        hint = "pass a different NAME=..." if plan.named else "pass NAME=... to scaffold a second version alongside it"
        raise ScaffoldError(f"refused: {plan.api}.{plan.attr} already exists ({API_CLASSES[plan.api]} has {plan.attr}); {hint}")
    changes: dict[Path, str] = {}
    if plan.shape == "Classic simple":
        module = CLC_MODULE
        test_module = CLC_TEST
        changes[module] = _insert_classic_class(_read(root, module), plan)
    else:
        prefix = "pro_" if plan.api == "pro" else "clc_endpoints_"
        module = ENDPOINTS / f"{prefix}{plan.slug}.py"
        test_module = Path("tests") / f"{prefix}{plan.slug}_test.py"
        for new in (module, test_module):
            if (root / new).exists():
                raise ScaffoldError(f"refused: {new} already exists")
        changes[module] = _module_text(plan)
    changes[CLIENT] = _wire(client, plan, module.stem)
    changes[test_module] = _classic_rows(_read(root, CLC_TEST), plan) if plan.shape == "Classic simple" else _test_text(plan, module.stem)
    if plan.has_lifecycle:
        changes[LIVE_TESTS[plan.api]] = _append_specs(_read(root, LIVE_TESTS[plan.api]), plan)
    changes[CONTRACT_TEST] = _bump_count(_read(root, CONTRACT_TEST), plan.endpoint_count)
    return changes


def _read(root: Path, relative: Path) -> str:
    """The text of ``relative`` under ``root``; a missing file fails with one line."""
    try:
        return (root / relative).read_text(encoding="utf-8")
    except OSError as exc:
        raise ScaffoldError(f"cannot read {relative} under {root}: {exc.strerror or exc}") from exc


def _check_not_wrapped(plan: Plan, root: Path) -> None:
    """Refuse a URI an existing endpoint class already wraps, under whatever attribute it is wired."""
    prefix = "pro_" if plan.api == "pro" else "clc_"
    for module in sorted((root / ENDPOINTS).glob(f"{prefix}*.py")):
        tree = ast.parse(module.read_text(encoding="utf-8"))
        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            consts = _class_constants(node)
            if node.name == plan.class_name and module.name == CLC_MODULE.name:
                raise ScaffoldError(f"refused: class {plan.class_name} already exists in {CLC_MODULE}")
            # An endpoint without its own _version (pro.mdm) names one per method, so it wraps every version.
            same_version = plan.api == "classic" or consts.get("_version", plan.version) == plan.version
            if consts.get("_uri") == plan.uri and same_version:
                raise ScaffoldError(f"refused: {plan.path} already exists: {node.name} in {module.relative_to(root)} wraps it")


def _class_constants(node: ast.ClassDef) -> dict[str, str]:
    found: dict[str, str] = {}
    for statement in node.body:
        if isinstance(statement, ast.Assign) and isinstance(statement.value, ast.Constant) and isinstance(statement.value.value, str):
            found.update({target.id: statement.value.value for target in statement.targets if isinstance(target, ast.Name)})
    return found


def _api_attributes(client: str, api: str, class_name: str) -> set[str]:
    """Every name an API instance already has: the subclass's and the API base's methods and ``self.<name>`` attributes."""
    names: set[str] = set()
    for source, wanted in ((client, class_name), (api, "API")):
        classes = [node for node in ast.parse(source).body if isinstance(node, ast.ClassDef) and node.name == wanted]
        for inner in (node for found in classes for node in ast.walk(found)):
            if isinstance(inner, (ast.FunctionDef, ast.AsyncFunctionDef)):
                names.add(inner.name)
            elif (isinstance(inner, ast.Attribute) and isinstance(inner.ctx, ast.Store)
                  and isinstance(inner.value, ast.Name) and inner.value.id == "self"):
                names.add(inner.attr)
    return names


def _insert_lines(text: str, insertions: Sequence[tuple[int, Sequence[str]]]) -> str:
    """``text`` with each block of lines inserted before 0-based line ``index``; later indices first, so earlier stay valid."""
    lines = text.splitlines(keepends=True)
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"
    for index, block in sorted(insertions, key=lambda pair: pair[0], reverse=True):
        lines[index:index] = [line + "\n" for line in block]
    return "".join(lines)


def _list_assignment(text: str, name: str, file: Path) -> ast.Assign:
    for node in ast.parse(text).body:
        if (isinstance(node, ast.Assign) and isinstance(node.value, ast.List)
                and any(isinstance(target, ast.Name) and target.id == name for target in node.targets)):
            return node
    raise ScaffoldError(f"cannot find a top-level {name} = [...] list in {file}")


def _append_to_list(text: str, name: str, block: Sequence[str], file: Path) -> str:
    """``block`` added as the last element(s) of the top-level list ``name``, before its closing bracket line."""
    node = _list_assignment(text, name, file)
    closing = (node.end_lineno or node.lineno) - 1
    lines = text.splitlines()
    previous = closing - 1
    while previous > node.lineno - 1 and not lines[previous].strip():
        previous -= 1
    if previous > node.lineno - 1 and not lines[previous].rstrip().endswith((",", "[")):
        lines[previous] = lines[previous].rstrip() + ","
        text = "\n".join(lines) + "\n"
    return _insert_lines(text, [(closing, block)])


def _insert_classic_class(text: str, plan: Plan) -> str:
    """The class block in ``clc_endpoints.py`` before the first class whose name sorts after it, or at the end."""
    block = [
        f"class {plan.class_name}(ClassicEndpoint):",
        f'    """Endpoint for managing {" ".join(plan.slug.split("_"))} in Jamf Pro."""',
        f'    _uri = "{plan.uri}"',
        f'    _name = "{plan.name}"',
    ]
    after = [node for node in ast.parse(text).body if isinstance(node, ast.ClassDef) and node.name > plan.class_name]
    if after:
        return _insert_lines(text, [(after[0].lineno - 1, [*block, "", ""])])
    return text.rstrip("\n") + "\n\n\n" + "\n".join(block) + "\n"


def _wire(text: str, plan: Plan, module: str) -> str:
    """``client.py`` with the endpoint imported and attached at the end of its API's ``__init__``."""
    if plan.shape == "Classic simple":
        text, import_at = _classic_import(text, plan)
    else:
        import_at = _module_import(ast.parse(text), plan, module)
    class_name = API_CLASSES[plan.api]
    api_class = next((n for n in ast.parse(text).body if isinstance(n, ast.ClassDef) and n.name == class_name), None)
    init = next((n for n in api_class.body if isinstance(n, ast.FunctionDef) and n.name == "__init__"), None) if api_class else None
    if init is None:
        raise ScaffoldError(f"cannot find {class_name}.__init__ in {CLIENT}")
    last = init.body[-1]
    local = f"Pro{plan.class_name}" if plan.api == "pro" else plan.class_name
    attach = (last.end_lineno or last.lineno, [f"{' ' * last.col_offset}self.{plan.attr} = {local}(self)"])
    return _insert_lines(text, [attach, import_at])


def _module_import(tree: ast.Module, plan: Plan, module: str) -> tuple[int, list[str]]:
    """Where a Pro or composite module's import line goes: after the last import of its kind."""
    imports = [n for n in tree.body if isinstance(n, ast.ImportFrom) and n.level == 2 and (n.module or "").startswith("endpoints.")]
    if plan.api == "pro":
        lines = _import_lines(f"..endpoints.{module}", f"{plan.class_name} as Pro{plan.class_name}")
        anchors = [n for n in imports if (n.module or "").startswith("endpoints.pro_")] or imports
        if not anchors:
            raise ScaffoldError(f"cannot find the endpoint imports in {CLIENT}")
        return (anchors[-1].end_lineno or anchors[-1].lineno, lines)
    lines = _import_lines(f"..endpoints.{module}", plan.class_name)
    composites = [n for n in imports if (n.module or "").startswith("endpoints.clc_endpoints_")]
    if composites:
        return (composites[-1].end_lineno or composites[-1].lineno, lines)
    block = _clc_import_block(tree)
    return (block.end_lineno or block.lineno, ["", *lines])


def _import_lines(module: str, name: str) -> list[str]:
    """``from <module> import <name>``, wrapped in parentheses when it would pass ``MAX_LINE``."""
    line = f"from {module} import {name}"
    return [line] if len(line) <= MAX_LINE else [f"from {module} import (", f"    {name},", ")"]


def _and_list(items: Sequence[str], word: str = "and") -> str:
    """``a``, ``a and b``, ``a, b and c``."""
    return items[0] if len(items) == 1 else f"{', '.join(items[:-1])} {word} {items[-1]}"


def _tuple(items: Sequence[str]) -> str:
    """A tuple literal of string items."""
    quoted = [f'"{item}"' for item in items]
    return f"({quoted[0]},)" if len(quoted) == 1 else f"({', '.join(quoted)})"


def _clc_import_block(tree: ast.Module) -> ast.ImportFrom:
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.level == 2 and node.module == "endpoints.clc_endpoints":
            if node.end_lineno is not None and node.end_lineno > node.lineno:
                return node
    raise ScaffoldError(f"cannot find the parenthesised 'from ..endpoints.clc_endpoints import (...)' block in {CLIENT}")


def _classic_import(text: str, plan: Plan) -> tuple[str, tuple[int, list[str]]]:
    """The class's line in the ``clc_endpoints`` import block (one name per line), before the first name sorting after it.

    Returns the text too: appended last, the previous last name may need the trailing comma it lacked.
    """
    block = _clc_import_block(ast.parse(text))
    lines = text.splitlines()
    first, closing = block.lineno, (block.end_lineno or block.lineno) - 1
    for index in range(first, closing):
        if lines[index].strip().rstrip(",") > plan.class_name:
            return text, (index, [_indent(lines[index]) + f"{plan.class_name},"])
    if not lines[closing - 1].rstrip().endswith(","):
        lines[closing - 1] = lines[closing - 1].rstrip() + ","
        text = "\n".join(lines) + "\n"
    return text, (closing, [_indent(lines[closing - 1]) + f"{plan.class_name},"])


def _indent(line: str) -> str:
    return line[: len(line) - len(line.lstrip())]


def _module_text(plan: Plan) -> str:
    if plan.shape == "Pro CRUD":
        return _pro_crud_module(plan)
    if plan.shape == "Pro action":
        return _pro_action_module(plan)
    return _composite_module(plan)


def _words_of(plan: Plan) -> str:
    return " ".join(plan.slug.split("_"))


def _pro_crud_module(plan: Plan) -> str:
    full = len(plan.mixins) == len(PRO_MIXINS)
    bases = "ProEndpoint" if full else ", ".join(plan.mixins)
    imports = "ProEndpoint" if full else ", ".join(sorted(plan.mixins))
    # Without the pagination signal the collection GET has the verb but not the paging get_all needs.
    missing = [method for _, _, _, method in PRO_MIXINS if method not in plan.methods and not (plan.unpaginated and method == "get_all")]
    sentences = []
    if missing:
        sentences.append(f"Composes only the verbs the schema has, so there is no {_and_list([f'``{method}``' for method in missing], 'or')}.")
    if plan.unpaginated:
        sentences.append("The collection GET is not paginated, so ``get_all`` is not composed; write it by hand if it is needed.")
    doc = f'    """Endpoint for managing {_words_of(plan)} in the modern Jamf Pro API."""'
    if sentences:
        body = "\n".join(f"    {sentence}" for sentence in sentences)
        doc = f'    """Endpoint for managing {_words_of(plan)} in the modern Jamf Pro API.\n\n{body}\n    """'
    return (
        f'"""Endpoint module for managing Jamf Pro {_words_of(plan)}."""\n\n'
        f"from .models import {imports}\n\n\n"
        f"class {plan.class_name}({bases}):\n"
        f"{doc}\n"
        f'    _uri = "{plan.uri}"\n'
        f'    _name = "{plan.name}"\n'
        f'    _version = "{plan.version}"\n'
    )


def _pro_action_module(plan: Plan) -> str:
    return (
        f'"""Endpoint module for the Jamf Pro {_words_of(plan)} action."""\n'
        "from typing import Any\n\n"
        "from requests import Request, Response\n\n"
        "from .models import Endpoint\n\n\n"
        f"class {plan.class_name}(Endpoint):\n"
        f'    """Action endpoint for {_words_of(plan)} in the modern Jamf Pro API.\n\n'
        "    Verbs, not CRUD, so it subclasses the bare ``Endpoint`` and inherits no CRUD methods.\n"
        '    """\n'
        f'    _uri = "{plan.uri}"\n'
        f'    _name = "{plan.name}"\n'
        f'    _version = "{plan.version}"\n\n'
        "    def send(self, payload: dict[str, Any]) -> Response:\n"
        '        """POST a JSON payload to the action."""\n'
        "        return self._api.do(\n"
        "            Request(\n"
        '                "POST",\n'
        "                url=self._api.url(self._version) + self._uri,\n"
        '                headers=self._api.header("create-update")["json"],\n'
        "                json=payload,\n"
        "            )\n"
        "        )\n"
    )


def _composite_module(plan: Plan) -> str:
    base = f"{plan.class_name}Child"
    words = _words_of(plan)
    children = "\n\n".join(
        f"class {child.class_name}({base}):\n"
        f'    """Endpoint for managing the {" ".join(child.attr.split("_"))} under {words} in Jamf Pro.\n\n'
        "    ``get_all`` is the inherited one and returns the whole collection, not only these records; override it, as\n"
        '    ``AccountUsers`` does, if the resource needs slicing.\n    """\n'
        f'    _uri = "{plan.uri}"\n'
        f'    _name = "{child.attr}"\n'
        f'    _by_id_uri = "{child.by_id_uri}"\n'
        + (f'    _by_name_uri = "{child.by_name_uri}"\n' if child.by_name_uri else "")
        for child in plan.children
    )
    wiring = "".join(f"        self.{child.attr} = {child.class_name}(api)\n" for child in plan.children)
    exposed = _and_list([f"``.{child.attr}``" for child in plan.children])
    return (
        f'"""Endpoint module for the Jamf Pro Classic {words} composite endpoint."""\n'
        "from typing import TYPE_CHECKING\n\n"
        "from requests import Request, Response\n\n"
        "from .models import ClassicEndpoint, Endpoint\n\n"
        "if TYPE_CHECKING:\n"
        "    from ..client.api import API\n\n\n"
        f"class {base}(ClassicEndpoint):\n"
        f'    """Shared CRUD for the {words} sub-resources, whose ids sit under their own URIs rather than ``/id/``."""\n\n'
        "    _by_id_uri: str\n"
        "    _by_name_uri: str | None = None\n\n"
        "    def get_by_id(self, target_id: int, xml_response: bool = False) -> Response:\n"
        '        """Get a single record by ID."""\n'
        '        read_header = "json" if not xml_response else "xml"\n'
        "        return self._api.do(\n"
        "            Request(\n"
        '                method="GET",\n'
        '                url=self._api.url() + f"{self._by_id_uri}/{target_id}",\n'
        '                headers=self._api.header("read")[read_header],\n'
        "            )\n"
        "        )\n\n"
        "    def update_by_id(self, target_id: int, updated_configuration: str) -> Response:\n"
        '        """Update a record by ID with new configuration."""\n'
        "        return self._api.do(\n"
        "            Request(\n"
        '                method="PUT",\n'
        '                url=self._api.url() + f"{self._by_id_uri}/{target_id}",\n'
        '                headers=self._api.header("create-update")["xml"],\n'
        "                data=updated_configuration,\n"
        "            )\n"
        "        )\n\n"
        "    def create(self, config_profile: str) -> Response:\n"
        '        """Create a new record."""\n'
        "        return self._api.do(\n"
        "            Request(\n"
        '                method="POST",\n'
        '                url=self._api.url() + f"{self._by_id_uri}/0",\n'
        '                headers=self._api.header("create-update")["xml"],\n'
        "                data=config_profile,\n"
        "            )\n"
        "        )\n\n"
        "    def delete_by_id(self, target_id: int) -> Response:\n"
        '        """Delete a record by ID."""\n'
        "        return self._api.do(\n"
        "            Request(\n"
        '                method="DELETE",\n'
        '                url=self._api.url() + f"{self._by_id_uri}/{target_id}",\n'
        "            )\n"
        "        )\n\n\n"
        f"{children}\n\n"
        f"class {plan.class_name}(Endpoint):\n"
        f'    """Composite endpoint for {words} in Jamf Pro, exposing {exposed}."""\n'
        f'    _uri = "{plan.uri}"\n'
        f'    _name = "{plan.name}"\n\n'
        '    def __init__(self, api: "API") -> None:\n'
        '        """Wire the sub-endpoints onto the shared API client."""\n'
        "        super().__init__(api)\n"
        f"{wiring}\n"
        "    def get_all(self) -> Response:\n"
        f'        """Get the whole {plan.uri} payload, every sub-resource included."""\n'
        "        return ClassicEndpoint(self._api).get_all(self._uri)\n"
    )


def _classic_rows(text: str, plan: Plan) -> str:
    """``clc_endpoints_test.py`` with the endpoint in ``CLASSIC_ENDPOINTS`` (class order) and ``EXPECTED_ATTRS`` (last)."""
    node = _list_assignment(text, "CLASSIC_ENDPOINTS", CLC_TEST)
    row = f'    (clc.{plan.class_name}, "{plan.uri}", "{plan.name}"),'
    for element in node.value.elts if isinstance(node.value, ast.List) else []:
        first = element.elts[0] if isinstance(element, ast.Tuple) and element.elts else None
        if isinstance(first, ast.Attribute) and first.attr == plan.class_name:
            raise ScaffoldError(f"refused: {plan.class_name} is already in CLASSIC_ENDPOINTS in {CLC_TEST}")
        if isinstance(first, ast.Attribute) and first.attr > plan.class_name:
            text = _insert_lines(text, [(element.lineno - 1, [row])])
            break
    else:
        text = _append_to_list(text, "CLASSIC_ENDPOINTS", [row], CLC_TEST)
    return _append_to_list(text, "EXPECTED_ATTRS", [f'    "{plan.attr}",'], CLC_TEST)


def _test_text(plan: Plan, module: str) -> str:
    if plan.shape == "Pro CRUD":
        return _pro_crud_test(plan, module)
    if plan.shape == "Pro action":
        return _pro_action_test(plan)
    return _composite_test(plan)


_HEADER = '# pylint: disable=missing-function-docstring\n'


def _request_asserts(method: str, url: str, headers: str) -> str:
    return (
        "    req = mocked_responses.calls[-1].request\n"
        f'    assert req.method == "{method}"\n'
        f"    assert req.url == {url}\n"
        f"    assert sent_headers(req) == with_bearer({headers})\n"
    )


def _pro_crud_test(plan: Plan, module: str) -> str:
    writes = any(method in plan.methods for method in ("create", "update_by_id"))
    accessor = f"pro_api.{plan.attr}"
    item = f'f"{{BASE}}{plan.uri}/7"'
    tests: list[str] = []
    if "get_all" in plan.methods:
        tests.append(
            "def test_get_all_reads_page_zero(pro_api, mocked_responses):\n"
            f'    url = f"{{BASE}}{plan.uri}?page=0&page-size=100"\n'
            '    mocked_responses.get(url, json={"totalCount": 1, "results": [{"id": "7"}]})\n'
            f"    resp = {accessor}.get_all()\n"
            + _request_asserts("GET", "url", 'H["crud"]["read"]["json"]')
            + '    assert resp.json() == {"totalCount": 1, "results": [{"id": "7"}]}\n'
        )
    if "get_by_id" in plan.methods:
        tests.append(
            "def test_get_by_id_builds_the_id_url(pro_api, mocked_responses):\n"
            f'    mocked_responses.get({item}, json={{"id": "7"}})\n'
            f"    {accessor}.get_by_id(7)\n"
            + _request_asserts("GET", item, 'H["crud"]["read"]["json"]')
        )
    if "create" in plan.methods:
        tests.append(
            "def test_create_posts_json_payload(pro_api, mocked_responses):\n"
            f'    mocked_responses.post(f"{{BASE}}{plan.uri}", status=201, json={{"id": "7"}})\n'
            f"    {accessor}.create(PAYLOAD)\n"
            + _request_asserts("POST", f'f"{{BASE}}{plan.uri}"', 'H["crud"]["create-update"]["json"]')
            + "    assert json.loads(req.body) == PAYLOAD\n"
        )
    if "update_by_id" in plan.methods:
        tests.append(
            "def test_update_by_id_puts_json_payload(pro_api, mocked_responses):\n"
            f'    mocked_responses.put({item}, json={{"id": "7"}})\n'
            f"    {accessor}.update_by_id(7, PAYLOAD)\n"
            + _request_asserts("PUT", item, 'H["crud"]["create-update"]["json"]')
            + "    assert json.loads(req.body) == PAYLOAD\n"
        )
    if "delete_by_id" in plan.methods:
        tests.append(
            "def test_delete_by_id_uses_delete_header(pro_api, mocked_responses):\n"
            f"    mocked_responses.delete({item}, status=204)\n"
            f"    {accessor}.delete_by_id(7)\n"
            + _request_asserts("DELETE", item, 'H["crud"]["delete"]["json"]')
        )
    missing = [method for _, _, _, method in PRO_MIXINS if method not in plan.methods]
    check = (
        "def test_has_only_the_methods_the_schema_backs():\n"
        f"    for method in {_tuple(plan.methods)}:\n"
        f"        assert hasattr({plan.class_name}, method)\n"
    )
    if missing:
        check += f"    for method in {_tuple(missing)}:\n        assert not hasattr({plan.class_name}, method)\n"
    tests.append(check)
    tests.append(f'def test_name_returns_the_name_key(pro_api):\n    assert {accessor}.name() == "{plan.name}"\n')
    head = (
        f'"""Unit tests for the Pro {plan.class_name} endpoint."""\n{_HEADER}'
        + ("import json\n\n" if writes else "")
        + "from conftest import FQDN, sent_headers, with_bearer\n\n"
        "from jamfpy.client.constants import DEFAULT_HTTP_CONFIG_HEADERS as H\n"
        + "\n".join(_import_lines(f"jamfpy.endpoints.{module}", plan.class_name)) + "\n\n"
        f'BASE = f"{{FQDN}}/api/v{plan.version}"\n'
        + ('PAYLOAD = {"name": "jamfpy"}\n' if writes else "")
    )
    return head + "\n\n" + "\n\n".join(tests)


def _pro_action_test(plan: Plan) -> str:
    return (
        f'"""Unit tests for the Pro {plan.class_name} action endpoint."""\n{_HEADER}'
        "import json\n\n"
        "from conftest import FQDN, sent_headers, with_bearer\n\n"
        "from jamfpy.client.constants import DEFAULT_HTTP_CONFIG_HEADERS as H\n\n"
        f'URL = f"{{FQDN}}/api/v{plan.version}{plan.uri}"\n'
        'PAYLOAD = {"name": "jamfpy"}\n\n\n'
        "def test_send_posts_json_payload(pro_api, mocked_responses):\n"
        "    mocked_responses.post(URL, status=201, json={})\n"
        f"    pro_api.{plan.attr}.send(PAYLOAD)\n"
        + _request_asserts("POST", "URL", 'H["crud"]["create-update"]["json"]')
        + "    assert json.loads(req.body) == PAYLOAD\n"
    )


def _composite_test(plan: Plan) -> str:
    by_id = "".join(f'    "{child.attr}": "{child.by_id_uri}",\n' for child in plan.children)
    accessor = f"getattr(classic_api.{plan.attr}, child)"
    url = 'f"{BASE}{BY_ID[child]}/7"'

    def child_test(name: str, body: str, fixtures: str = "classic_api, mocked_responses") -> str:
        return f'@pytest.mark.parametrize("child", BY_ID)\ndef {name}({fixtures}, child):\n{body}'

    return (
        f'"""Unit tests for the Classic {plan.class_name} composite endpoint and its sub-endpoints."""\n{_HEADER}'
        "import pytest\n"
        "from conftest import FQDN, sent_headers, with_bearer\n\n"
        "from jamfpy.client.constants import DEFAULT_HTTP_CONFIG_HEADERS as H\n\n"
        'BASE = f"{FQDN}/JSSResource"\n'
        f'COLLECTION = f"{{BASE}}{plan.uri}"\n'
        f"BY_ID = {{\n{by_id}}}\n\n\n"
        "def test_get_all_reads_the_whole_collection(classic_api, mocked_responses):\n"
        "    mocked_responses.get(COLLECTION, json={})\n"
        f"    classic_api.{plan.attr}.get_all()\n"
        + _request_asserts("GET", "COLLECTION", 'H["crud"]["read"]["json"]')
        + "\n\n"
        + child_test("test_child_get_all_reads_the_collection", (
            "    mocked_responses.get(COLLECTION, json={})\n"
            f"    {accessor}.get_all()\n"
            + _request_asserts("GET", "COLLECTION", 'H["crud"]["read"]["json"]')
        ))
        + "\n\n"
        + child_test("test_child_get_by_id_uses_its_by_id_uri", (
            f"    mocked_responses.get({url}, json={{}})\n"
            f"    {accessor}.get_by_id(7)\n"
            + _request_asserts("GET", url, 'H["crud"]["read"]["json"]')
        ))
        + "\n\n"
        + child_test("test_child_update_by_id_puts_xml", (
            f'    mocked_responses.put({url}, status=201, body="<id>7</id>")\n'
            f'    {accessor}.update_by_id(7, "<record/>")\n'
            + _request_asserts("PUT", url, 'H["crud"]["create-update"]["xml"]')
            + '    assert req.body == "<record/>"\n'
        ))
        + "\n\n"
        + child_test("test_child_create_posts_xml_to_id_zero", (
            '    mocked_responses.post(f"{BASE}{BY_ID[child]}/0", status=201, body="<id>8</id>")\n'
            f'    {accessor}.create("<record/>")\n'
            + _request_asserts("POST", 'f"{BASE}{BY_ID[child]}/0"', 'H["crud"]["create-update"]["xml"]')
            + '    assert req.body == "<record/>"\n'
        ))
        + "\n\n"
        + child_test("test_child_delete_by_id_sends_no_headers_of_its_own", (
            f"    mocked_responses.delete({url})\n"
            f"    {accessor}.delete_by_id(7)\n"
            + _request_asserts("DELETE", url, "{}")
        ))
        + "\n\n"
        + child_test("test_child_name_returns_its_attribute", f"    assert {accessor}.name() == child\n", "classic_api")
    )


def _append_specs(text: str, plan: Plan) -> str:
    """The live module with one spec per lifecycle-capable endpoint appended to ``SPECS``; each fails until filled in."""
    targets = [(f"{plan.attr}_{child.attr}", f"{plan.attr}.{child.attr}", child.attr) for child in plan.children]
    if not targets:
        targets = [(plan.attr, plan.attr, plan.name)]
    node = _list_assignment(text, "SPECS", LIVE_TESTS[plan.api])
    existing = {
        value.value
        for element in (node.value.elts if isinstance(node.value, ast.List) else [])
        if isinstance(element, ast.Dict)
        for key, value in zip(element.keys, element.values)
        if isinstance(key, ast.Constant) and key.value == "id" and isinstance(value, ast.Constant)
    }
    block: list[str] = []
    for spec_id, accessor, root in targets:
        if spec_id in existing:
            raise ScaffoldError(f"refused: a live spec with id {spec_id!r} already exists in {LIVE_TESTS[plan.api]}")
        note = "check root (one record's XML root element) and fill in the builders" if plan.api == "classic" else "fill in the builders"
        block += [
            "    {",
            f"        # Scaffolded from {plan.path}: {note}.",
            f'        "id": "{spec_id}",',
            f'        "accessor": "{accessor}",',
            *([f'        "root": "{root}",'] if plan.api == "classic" else []),
            f'        "min": {FILL_IN},',
            f'        "max": {FILL_IN},',
            "    },",
        ]
    return _append_to_list(text, "SPECS", block, LIVE_TESTS[plan.api])


def _bump_count(text: str, by: int) -> str:
    new, count = re.subn(r"^(EXPECTED_ENDPOINT_COUNT = )(\d+)$", lambda m: f"{m[1]}{int(m[2]) + by}", text, flags=re.MULTILINE)
    if count != 1:
        raise ScaffoldError(f"cannot find one 'EXPECTED_ENDPOINT_COUNT = <n>' line in {CONTRACT_TEST}")
    return new


# Writing


def write_all(root: Path, changes: Mapping[Path, str]) -> None:
    """Write every change or none: stage each to a temp file, then swap them in, restoring the originals on a failure."""
    staged: list[tuple[Path, Path, bytes | None]] = []
    try:
        for relative, text in changes.items():
            target = root / relative
            temp = target.with_name(f".{target.name}.scaffold-tmp")
            staged.append((target, temp, target.read_bytes() if target.exists() else None))
            temp.write_text(text, encoding="utf-8")
    except OSError as exc:
        _discard(staged)
        raise ScaffoldError(f"could not write {exc.filename or exc}: {exc.strerror or exc}; nothing was changed") from exc
    done: list[tuple[Path, bytes | None]] = []
    try:
        for target, temp, original in staged:
            os.replace(temp, target)
            done.append((target, original))
    except OSError as exc:
        for target, original in reversed(done):
            if original is None:
                target.unlink(missing_ok=True)
            else:
                target.write_bytes(original)
        _discard(staged)
        raise ScaffoldError(f"could not write {exc.filename or exc}: {exc.strerror or exc}; nothing was changed") from exc


def _discard(staged: Sequence[tuple[Path, Path, bytes | None]]) -> None:
    for _, temp, _ in staged:
        temp.unlink(missing_ok=True)


# CLI


def scaffold(api: str, key: str, root: Path, *, name: str | None = None, dry_run: bool = False) -> list[str]:
    """Classify, render and (unless ``dry_run``) write; returns the lines the CLI prints."""
    plan = classify(api, key, load_schema(api, root), name)
    changes = render(plan, root)
    lines = [plan.summary(), "would write:" if dry_run else "wrote:"]
    lines += [f"  {'changed' if (root / relative).exists() else 'new':<8} {relative}" for relative in changes]
    if not dry_run:
        write_all(root, changes)
    lines += plan.next_steps()
    lines.append("regenerate COVERAGE.md with make coverage-doc")
    return lines


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m tools.scaffold", description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--api", choices=APIS, required=True)
    parser.add_argument("--path", required=True, help="the collection path exactly as the schema has it, e.g. /v1/categories or /printers")
    parser.add_argument("--name", help="the PascalCase class name, in place of the one derived from the path (the attribute follows it)")
    parser.add_argument("--root", type=Path, default=REPO_ROOT, help="the repo to scaffold into (default: this one)")
    parser.add_argument("--dry-run", action="store_true", help="print the shape and the files it would write; write nothing")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI; returns the exit status. A refusal or write failure prints one line on stderr and exits 1."""
    args = _parser().parse_args(argv)
    try:
        lines = scaffold(args.api, args.path, args.root.resolve(), name=args.name, dry_run=args.dry_run)
    except (ScaffoldError, SchemaError) as exc:
        print(f"scaffold: {exc}", file=sys.stderr)
        return 1
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
