"""Read, query, pull and probe the Jamf Pro API schemas committed in ``api_schemas/``.

This is the one module that parses ``api_schemas/*.json``; anything else that needs a schema imports it.

- ``pro.json``: Jamf's OpenAPI 3 schema of the Pro API, pulled from ``https://<fqdn>/api/schema/``.
- ``classic.json``: Jamf's Swagger 2 schema of the Classic API. The server only serves it as YAML, at
  ``https://<fqdn>/classicapi/doc/swagger.yaml``; ``pull`` converts it to JSON.
- ``pro-supplement.json``: Pro paths the tenant serves but its schema leaves out, with the verbs an OPTIONS probe
  found. ``load_pro`` merges them into the schema's ``paths``; each carries ``"x-jamfpy-source": "options-probe"``.

The CLI is ``python -m tools.schemas {refresh,pull,probe,drift,paths,path}``; the make targets ``schemas`` (``refresh``),
``schema-paths`` and ``schema-path`` wrap it.
"""
# One module on purpose: it is the only reader of api_schemas/, so it outgrows pylint's 500-line default.
# pylint: disable=too-many-lines

import argparse
import datetime as dt
import difflib
import json
import os
import re
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, NamedTuple

import requests
import yaml

import jamfpy
from jamfpy.client.exceptions import JamfAuthError

Schema = dict[str, Any]

SCHEMA_DIR = Path(__file__).resolve().parent.parent / "api_schemas"
APIS = ("pro", "classic")
SCHEMA_FILES = {"pro": "pro.json", "classic": "classic.json"}
SUPPLEMENT_FILE = "pro-supplement.json"

FQDN_ENV = "JAMFPRO_INSTANCE_FQDN"
CLIENT_ID_ENV = "JAMFPRO_CLIENT_ID"
CLIENT_SECRET_ENV = "JAMFPRO_CLIENT_SECRET"
SOURCE_ENV = {"pro": "JAMFPY_PRO_SCHEMA_SOURCE", "classic": "JAMFPY_CLASSIC_SCHEMA_SOURCE"}
# What the Swagger UIs the server hosts (/api/doc/ and /classicapi/doc/) load. Both answer without authentication.
SCHEMA_URL_PATHS = {"pro": "/api/schema/", "classic": "/classicapi/doc/swagger.yaml"}
PULL_TIMEOUT = 60.0

# The operation keys of an OpenAPI path item, in the order the spec lists them.
HTTP_VERBS = ("get", "put", "post", "delete", "options", "head", "patch", "trace")
# The server's Allow header lists these on every route, and neither schema ever does, so the probe drops them.
IMPLICIT_VERBS = frozenset({"head", "options"})
# A probe URL needs a concrete value for each {param}; the Allow header is the same whether the record exists or not.
PLACEHOLDER_ID = "0"

SOURCE_KEY = "x-jamfpy-source"
PROBE_SOURCE = "options-probe"
PROBE_KEY = "x-jamfpy-probe"
ALLOW_MISSING = "allow-header-missing"
GENERATED_KEY = "x-jamfpy-generated"
REF_KEY = "x-jamfpy-ref"
UNRESOLVED_KEY = "x-jamfpy-unresolved"
NOTE_KEY = "x-jamfpy-note"
MAX_REF_DEPTH = 8
# How many schema names a drift summary lists per kind of change before it says "and N more".
MAX_LISTED_NAMES = 20
# What `path` reports about an operation besides its parameters and request body.
OPERATION_FIELDS = ("summary", "operationId", "deprecated", "x-deprecation-date", "x-required-privileges")

# A whole JSON string, escapes included, or a comma whose next non-blank character closes an object or array.
# Strings are matched as single tokens, so a comma inside one is never mistaken for a trailing comma.
_STRING_OR_TRAILING_COMMA = re.compile(r'"(?:[^"\\]|\\.)*"|,(?=\s*[}\]])', re.DOTALL)
_TEMPLATE_PARAM = re.compile(r"\{([^}/]+)\}")


