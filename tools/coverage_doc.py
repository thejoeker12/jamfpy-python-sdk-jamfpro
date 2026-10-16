"""Generate COVERAGE.md from the wired endpoints, the API schemas and the live specs.

``python -m tools.coverage_doc [--root <repo>] [--check]``. ``make coverage-doc`` writes ``<root>/COVERAGE.md``;
``make coverage-doc-check`` (part of ``make check`` and CI) writes nothing and exits 1 with a unified diff when the
committed file differs from what would be written. The output has no timestamps, so the check is byte-stable.

Nothing in the file is typed by hand. Its sources:

- the endpoints: every ``Endpoint`` attribute of a ``ClassicAPI`` and a ``ProAPI``, recursing into composites
  (``classic.accounts.users``), as ``tests/contract_test.py`` discovers them; for each, its public methods and the
  requests they actually send, recorded by calling every method with dummy arguments under a stub ``do``
  (``tools.introspect``, shared with the contract test);
- the schemas, through ``tools.schemas`` (Pro with ``pro-supplement.json`` merged in): whether each recorded path and
  verb is in them, the resources each API has, and from those what is not yet covered;
- the live modules' ``SPECS`` and ``LIVE_NOT_COVERED``. Every endpoint needs a spec or a reason it has none; an
  endpoint with neither, or a spec or reason naming an endpoint that is not wired, fails the run with one line naming
  the accessor.
"""
# One module on purpose: the file's prose sits next to the code that fills it in, which outgrows this repo's
# 500-line max-module-lines (.pylintrc; pylint's own default is 1000).
# pylint: disable=too-many-lines

import argparse
import ast
import difflib
import importlib
import re
import sys
import textwrap
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, NamedTuple

import jamfpy
from jamfpy.endpoints.models import Endpoint
from tools.introspect import DummyValueError, Sent, normalise, record_requests
from tools.scaffold import FILL_IN, LIVE_TESTS
from tools.schemas import APIS, PROBE_SOURCE, SOURCE_KEY, Schema, SchemaError, load_classic, load_pro, verbs

REPO_ROOT = Path(__file__).resolve().parent.parent
COVERAGE_FILE = "COVERAGE.md"
SCHEMA_DIR = "api_schemas"
# Never contacted: auth is lazy, and the recorder answers every request itself. A .invalid name can never resolve (RFC 2606).
STUB_FQDN = "https://coverage-doc.invalid"
# The message in the builders `make scaffold` writes: a live test with one can only fail. Read out of FILL_IN, not retyped.
PLACEHOLDER: str = next(
    node.value for node in ast.walk(ast.parse(FILL_IN, mode="eval")) if isinstance(node, ast.Constant) and isinstance(node.value, str)
)
BUILDERS = ("min", "max")
YES, NO, NOT_APPLICABLE = "✅", "❌", "N/A"
LABELS = {"classic": "Classic", "pro": "Pro"}
# Rough width of the "Not yet covered" lists.
WRAP = 100

_VERSION_SEGMENT = re.compile(r"v\d+")


class CoverageDocError(Exception):
    """The generator cannot build the file. Each line of the message is one problem, fit for the CLI."""


class SentPath(NamedTuple):
    """A path an endpoint's methods send to, the verbs they send there, and what the schema has for that path.

    ``schema`` is the verbs the schema gives the path, ``None`` when it has no such path; ``probed`` is whether the
    path is only in ``pro-supplement.json``.
    """

    path: str
    sent: list[str]
    schema: list[str] | None
    probed: bool


@dataclass(frozen=True)
class Wrapped:
    """One wired endpoint, as the covered tables show it: its methods and the requests each one sends."""

    accessor: str
    api: str
    uri: str
    # Method name to the distinct requests it sent under dummy arguments (see tools.introspect.record_requests).
    requests: Mapping[str, tuple[Sent, ...]]

    @property
    def methods(self) -> tuple[str, ...]:
        """The public methods, sorted."""
        return tuple(self.requests)

    @property
    def sent(self) -> dict[str, list[str]]:
        """Each path some method sends to, sorted, with the sorted verbs sent there."""
        verbs_by_path: dict[str, set[str]] = {}
        for requests in self.requests.values():
            for request in requests:
                verbs_by_path.setdefault(request.path, set()).add(request.verb)
        return {path: sorted(found) for path, found in sorted(verbs_by_path.items())}

    @property
    def versions(self) -> list[str]:
        """The ``/v{n}`` prefixes of the paths sent to, lowest first; none for Classic or an unversioned Pro path."""
        if self.api != "pro":
            return []
        first_segments = {path.split("/")[1] for path in self.sent}
        found = {segment for segment in first_segments if _VERSION_SEGMENT.fullmatch(segment)}
        return sorted(found, key=lambda version: int(version[1:]))

    @property
    def version(self) -> str | None:
        """The one ``v{n}`` every request goes to, ``None`` when there is none or the methods hit different ones."""
        return self.versions[0] if len(self.versions) == 1 else None

    @property
    def path(self) -> str:
        """The collection's schema path: ``_uri``, under ``/v{n}`` when the methods send to exactly one Pro version."""
        return f"/{self.version}{self.uri}" if self.version else self.uri

    @property
    def resource(self) -> str:
        """The resource the endpoint's path belongs to (see ``resource``)."""
        return resource(self.api, self.path)