class SchemaError(Exception):
    """A schema can't be found, fetched, parsed, queried or probed. The message is one line, fit for the CLI."""


class Drift(NamedTuple):
    """The names (paths, or schema definitions) that differ between two versions of a schema, each list sorted."""

    added: list[str]
    removed: list[str]
    changed: list[str]


# Loading


def strip_trailing_commas(text: str) -> str:
    """Remove the commas before a closing ``}`` or ``]`` that make ``text`` invalid JSON, leaving strings alone."""
    return _STRING_OR_TRAILING_COMMA.sub(lambda m: m.group() if m.group().startswith('"') else "", text)


def load_pro(directory: Path | None = None, *, supplement: bool = True) -> Schema:
    """The committed Pro schema with ``pro-supplement.json``'s paths merged in (see ``merge_supplement``).

    ``supplement=False`` gives the schema exactly as Jamf serves it. ``directory`` defaults to ``api_schemas/``.
    """
    folder = directory or SCHEMA_DIR
    schema = _read_json(folder / SCHEMA_FILES["pro"])
    supplement_file = folder / SUPPLEMENT_FILE
    if supplement and supplement_file.exists():
        merge_supplement(schema, _read_json(supplement_file))
    return schema


def merge_supplement(schema: Schema, supplement: Schema) -> Schema:
    """Add the supplement's paths to ``schema["paths"]`` in place, and return ``schema``.

    A path in both keeps the schema's entry: once Jamf documents a path, its own description is the better one.
    """
    for key, item in supplement["paths"].items():
        schema["paths"].setdefault(key, item)
    return schema


def load_classic(directory: Path | None = None) -> Schema:
    """The committed Classic schema, its verb keys normalised (see ``operations``).

    Trailing commas are tolerated, because earlier snapshots of the file had them. ``directory`` defaults to
    ``api_schemas/``.
    """
    schema = _read_json((directory or SCHEMA_DIR) / SCHEMA_FILES["classic"], tolerant=True)
    return normalise_verbs(schema)


def load(api: str, directory: Path | None = None) -> Schema:
    """``load_pro()`` or ``load_classic()``, by API name."""
    _check_api(api)
    return load_pro(directory) if api == "pro" else load_classic(directory)


def _read_json(file: Path, *, tolerant: bool = False) -> Schema:
    try:
        text = file.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise SchemaError(f"no schema file at {file}") from exc
    try:
        data = json.loads(strip_trailing_commas(text) if tolerant else text)
    except json.JSONDecodeError as exc:
        raise SchemaError(f"{file} is not valid JSON: {exc}") from exc
    return _require_schema(data, str(file))


def _require_schema(data: object, origin: str) -> Schema:
    if not isinstance(data, dict) or not isinstance(data.get("paths"), dict):
        raise SchemaError(f"{origin} is not an API schema: it has no 'paths' object")
    return data


def _check_api(api: str) -> None:
    if api not in APIS:
        raise ValueError(f"unknown API {api!r}: expected one of {', '.join(APIS)}")


# Verbs


def operations(item: Mapping[str, Any]) -> dict[str, Any]:
    """A path item's operations, keyed by lower-case verb.

    Jamf's Classic schema has a verb key with a leading space (``' delete'``). It counts as that verb, unless the item
    also has the proper key, which wins.
    """
    ops: dict[str, Any] = {}
    for key, operation in item.items():
        verb = key.strip().lower()
        if verb in HTTP_VERBS and (verb not in ops or key == verb):
            ops[verb] = operation
    return ops


def verbs(item: Mapping[str, Any]) -> list[str]:
    """A path item's verbs, lower-case and sorted."""
    return sorted(operations(item))


def normalise_verbs(schema: Schema) -> Schema:
    """Respell every path item's verb keys properly, in place and in their original position, and return ``schema``."""
    for key, item in schema["paths"].items():
        schema["paths"][key] = _normalise_item(item)
    return schema


def _normalise_item(item: Mapping[str, Any]) -> dict[str, Any]:
    ops = operations(item)
    fixed: dict[str, Any] = {}
    for name, value in item.items():
        verb = name.strip().lower()
        if verb in ops:
            # Whichever spelling comes first keeps its position; the value is the one operations() chose.
            fixed.setdefault(verb, ops[verb])
        else:
            fixed[name] = value
    return fixed


# Lookup


def paths(api: str, match: str | None = None, *, schema: Schema | None = None) -> list[tuple[str, list[str]]]:
    """Every path containing ``match`` (case-insensitive; every path when ``None``), sorted, with its verbs.

    ``schema`` defaults to the committed one for ``api``; pass one already loaded to save reading the file again.
    """
    loaded = load(api) if schema is None else schema
    needle = (match or "").lower()
    return [(key, verbs(item)) for key, item in sorted(loaded["paths"].items()) if needle in key.lower()]


def path(api: str, key: str, *, schema: Schema | None = None) -> Schema:
    """One path's methods, each with its parameters and resolved request body.

    The result has ``api``, ``path``, the supplement's ``x-jamfpy-*`` markers when the path came from it, and
    ``methods``: per verb, the operation's summary-level fields, ``parameters`` (path-level ones included, overridden
    by the operation's own of the same name and location) and, when it takes one, ``requestBody``, always shaped
    ``{"contentTypes": [...], "required": bool, "schema": {...}}``. Swagger 2's ``in: body`` parameters become that
    ``requestBody``: one parameter gives its schema as it is, several are merged into one object schema (see
    ``_swagger_body``). Every ``$ref`` (OpenAPI 3 ``components``, Swagger 2 ``definitions``) is replaced by its target
    (see ``resolve``).

    Raises ``SchemaError`` when the schema has no such path.
    """
    loaded = load(api) if schema is None else schema
    items = loaded["paths"]
    if key not in items:
        close = difflib.get_close_matches(key, list(items), n=3)
        hint = f"; closest: {', '.join(close)}" if close else ""
        raise SchemaError(f"the {api} schema has no path {key}{hint}")
    item = items[key]
    shared = [resolve(param, loaded) for param in item.get("parameters", [])]
    result: Schema = {"api": api, "path": key}
    result.update({marker: item[marker] for marker in (SOURCE_KEY, PROBE_KEY) if marker in item})
    result["methods"] = {verb: _describe(op, shared, loaded) for verb, op in sorted(operations(item).items())}
    return result


def _describe(operation: Mapping[str, Any], shared: list[Any], schema: Schema) -> Schema:
    described: Schema = {field: operation[field] for field in OPERATION_FIELDS if field in operation}
    own = [resolve(param, schema) for param in operation.get("parameters", [])]
    own_keys = {(param.get("name"), param.get("in")) for param in own}
    params = [param for param in shared if (param.get("name"), param.get("in")) not in own_keys] + own
    body: Schema | None = None
    if "requestBody" in operation:
        request_body = resolve(operation["requestBody"], schema)
        content = request_body.get("content", {})
        # Every body in Jamf's schemas has one schema for all its content types, so the first stands for them all.
        first: dict[str, Any] = next(iter(content.values()), {})
        body = {"required": request_body.get("required", False), "contentTypes": list(content), "schema": first.get("schema", {})}
    body_params = [param for param in params if param.get("in") == "body"]
    if body_params:
        body = _swagger_body(body_params, operation.get("consumes", schema.get("consumes", [])))
    described["parameters"] = [param for param in params if param.get("in") != "body"]
    if body is not None:
        described["requestBody"] = body
    return described