@dataclass(frozen=True)
class LiveRow:
    """One row of the live table: a spec's builders and notes, or N/A and the reason there is no spec."""

    accessor: str
    min: str
    max: str
    notes: str


# Endpoints


def stub_apis() -> dict[str, jamfpy.API]:
    """A ``ClassicAPI`` and a ``ProAPI`` to introspect, sharing one ``OAuth`` with dummy credentials.

    Auth is lazy, so building them sends nothing. Endpoints are called only under ``record_requests``, whose stub ``do``
    answers each request itself: the credentials and the FQDN are never used.
    """
    auth = jamfpy.OAuth(fqdn=STUB_FQDN, client_id="coverage-doc", client_secret="coverage-doc")
    return {"classic": jamfpy.ClassicAPI(fqdn=STUB_FQDN, auth=auth), "pro": jamfpy.ProAPI(fqdn=STUB_FQDN, auth=auth)}


def discover(apis: Mapping[str, object]) -> dict[str, Endpoint]:
    """Every endpoint reachable from each API, keyed by dotted accessor (``classic.accounts.users``) and sorted."""
    found: dict[str, Endpoint] = {}
    for api, owner in apis.items():
        _collect(owner, api, found)
    return dict(sorted(found.items()))


def _collect(owner: object, prefix: str, found: dict[str, Endpoint]) -> None:
    for attr, value in vars(owner).items():
        if attr.startswith("_") or not isinstance(value, Endpoint):
            continue
        accessor = f"{prefix}.{attr}"
        found[accessor] = value
        _collect(value, accessor, found)


def describe(accessor: str, endpoint: Endpoint, apis: Mapping[str, jamfpy.API]) -> Wrapped:
    """The covered-table facts of one endpoint: its API, ``_uri``, public methods and the requests each sends.

    ``apis`` are the objects ``discover`` walked; the endpoint's own (its first accessor segment) is the one whose
    ``do`` is stubbed while its methods run.
    """
    api = accessor.split(".", 1)[0]
    try:
        requests = record_requests(endpoint, api, apis[api])
    except DummyValueError as exc:
        raise CoverageDocError(f"{accessor}: {exc}") from exc
    # _uri is private on purpose; the generator reads it to name the endpoint's resource.
    return Wrapped(accessor, api, endpoint._uri, requests)  # pylint: disable=protected-access


# Schemas


def resource(api: str, path: str) -> str:
    """The resource a path belongs to: its first segment, after the ``/v{n}`` prefix for Pro.

    ``/v1/scripts/{id}`` and ``/v2/mdm/commands`` belong to ``scripts`` and ``mdm``; a Pro path with no version
    (``/preview/computers``) to its first segment, as every Classic path (``/accounts/userid/{id}``: ``accounts``).
    """
    segments = path.strip("/").split("/")
    if api == "pro" and len(segments) > 1 and _VERSION_SEGMENT.fullmatch(segments[0]):
        segments = segments[1:]
    return segments[0]


def schema_resources(api: str, schema: Schema) -> list[str]:
    """Every resource the schema has a path in, sorted."""
    return sorted({resource(api, key) for key in schema["paths"]})


def supplement_only(schema: Schema) -> list[str]:
    """The Pro resources whose every path came from ``pro-supplement.json``: Jamf's own schema has none of them."""
    probed: dict[str, bool] = {}
    for key, item in schema["paths"].items():
        name = resource("pro", key)
        probed[name] = probed.get(name, True) and item.get(SOURCE_KEY) == PROBE_SOURCE
    return sorted(name for name, only in probed.items() if only)