def _swagger_body(body_params: list[Any], content_types: list[str]) -> Schema:
    """One ``requestBody`` from an operation's resolved ``in: body`` parameters.

    Swagger 2 allows one such parameter, but Jamf's Classic schema declares several on some operations (16 on
    ``POST /mobiledevicecommands/command``, one per XML element). Keeping only one would drop the rest, so several
    become a single object schema with a property per parameter; the note says it was synthesised.
    """
    if len(body_params) == 1:
        param = body_params[0]
        return {"required": param.get("required", False), "contentTypes": content_types, "schema": param.get("schema", {})}
    merged: Schema = {
        "type": "object",
        "properties": {param.get("name", "body"): param.get("schema", {}) for param in body_params},
        "required": [param.get("name", "body") for param in body_params if param.get("required", False)],
        NOTE_KEY: f"{len(body_params)} in: body parameters merged into one object schema",
    }
    # The body is needed as soon as one of its parameters is.
    return {"required": bool(merged["required"]), "contentTypes": content_types, "schema": merged}


def resolve(node: Any, schema: Schema, _chain: tuple[str, ...] = ()) -> Any:
    """``node`` with every local ``$ref`` in it replaced by what it points at.

    A resolved object keeps the reference under ``x-jamfpy-ref``. A reference that is already being resolved further
    up (a cycle), that is more than ``MAX_REF_DEPTH`` references deep, or whose target doesn't exist is left as the
    ``$ref``, with ``x-jamfpy-unresolved`` set to ``cycle``, ``depth`` or ``missing``.
    """
    if isinstance(node, list):
        return [resolve(child, schema, _chain) for child in node]
    if not isinstance(node, dict):
        return node
    ref = node.get("$ref")
    if not isinstance(ref, str):
        return {key: resolve(value, schema, _chain) for key, value in node.items()}
    reason = "cycle" if ref in _chain else "depth" if len(_chain) >= MAX_REF_DEPTH else None
    target = None if reason else _lookup(schema, ref)
    if target is None:
        return {"$ref": ref, UNRESOLVED_KEY: reason or "missing"}
    siblings = {key: value for key, value in node.items() if key != "$ref"}
    return {REF_KEY: ref, **resolve({**target, **siblings}, schema, (*_chain, ref))}


def _lookup(schema: Schema, ref: str) -> dict[str, Any] | None:
    """The object a local JSON pointer such as ``#/components/schemas/Script`` names, or ``None``."""
    if not ref.startswith("#/"):
        return None
    node: Any = schema
    for part in ref[2:].split("/"):
        name = part.replace("~1", "/").replace("~0", "~")
        if not isinstance(node, dict) or name not in node:
            return None
        node = node[name]
    return node if isinstance(node, dict) else None


# Pull


def normalise_fqdn(fqdn: str) -> str:
    """``https://<host>`` from a bare host, or from a URL with any scheme or a trailing slash."""
    host = re.sub(r"^[A-Za-z][A-Za-z0-9+.-]*://", "", fqdn.strip()).rstrip("/")
    return f"https://{host}"


def default_source(api: str, env: Mapping[str, str] | None = None) -> str:
    """Where ``pull`` reads ``api``'s schema from by default.

    ``JAMFPY_PRO_SCHEMA_SOURCE`` / ``JAMFPY_CLASSIC_SCHEMA_SOURCE`` (a URL or a local path) when set, else the schema
    URL on the tenant in ``JAMFPRO_INSTANCE_FQDN``. Raises ``SchemaError`` when neither is set.
    """
    _check_api(api)
    variables = os.environ if env is None else env
    override = variables.get(SOURCE_ENV[api], "").strip()
    if override:
        return override
    fqdn = variables.get(FQDN_ENV, "").strip()
    if not fqdn:
        raise SchemaError(f"no source for the {api} schema: set {FQDN_ENV} (copy .env.example to .env) or {SOURCE_ENV[api]}")
    return normalise_fqdn(fqdn) + SCHEMA_URL_PATHS[api]


def pull(api: str, source: str) -> Schema:
    """Fetch ``api``'s schema from ``source``, a URL or a local path, and parse it into what ``save`` writes.

    Pro is JSON. The server labels it ``charset=ISO-8859-1`` but sends UTF-8, so the bytes are decoded as UTF-8
    whatever the header says. Classic is Swagger 2 YAML, the only form the server has; it is read with
    ``yaml.safe_load``, its verb keys are normalised (``' delete'`` becomes ``delete``), and the dates YAML parses
    stay ``date`` objects until ``save`` writes them as ISO strings. Key order is the source's.
    """
    _check_api(api)
    raw = _fetch(source)
    try:
        text = raw.decode("utf-8")
        data = json.loads(text) if api == "pro" else yaml.safe_load(text)
    except (UnicodeDecodeError, json.JSONDecodeError, yaml.YAMLError) as exc:
        raise SchemaError(f"could not parse the {api} schema from {source}: {_one_line(exc)}") from exc
    schema = _require_schema(data, source)
    return normalise_verbs(schema) if api == "classic" else schema


def _fetch(source: str) -> bytes:
    if re.match(r"https?://", source, re.IGNORECASE):
        try:
            response = requests.get(source, timeout=PULL_TIMEOUT)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise SchemaError(f"could not fetch {source}: {_one_line(exc)}") from exc
        return response.content
    try:
        return Path(source).expanduser().read_bytes()
    except OSError as exc:
        raise SchemaError(f"could not read {source}: {exc.strerror or exc}") from exc


def save(schema: Schema, file: Path) -> None:
    """Write ``schema`` as JSON laid out for stable diffs: 2-space indent, the source's key order, final newline.

    Non-ASCII text is written as UTF-8 rather than escaped, so the file reads like the source.
    """
    file.write_text(json.dumps(schema, indent=2, sort_keys=False, ensure_ascii=False, default=_json_default) + "\n", encoding="utf-8")


def _json_default(value: object) -> str:
    # YAML reads unquoted dates (Classic's x-deprecation-date) as date objects, which JSON has no type for.
    if isinstance(value, dt.date):
        return value.isoformat()
    raise TypeError(f"{type(value).__name__} is not JSON serialisable")


def _one_line(exc: BaseException) -> str:
    return " ".join(str(exc).split())


# Probe


def tenant_from_env(env: Mapping[str, str] | None = None) -> jamfpy.Tenant:
    """An OAuth ``Tenant`` built from ``JAMFPRO_INSTANCE_FQDN``, ``JAMFPRO_CLIENT_ID`` and ``JAMFPRO_CLIENT_SECRET``."""
    variables = os.environ if env is None else env
    missing = [name for name in (FQDN_ENV, CLIENT_ID_ENV, CLIENT_SECRET_ENV) if not variables.get(name, "").strip()]
    if missing:
        raise SchemaError(f"the probe needs {', '.join(missing)} set (copy .env.example to .env)")
    return jamfpy.Tenant(
        fqdn=normalise_fqdn(variables[FQDN_ENV]),
        auth_method="oauth2",
        client_id=variables[CLIENT_ID_ENV],
        client_secret=variables[CLIENT_SECRET_ENV],
    )