def covered(api: str, schema: Schema, endpoints: Iterable[Wrapped]) -> list[str]:
    """The schema's resources at least one wired endpoint falls in, sorted."""
    wrapped = {endpoint.resource for endpoint in endpoints if endpoint.api == api}
    return [name for name in schema_resources(api, schema) if name in wrapped]


def not_covered(api: str, schema: Schema, endpoints: Iterable[Wrapped]) -> list[str]:
    """The schema's resources no wired endpoint falls in, sorted."""
    wrapped = {endpoint.resource for endpoint in endpoints if endpoint.api == api}
    return [name for name in schema_resources(api, schema) if name not in wrapped]


def sent_paths(endpoint: Wrapped, schema: Schema) -> list[SentPath]:
    """The paths an endpoint's methods send to, with the verbs sent and what the schema has for each, sorted by path.

    Paths compare normalised (``{id}`` for every id segment, as the contract test does). A path or verb the schema
    lacks is kept, with ``schema`` ``None`` or without that verb, so the gap shows.
    """
    # Two schema paths that differ only in a parameter's name are one path once normalised: their verbs add up.
    index: dict[str, tuple[set[str], bool]] = {}
    for key, item in schema["paths"].items():
        known, probed = index.get(normalise(key), (set(), True))
        index[normalise(key)] = (known | set(verbs(item)), probed and item.get(SOURCE_KEY) == PROBE_SOURCE)
    found = []
    for path, sent in endpoint.sent.items():
        in_schema = index.get(path)
        found.append(SentPath(path, sent, sorted(in_schema[0]) if in_schema else None, bool(in_schema and in_schema[1])))
    return found


# Live specs


def load_live(root: Path) -> tuple[dict[str, list[dict[str, Any]]], dict[str, dict[str, str]]]:
    """Each live module's ``SPECS`` and ``LIVE_NOT_COVERED``, keyed by API.

    The modules import without a tenant: their only import-time work is defining the specs and a pytest marker.
    Raises ``CoverageDocError`` for a missing list or dict, and, one line each, for a spec that is not a dict and for
    a reason that is not a string with something in it (naming the accessor).
    """
    specs: dict[str, list[dict[str, Any]]] = {}
    reasons: dict[str, dict[str, str]] = {}
    problems: list[str] = []
    for api in APIS:
        where = LIVE_TESTS[api]
        module = _import_from(root, ".".join(where.with_suffix("").parts))
        spec_list = getattr(module, "SPECS", None)
        if not isinstance(spec_list, list):
            raise CoverageDocError(f"{where} has no SPECS list")
        problems += [f"{where}: SPECS[{index}] is not a dict" for index, spec in enumerate(spec_list) if not isinstance(spec, dict)]
        reason_map = getattr(module, "LIVE_NOT_COVERED", None)
        if not isinstance(reason_map, dict):
            raise CoverageDocError(f"{where} has no LIVE_NOT_COVERED dict of accessor to reason")
        # strip(): a reason of spaces renders as an empty cell, which says nothing.
        problems += [
            f"{where}: LIVE_NOT_COVERED has no reason for {api}.{accessor}: give a string with something in it"
            for accessor, reason in reason_map.items()
            if not isinstance(reason, str) or not reason.strip()
        ]
        specs[api] = spec_list
        reasons[api] = reason_map
    if problems:
        raise CoverageDocError("\n".join(problems))
    return specs, reasons


def is_placeholder(builder: object) -> bool:
    """Whether a live builder is the stub ``make scaffold`` writes, which fails the live test until it is replaced."""
    code = getattr(builder, "__code__", None)
    return code is not None and PLACEHOLDER in code.co_consts