def probe(supplement: Schema, tenant: jamfpy.Tenant, *, now: dt.datetime | None = None) -> Schema:
    """Probe every path template the supplement lists and return the supplement rebuilt from the answers.

    Each template goes out as an OPTIONS request through ``tenant.pro.do()``, so with the tenant's token, with ``0``
    in place of each ``{param}``. Its verbs are those in the ``Allow`` header, less HEAD and OPTIONS. A response with
    no ``Allow`` header keeps the verbs the supplement already records for that path, marked
    ``"x-jamfpy-probe": "allow-header-missing"``. Every entry is marked ``"x-jamfpy-source": "options-probe"`` and
    gets a string path parameter per ``{param}``.

    ``generatedAt`` moves only when the probed paths differ from the ones the supplement records, so a probe that
    finds nothing new leaves the file byte-identical once saved.

    Raises ``SchemaError`` for a template without a ``/v<n>`` prefix, a non-2xx answer, or a path left with no verbs.
    """
    probed: dict[str, Schema] = {}
    for template, item in supplement["paths"].items():
        entry: Schema = {SOURCE_KEY: PROBE_SOURCE}
        found = _allowed_verbs(tenant, template)
        if found is None:
            found = verbs(item)
            entry[PROBE_KEY] = ALLOW_MISSING
        if not found:
            raise SchemaError(f"OPTIONS found no verbs for {template}, and the supplement records none")
        params = [
            {"name": name, "in": "path", "required": True, "schema": {"type": "string"}}
            for name in _TEMPLATE_PARAM.findall(template)
        ]
        if params:
            entry["parameters"] = params
        entry.update({verb: {} for verb in HTTP_VERBS if verb in found})
        probed[template] = entry
    recorded = supplement.get(GENERATED_KEY, {}).get("generatedAt")
    if isinstance(recorded, str) and _canonical(supplement["paths"]) == _canonical(probed):
        stamp = recorded
    else:
        stamp = (now or dt.datetime.now(dt.UTC)).isoformat(timespec="seconds")
    return {
        GENERATED_KEY: {
            "generatedAt": stamp,
            "method": "OPTIONS request per path through jamfpy with the tenant's token; verbs from the Allow header, "
                      "less HEAD and OPTIONS",
            "note": "Written by `make schemas`; the path list is curated by hand, the verbs are always probed, never "
                    "typed. These are Pro paths the tenant serves but /api/schema/ leaves out; tools.schemas.load_pro "
                    "merges them in.",
        },
        "paths": probed,
    }


def _allowed_verbs(tenant: jamfpy.Tenant, template: str) -> list[str] | None:
    """The verbs the tenant's ``Allow`` header lists for ``template``, or ``None`` when it sends none."""
    match = re.fullmatch(r"/v(\d+)(/.*)", template)
    if match is None:
        raise SchemaError(f"supplement path {template} has no /v<n> version prefix")
    url = tenant.pro.url(match[1]) + _TEMPLATE_PARAM.sub(PLACEHOLDER_ID, match[2])
    response = tenant.pro.do(requests.Request("OPTIONS", url))
    if not response.ok:
        raise SchemaError(f"OPTIONS {url} returned {response.status_code}")
    allow = response.headers.get("Allow", "")
    if not allow.strip():
        return None
    listed = {verb.strip().lower() for verb in allow.split(",")}
    return [verb for verb in HTTP_VERBS if verb in listed and verb not in IMPLICIT_VERBS]


# Drift


def drift(api: str, new: Schema, old: Schema) -> Drift:
    """Paths added in ``new``, removed from ``old``, and changed between them.

    A path has changed when its verbs or its JSON differ; key order doesn't count. Classic verb keys are normalised
    first, so ``' delete'`` and ``delete`` are the same. ``definitions_drift`` does the same for the schemas the
    paths point at.
    """
    return _diff(_comparable(api, new), _comparable(api, old))


def definitions_drift(api: str, new: Schema, old: Schema) -> Drift:
    """Schema definitions (Pro ``components.schemas``, Classic ``definitions``) added, removed and changed.

    A schema counts as changed when its JSON differs; key order doesn't count. A schema with no definitions at all
    (such as the supplement) has none to add or remove.
    """
    return _diff(_definitions(api, new) or {}, _definitions(api, old) or {})


def drift_summary(api: str, new: Schema, old: Schema, *, label: str | None = None) -> str:
    """``drift()`` as text: a headline with the counts before and after, then one line per path that differs.

    ``+`` added and ``-`` removed paths show their verbs; ``~`` changed ones show any verb change and which keys of the
    path item differ. When either schema has definitions, the headline also carries their counts and a ``schemas``
    line per kind of change lists the names, ``MAX_LISTED_NAMES`` at most. ``label`` names the schema in the headline
    (default: ``api``).
    """
    result = drift(api, new, old)
    new_paths, old_paths = _comparable(api, new), _comparable(api, old)
    new_defs, old_defs = _definitions(api, new), _definitions(api, old)
    headline = f"{label or api}: {len(old_paths)} -> {len(new_paths)} paths ({_counts(result)})"
    lines: list[str] = []
    lines += [f"  + {key}  [{' '.join(verbs(new_paths[key]))}]" for key in result.added]
    lines += [f"  - {key}  [{' '.join(verbs(old_paths[key]))}]" for key in result.removed]
    lines += [f"  ~ {key}  ({_describe_change(old_paths[key], new_paths[key])})" for key in result.changed]
    if new_defs is not None or old_defs is not None:
        defs = definitions_drift(api, new, old)
        headline += f"; {len(old_defs or {})} -> {len(new_defs or {})} schemas ({_counts(defs)})"
        for sign, names in (("+", defs.added), ("-", defs.removed), ("~", defs.changed)):
            if names:
                lines.append(f"  schemas {sign} {_listed(names)}")
    return "\n".join([headline, *lines])


def _diff(new: Mapping[str, Any], old: Mapping[str, Any]) -> Drift:
    shared = new.keys() & old.keys()
    return Drift(
        added=sorted(new.keys() - old.keys()),
        removed=sorted(old.keys() - new.keys()),
        changed=sorted(key for key in shared if _canonical(new[key]) != _canonical(old[key])),
    )


def _counts(result: Drift) -> str:
    return f"{len(result.added)} added, {len(result.removed)} removed, {len(result.changed)} changed"


def _listed(names: list[str]) -> str:
    shown = names[:MAX_LISTED_NAMES]
    if len(names) > MAX_LISTED_NAMES:
        shown.append(f"\u2026 and {len(names) - MAX_LISTED_NAMES} more")
    return ", ".join(shown)


def _definitions(api: str, schema: Schema) -> dict[str, Any] | None:
    """The schema's definitions object, or ``None`` when it has none."""
    _check_api(api)
    node = schema.get("components", {}).get("schemas") if api == "pro" else schema.get("definitions")
    return node if isinstance(node, dict) else None


def _comparable(api: str, schema: Schema) -> dict[str, Any]:
    _check_api(api)
    items: dict[str, Any] = schema["paths"]
    return {key: _normalise_item(item) for key, item in items.items()} if api == "classic" else items


def _describe_change(old: Mapping[str, Any], new: Mapping[str, Any]) -> str:
    before, after = verbs(old), verbs(new)
    differing = [key for key in sorted(old.keys() | new.keys()) if _canonical(old.get(key)) != _canonical(new.get(key))]
    verb_change = f"verbs {' '.join(before)} -> {' '.join(after)}; " if before != after else ""
    return f"{verb_change}differs in {', '.join(differing)}"


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, default=_json_default)


# CLI


def _committed(api: str) -> Schema:
    """The committed schema as Jamf serves it (Pro without the supplement), or an empty one when there is no file."""
    if not (SCHEMA_DIR / SCHEMA_FILES[api]).exists():
        return {"paths": {}}
    return load_pro(SCHEMA_DIR, supplement=False) if api == "pro" else load_classic(SCHEMA_DIR)


def _pull_all(sources: Mapping[str, str]) -> dict[str, Schema]:
    """Fetch and parse every source; nothing is written, so one failure leaves ``api_schemas/`` as it was."""
    return {api: pull(api, source) for api, source in sources.items()}


def _write_pulled(pulled: Mapping[str, Schema], sources: Mapping[str, str]) -> None:
    for api, schema in pulled.items():
        old = _committed(api)
        save(schema, SCHEMA_DIR / SCHEMA_FILES[api])
        print(f"{api}: pulled from {sources[api]}")
        print(drift_summary(api, schema, old))


def _run_probe(old: Schema, tenant: jamfpy.Tenant) -> Schema:
    try:
        return probe(old, tenant)
    except (requests.RequestException, JamfAuthError) as exc:
        raise SchemaError(f"probe failed: {_one_line(exc)}") from exc
    finally:
        # Invalidates the probe's token; a no-op when the probe failed before fetching one.
        tenant.pro.close()


def _write_probed(new: Schema, old: Schema) -> None:
    save(new, SCHEMA_DIR / SUPPLEMENT_FILE)
    print(drift_summary("pro", new, old, label="pro-supplement"))