def live_rows(
    accessors: Iterable[str], specs: Mapping[str, Sequence[Mapping[str, Any]]], reasons: Mapping[str, Mapping[str, str]]
) -> list[LiveRow]:
    """One row per wired endpoint, from its spec or its ``LIVE_NOT_COVERED`` reason, sorted by accessor.

    Raises ``CoverageDocError``, one line per problem, when an endpoint has neither, both or two specs, or a spec or
    reason names an accessor that is not wired.
    """
    wired = sorted(accessors)
    problems: list[str] = []
    found: dict[str, list[Mapping[str, Any]]] = {}
    for api, api_specs in specs.items():
        for index, spec in enumerate(api_specs):
            relative = spec.get("accessor")
            if not isinstance(relative, str) or not relative:
                # Name the spec by its id, or its place in the list, since it has no accessor to name.
                label = f"SPECS entry {spec['id']!r}" if spec.get("id") else f"SPECS[{index}]"
                problems.append(f"{LIVE_TESTS[api]}: {label} has no accessor")
                continue
            accessor = f"{api}.{relative}"
            if accessor not in wired:
                problems.append(f"{LIVE_TESTS[api]}: SPECS names {accessor}, which is not a wired endpoint")
            found.setdefault(accessor, []).append(spec)
    excused: dict[str, str] = {}
    for api, api_reasons in reasons.items():
        for relative, reason in api_reasons.items():
            accessor = f"{api}.{relative}"
            if accessor not in wired:
                problems.append(f"{LIVE_TESTS[api]}: LIVE_NOT_COVERED names {accessor}, which is not a wired endpoint")
            excused[accessor] = reason
    rows = []
    for accessor in wired:
        where = LIVE_TESTS[accessor.split(".", 1)[0]]
        accessor_specs = found.get(accessor, [])
        if len(accessor_specs) > 1:
            problems.append(f"{where}: {accessor} has {len(accessor_specs)} live specs; keep one")
        elif accessor_specs and accessor in excused:
            problems.append(f"{where}: {accessor} has a live spec and a LIVE_NOT_COVERED reason; keep one")
        elif accessor_specs:
            rows.append(_spec_row(accessor, accessor_specs[0]))
        elif accessor in excused:
            rows.append(LiveRow(accessor, NOT_APPLICABLE, NOT_APPLICABLE, _cell(excused[accessor])))
        else:
            problems.append(f"{accessor} has no live spec and no reason: add a spec to SPECS, or why it has none to LIVE_NOT_COVERED, in {where}")
    if problems:
        raise CoverageDocError("\n".join(problems))
    return rows


def _spec_row(accessor: str, spec: Mapping[str, Any]) -> LiveRow:
    marks = {kind: YES if kind in spec and not is_placeholder(spec[kind]) else NO for kind in BUILDERS}
    notes = []
    if any(is_placeholder(spec.get(kind)) for kind in BUILDERS):
        notes.append("Scaffolded: the builders are not written yet, so the live test fails.")
    if spec.get("notes"):
        notes.append(str(spec["notes"]))
    return LiveRow(accessor, marks["min"], marks["max"], _cell(" ".join(notes)))


# Rendering


def render(endpoints: Sequence[Wrapped], schemas: Mapping[str, Schema], live: Sequence[LiveRow]) -> str:
    """The whole of COVERAGE.md, ending in a newline; the same inputs always give the same text."""
    lines = [
        "# API coverage",
        "",
        "> **Generated file: do not edit by hand.** `make coverage-doc` (`tools/coverage_doc.py`) writes it from the wired",
        "> endpoints, `api_schemas/` and the live specs; run it after adding or changing an endpoint or a live spec, and",
        "> commit the result. `make coverage-doc-check` (part of `make check` and CI) fails while this file is stale.",
        "",
        "Which Jamf Pro server resources this SDK wraps, and which it doesn't yet. Jamf exposes **two** HTTP APIs (see",
        "[`AGENTS.md`](AGENTS.md)); this SDK wraps a subset of each.",
        "",
        "**How to read this**",
        "",
        "- The endpoints are every `Endpoint` attribute of `ClassicAPI` and `ProAPI`, composites' children included, as",
        "  `tests/contract_test.py` discovers them. The schemas are `api_schemas/`, read through `tools/schemas.py`, with",
        "  `pro-supplement.json`'s probed paths merged into Pro.",
        "- A *resource* is one top-level path group, not an HTTP operation: a schema path's first segment, after the",
        "  `/v{n}` prefix for Pro (`/v1/scripts/{id}` → `scripts`, `/v2/mdm/commands` → `mdm`; an unversioned Pro path",
        "  such as `/preview/computers` → `preview`), and its first segment under `/JSSResource` for Classic",
        "  (`/accounts/userid/{id}` → `accounts`). Every count below counts resources. A resource is *covered* when at",
        "  least one wired endpoint's path is in it, however few of its paths and verbs that endpoint wraps.",
        "- *Methods* are an endpoint's public methods (`name()` is left out); one that sends nothing is marked *(no",
        "  request)*. *Sends to* is what the endpoint really sends, not what the schema lists for its path: the",
        "  generator calls every method with dummy arguments under a stub that records each request instead of sending",
        "  it, the way `tests/contract_test.py` does (both use `tools/introspect.py`), and lists each path some method",
        "  sends to with the verbs sent there. `[options-probe]` marks a path that is only in `pro-supplement.json`, not",
        "  in Jamf's published schema; *not in schema* marks a path, or the verbs, that the schema lacks (the contract",
        "  test fails on those, so they should not appear).",
        "- Jamf ships new resources continuously, so the totals move with each `make schemas`: treat them as an",
        "  order-of-magnitude gauge.",
        "",
        "---",
        "",
        "## Summary",
        "",
        *_summary(endpoints, schemas),
        "",
        "---",
        "",
        "## Classic — covered (`tenant.classic.*`)",
        "",
        "Classic write bodies are **XML strings**.",
        "",
        *_table(
            ("SDK accessor", "Path (`/JSSResource`)", "Methods", "Sends to"),
            ("---", "---", "---", "---"),
            [(_code(e.accessor), _code(e.path), _methods(e), _sends_cell(e, schemas["classic"])) for e in endpoints if e.api == "classic"],
        ),
        "",
        "## Pro — covered (`tenant.pro.*`)",
        "",
        "Pro bodies are **JSON dicts**; a Pro `get_all` paginates and aggregates every page into one response. *Version*",
        "is the `/v{n}` of the paths the methods send to: *per method* when they hit different versions, *none* when",
        "they send to no versioned path.",
        "",
        *_table(
            ("SDK accessor", "Path (`/api`)", "Version", "Methods", "Sends to"),
            ("---", "---", "---", "---", "---"),
            [
                (_code(e.accessor), _code(e.path), _version(e), _methods(e), _sends_cell(e, schemas["pro"]))
                for e in endpoints if e.api == "pro"
            ],
        ),
        "",
        "---",
        "",
        "## Live integration test coverage (min/max)",
        "",
        "Which wired endpoints have live min/max lifecycle tests (`tests/integration/`: create with the required fields",
        "only / with every writable field, then read → update → read → delete against a real tenant; see `AGENTS.md` →",
        "*Quality gates*). A row with ✅/❌ comes from a spec in `SPECS` in `tests/integration/clc_resources_live_test.py`",
        "or `pro_resources_live_test.py`: ✅ where the spec has that builder, ❌ where it has none or still has the",
        "placeholder `make scaffold` writes; *Notes* is the spec's `notes`. An N/A row comes from the module's",
        "`LIVE_NOT_COVERED`, with the reason the endpoint has no spec. Every wired endpoint has one or the other:",
        "`make coverage-doc` refuses an endpoint with neither. Behaviour that is not per resource (lazy auth, one token",
        "for back-to-back calls with the buffer-clamp warning once, parallel pagination, `pro.app_installers.get_all`",
        "paging, hooks over a lifecycle, `close()` invalidating the token) is checked live in",
        "`tests/integration/sdk_behaviour_live_test.py`, which is not in this table.",
        "",
        *_table(
            ("SDK accessor", "API", "Min", "Max", "Notes"),
            ("---", "---", ":-:", ":-:", "---"),
            [(_code(row.accessor), LABELS[row.accessor.split(".", 1)[0]], row.min, row.max, row.notes) for row in live],
        ),
        "",
        "---",
        "",
        "## Not yet covered",
        "",
        "Resources in the schemas that no wired endpoint's path is in. Adding any of these follows `AGENTS.md` → *How to",
        "add an endpoint* (start with `make scaffold`).",
    ]
    for api in ("classic", "pro"):
        missing = not_covered(api, schemas[api], endpoints)
        lines += ["", f"### {LABELS[api]} ({len(missing)})", "", "```", *_wrapped(missing), "```"]
    return "\n".join(lines) + "\n"


def _summary(endpoints: Sequence[Wrapped], schemas: Mapping[str, Schema]) -> list[str]:
    rows = []
    for api in ("classic", "pro"):
        total = len(schema_resources(api, schemas[api]))
        count = len(covered(api, schemas[api], endpoints))
        share = f"~{round(100 * count / total)}%" if total else "n/a"
        wired = sum(1 for endpoint in endpoints if endpoint.api == api)
        rows.append((f"**{LABELS[api]}** (`tenant.{api}.*`)", str(wired), str(count), str(total), share))
    header = ("API", "Endpoints wired", "Resources covered", "Resources in schema", "Rough coverage")
    lines = _table(header, ("---", "--:", "--:", "--:", "--:"), rows)
    extra = supplement_only(schemas["pro"])
    if extra:
        names = ", ".join(_code(name) for name in extra)
        lines += [
            "",
            f"Pro's {len(schema_resources('pro', schemas['pro']))} resources include {len(extra)} whose paths are only in "
            f"`pro-supplement.json` ({names}): the tenant serves those paths, but Jamf's published schema leaves them out.",
        ]
    return lines