def _cmd_refresh(_args: argparse.Namespace) -> None:
    # What `make schemas` runs. Every prerequisite (both sources, the supplement, the probe's credentials) is checked
    # and every fetch and probe made before the first write, so a failure at any step leaves all three files as they were.
    sources = {api: default_source(api) for api in APIS}
    old_supplement = _read_json(SCHEMA_DIR / SUPPLEMENT_FILE)
    tenant = tenant_from_env()
    pulled = _pull_all(sources)
    new_supplement = _run_probe(old_supplement, tenant)
    _write_pulled(pulled, sources)
    _write_probed(new_supplement, old_supplement)


def _cmd_pull(args: argparse.Namespace) -> None:
    sources = {api: default_source(api) for api in ([args.api] if args.api else APIS)}
    _write_pulled(_pull_all(sources), sources)


def _cmd_probe(_args: argparse.Namespace) -> None:
    old = _read_json(SCHEMA_DIR / SUPPLEMENT_FILE)
    _write_probed(_run_probe(old, tenant_from_env()), old)


def _cmd_drift(args: argparse.Namespace) -> None:
    source = args.source or default_source(args.api)
    print(drift_summary(args.api, pull(args.api, source), _committed(args.api)))


def _cmd_paths(args: argparse.Namespace) -> None:
    schema = load(args.api)
    rows = paths(args.api, args.match, schema=schema)
    if not rows:
        raise SchemaError(f"no {args.api} path contains {args.match!r}")
    width = max(len(key) for key, _ in rows)
    for key, path_verbs in rows:
        item = schema["paths"][key]
        markers = [str(item[marker]) for marker in (SOURCE_KEY, PROBE_KEY) if marker in item]
        suffix = f"  [{', '.join(markers)}]" if markers else ""
        print(f"{key:<{width}}  {' '.join(path_verbs)}{suffix}")


def _cmd_path(args: argparse.Namespace) -> None:
    print(json.dumps(path(args.api, args.path), indent=2, ensure_ascii=False, default=_json_default))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m tools.schemas", description=__doc__.splitlines()[0] if __doc__ else None)
    commands = parser.add_subparsers(dest="command", required=True)

    refresh_cmd = commands.add_parser(
        "refresh", help="pull both schemas and re-probe the supplement, writing all three files only once every step has succeeded"
    )
    refresh_cmd.set_defaults(run=_cmd_refresh)

    pull_cmd = commands.add_parser("pull", help="fetch the schemas, rewrite api_schemas/ and print the drift")
    pull_cmd.add_argument("--api", choices=APIS, help="pull only this API (default: both)")
    pull_cmd.set_defaults(run=_cmd_pull)

    probe_cmd = commands.add_parser("probe", help="re-probe the supplement's paths with OPTIONS and rewrite it")
    probe_cmd.set_defaults(run=_cmd_probe)

    drift_cmd = commands.add_parser("drift", help="print the drift between a source and the committed schema; writes nothing")
    drift_cmd.add_argument("--api", choices=APIS, required=True)
    drift_cmd.add_argument("--source", help="a URL or local path (default: as pull)")
    drift_cmd.set_defaults(run=_cmd_drift)

    paths_cmd = commands.add_parser("paths", help="list the paths containing a string, with their verbs")
    paths_cmd.add_argument("--api", choices=APIS, required=True)
    paths_cmd.add_argument("--match", help="case-insensitive substring (default: every path)")
    paths_cmd.set_defaults(run=_cmd_paths)

    path_cmd = commands.add_parser("path", help="print one path's methods, parameters and resolved request bodies as JSON")
    path_cmd.add_argument("--api", choices=APIS, required=True)
    path_cmd.add_argument("path", help="the path exactly as the schema has it, e.g. /v1/scripts")
    path_cmd.set_defaults(run=_cmd_path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI; returns the exit status. A ``SchemaError`` prints as one line on stderr and exits 1."""
    args = _parser().parse_args(argv)
    try:
        args.run(args)
    except SchemaError as exc:
        print(f"schemas: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