def _table(header: Sequence[str], align: Sequence[str], rows: Iterable[Sequence[str]]) -> list[str]:
    return [f"| {' | '.join(header)} |", f"|{'|'.join(align)}|", *(f"| {' | '.join(row)} |" for row in rows)]


def _code(text: str) -> str:
    return f"`{text}`"


def _cell(text: str) -> str:
    # A table cell is one line, and a bare pipe would end it.
    return " ".join(text.split()).replace("|", "\\|")


def _methods(endpoint: Wrapped) -> str:
    return ", ".join(_code(method) + ("" if requests else " (no request)") for method, requests in endpoint.requests.items()) or "none"


def _version(endpoint: Wrapped) -> str:
    if endpoint.version:
        return endpoint.version
    return "per method" if endpoint.versions else "none"


def _sends_cell(endpoint: Wrapped, schema: Schema) -> str:
    parts = []
    for found in sent_paths(endpoint, schema):
        text = f"{_code(found.path)} {' '.join(verb.upper() for verb in found.sent)}"
        if found.schema is None:
            text += " *not in schema*"
        elif absent := [verb for verb in found.sent if verb not in found.schema]:
            text += f" *not in schema: {' '.join(verb.upper() for verb in absent)}*"
        parts.append(text + (" [options-probe]" if found.probed else ""))
    return "; ".join(parts) or "no request"


def _wrapped(names: Sequence[str]) -> list[str]:
    if not names:
        return ["(none)"]
    return textwrap.wrap(", ".join(names), width=WRAP, break_long_words=False, break_on_hyphens=False)


# Generating and checking


def _import_from(root: Path, name: str) -> ModuleType:
    """Import ``name`` and check it is ``root``'s own, so the file describes the code in the repo it is written to."""
    module = importlib.import_module(name)
    _require_under(root, module)
    return module


def _require_under(root: Path, module: ModuleType) -> None:
    location = Path(module.__file__ or "").resolve()
    if not location.is_relative_to(root):
        raise CoverageDocError(f"{module.__name__} is imported from {location}, not from {root}: run the generator in {root}")


def generate(root: Path) -> str:
    """COVERAGE.md for the repo at ``root``, from its endpoints, ``api_schemas/`` and live specs."""
    root = root.resolve()
    _require_under(root, jamfpy)
    specs, reasons = load_live(root)
    apis = stub_apis()
    endpoints = [describe(accessor, endpoint, apis) for accessor, endpoint in discover(apis).items()]
    schemas = {"classic": load_classic(root / SCHEMA_DIR), "pro": load_pro(root / SCHEMA_DIR)}
    live = live_rows([endpoint.accessor for endpoint in endpoints], specs, reasons)
    return render(endpoints, schemas, live)


def stale(text: str, file: Path) -> str | None:
    """``None`` when ``file`` holds exactly ``text``; otherwise a unified diff from the file to ``text``."""
    current = file.read_bytes().decode("utf-8") if file.exists() else ""
    if current == text:
        return None
    diff = difflib.unified_diff(
        current.splitlines(), text.splitlines(), fromfile=f"{file.name} (committed)", tofile=f"{file.name} (generated)", lineterm=""
    )
    return "\n".join(diff) + "\n"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m tools.coverage_doc", description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument(
        "--root", type=Path, default=REPO_ROOT,
        help="the repo whose COVERAGE.md to write or check (default: this one); its jamfpy and live modules must be the ones imported",
    )
    parser.add_argument("--check", action="store_true", help="write nothing; exit 1 with a diff when COVERAGE.md is stale")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI; returns the exit status. A problem prints one line per problem on stderr and exits 1."""
    args = _parser().parse_args(argv)
    target = args.root.resolve() / COVERAGE_FILE
    try:
        text = generate(args.root)
    except (CoverageDocError, SchemaError) as exc:
        for line in str(exc).splitlines():
            print(f"coverage-doc: {line}", file=sys.stderr)
        return 1
    diff = stale(text, target)
    if diff is None:
        print(f"{COVERAGE_FILE} is up to date")
        return 0
    if args.check:
        sys.stdout.write(diff)
        # A piped stdout is block-buffered: flush so the hint follows the diff in a combined log such as CI's.
        sys.stdout.flush()
        print(f"coverage-doc: {COVERAGE_FILE} is stale; run make coverage-doc", file=sys.stderr)
        return 1
    target.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {COVERAGE_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
