"""Unit tests for tools/coverage_doc.py: endpoint introspection, resource counting, the live table and its refusals, --check.

The pure functions run on fixture schemas, fixture endpoints and fixture specs. The real repo is used only for smoke
tests: discovery against the contract test's, the real endpoints' recorded requests, the real live modules, and
whole-file generation (deterministic, with no timestamp). The recording itself is tested in tools_introspect_test.py.
"""
# pylint: disable=missing-function-docstring,redefined-outer-name,too-many-lines
import re
import types
from pathlib import Path

import pytest
from contract_test import DISCOVERED, EXPECTED_ENDPOINT_COUNT
from requests import Request, Response

from jamfpy.endpoints.models import Endpoint
from tools import coverage_doc, scaffold
from tools.coverage_doc import CoverageDocError, LiveRow, SentPath, Wrapped
from tools.introspect import Sent
from tools.schemas import PROBE_SOURCE, SOURCE_KEY

REPO_ROOT = Path(__file__).resolve().parent.parent
CRUD = ("create", "delete_by_id", "get_all", "get_by_id", "update_by_id")
ALL_FOUR = ["delete", "get", "post", "put"]
PROBED = {SOURCE_KEY: PROBE_SOURCE}
CLASSIC_LIVE = "tests/integration/clc_resources_live_test.py"
PRO_LIVE = "tests/integration/pro_resources_live_test.py"

PRO = {"paths": {
    "/v1/things": {"get": {}, "post": {}},
    "/v1/things/{id}": {"get": {}, "put": {}, "delete": {}},
    "/v1/things/{id}/history": {"get": {}},
    "/v2/things": {"get": {}},
    "/v1/actions/run": {"post": {}},
    "/v2/actions/run": {"get": {}, "post": {}},
    "/v1/drafts": {"post": {}},
    "/preview/computers": {"get": {}},
    "/auth": {"post": {}},
    "/v1/probed/items": {"get": {}, **PROBED},
    "/v1/mixed": {"get": {}},
    "/v1/mixed/extra": {"get": {}, **PROBED},
    # A different parameter name from the {id} the endpoints' paths are normalised to.
    "/v1/named/{thingName}": {"get": {}},
}}
CLASSIC = {"paths": {
    "/buildings": {"get": {}},
    "/buildings/id/{id}": {"delete": {}, "get": {}, "post": {}, "put": {}},
    "/buildings/name/{name}": {"get": {}},
    "/accounts": {"get": {}},
    "/accounts/userid/{id}": {"delete": {}, "get": {}, "post": {}, "put": {}},
    "/printers": {"get": {}},
}}
SCHEMAS = {"classic": CLASSIC, "pro": PRO}


def sends(**methods):
    """The ``requests`` of a ``Wrapped``: each method's ``(verb, path)`` pairs; a method given none sends nothing."""
    return {name: tuple(Sent(verb, path) for verb, path in pairs) for name, pairs in sorted(methods.items())}


def classic_crud(base, by_id):
    """What ``ClassicEndpoint`` sends: the collection read, and everything else by id (create posts to id 0)."""
    item = f"{by_id}/{{id}}"
    return sends(
        create=[("post", item)], delete_by_id=[("delete", item)], get_all=[("get", base)],
        get_by_id=[("get", item)], update_by_id=[("put", item)],
    )


def pro_crud(base):
    """What ``ProEndpoint`` sends under ``base``, a versioned path."""
    item = f"{base}/{{id}}"
    return sends(
        create=[("post", base)], delete_by_id=[("delete", item)], get_all=[("get", base)],
        get_by_id=[("get", item)], update_by_id=[("put", item)],
    )


THINGS = Wrapped("pro.things", "pro", "/things", sends(create=[("post", "/v1/things")], get_all=[("get", "/v1/things")]))
ACTIONS = Wrapped(
    "pro.actions", "pro", "/actions/run",
    sends(send=[("post", "/v1/actions/run")], send_v2=[("post", "/v2/actions/run"), ("get", "/v2/actions/run")]),
)
BUILDINGS = Wrapped("classic.buildings", "classic", "/buildings", classic_crud("/buildings", "/buildings/id"))
USERS = Wrapped("classic.accounts.users", "classic", "/accounts", classic_crud("/accounts", "/accounts/userid"))
ENDPOINTS = [BUILDINGS, USERS, ACTIONS, THINGS]


def builder(name):
    return {"name": name}


def placeholder():
    """The builder ``make scaffold`` writes, made from the scaffolder's own text: its code object, without evaluating it."""
    module = compile(scaffold.FILL_IN, "<fill-in>", "eval")
    function_code = next(const for const in module.co_consts if isinstance(const, types.CodeType))
    return types.FunctionType(function_code, {"pytest": pytest})


class Mixed(Endpoint):
    """A fixture endpoint that sends to two Pro versions, twice to one of them, and sometimes to none."""

    _uri = "/mixed"

    def one(self) -> Response:
        return self._api.do(Request("GET", url=self._api.url("1") + self._uri))

    def two(self, target_id: int) -> Response:
        self._api.do(Request("DELETE", url=self._api.url("2") + f"{self._uri}/{target_id}"))
        return self._api.do(Request("POST", url=self._api.url("2") + self._uri, json={}))

    def silent(self) -> None:
        """Sends nothing."""


class Odd(Endpoint):
    """A fixture endpoint with a parameter the dummy-argument rules have no value for."""

    _uri = "/odd"

    def lopsided(self, ratio: float) -> Response:
        return self._api.do(Request("GET", url=self._api.url("1") + f"{self._uri}/{ratio}"))


# Introspection


def test_discovers_every_endpoint_the_contract_test_finds_and_sends_nothing(mocked_responses):
    found = coverage_doc.discover(coverage_doc.stub_apis())

    assert set(found) == set(DISCOVERED)
    assert len(found) == EXPECTED_ENDPOINT_COUNT
    assert list(found) == sorted(found)
    # Nothing is registered, so any request would have raised; and none was recorded.
    assert not mocked_responses.calls


@pytest.fixture(scope="module")
def real():
    apis = coverage_doc.stub_apis()
    return {accessor: coverage_doc.describe(accessor, endpoint, apis) for accessor, endpoint in coverage_doc.discover(apis).items()}


@pytest.mark.parametrize(("accessor", "methods", "version", "sent"), [
    ("classic.buildings", CRUD, None, {"/buildings": ["get"], "/buildings/id/{id}": ["delete", "get", "post", "put"]}),
    ("classic.accounts.users", CRUD, None, {"/accounts": ["get"], "/accounts/userid/{id}": ["delete", "get", "post", "put"]}),
    ("classic.accounts", ("get_all",), None, {"/accounts": ["get"]}),
    ("pro.scripts", CRUD, "v1", {"/v1/scripts": ["get", "post"], "/v1/scripts/{id}": ["delete", "get", "put"]}),
    # No get_all: the collection is POST-only in the schema.
    ("pro.dock_items", ("create", "delete_by_id", "get_by_id", "update_by_id"), "v1",
     {"/v1/dock-items": ["post"], "/v1/dock-items/{id}": ["delete", "get", "put"]}),
])
def test_describe_records_the_methods_and_the_requests_they_send(real, accessor, methods, version, sent):
    described = real[accessor]

    assert described.methods == methods
    assert described.version == version
    assert described.sent == sent


def test_the_real_mdm_endpoint_sends_only_a_v2_post(real):
    mdm = real["pro.mdm"]

    # The schema has /v1/mdm/commands GET and /v2/mdm/commands GET; the endpoint's own _uri names neither version.
    assert mdm.sent == {"/v2/mdm/commands": ["post"]}
    assert (mdm.versions, mdm.version, mdm.path, mdm.resource) == (["v2"], "v2", "/v2/mdm/commands", "mdm")
    assert {"send_command", "lock_device"} <= set(mdm.methods)
    assert "name" not in mdm.methods
    assert list(mdm.methods) == sorted(mdm.methods)


def test_every_real_method_sends_a_request(real):
    assert len(real) == EXPECTED_ENDPOINT_COUNT
    assert [(accessor, method) for accessor, row in real.items() for method, sent in row.requests.items() if not sent] == []


def test_public_methods_leave_out_name_private_names_and_nested_endpoints(real):
    assert real["classic.accounts"].methods == ("get_all",)
    assert all(not method.startswith("_") and method != "name" for row in real.values() for method in row.methods)


def test_describe_a_fixture_endpoint_that_sends_to_two_versions_and_sometimes_to_none():
    apis = coverage_doc.stub_apis()

    mixed = coverage_doc.describe("pro.mixed", Mixed(apis["pro"]), apis)

    assert mixed.requests == {
        "one": (Sent("get", "/v1/mixed"),),
        "silent": (),
        "two": (Sent("delete", "/v2/mixed/{id}"), Sent("post", "/v2/mixed")),
    }
    assert mixed.sent == {"/v1/mixed": ["get"], "/v2/mixed": ["post"], "/v2/mixed/{id}": ["delete"]}
    assert (mixed.versions, mixed.version, mixed.path) == (["v1", "v2"], None, "/mixed")


def test_describe_names_the_accessor_when_a_parameter_has_no_dummy_value():
    apis = coverage_doc.stub_apis()

    with pytest.raises(CoverageDocError, match=r"^pro\.odd: no dummy value for parameter 'ratio' annotated <class 'float'>: add one to"):
        coverage_doc.describe("pro.odd", Odd(apis["pro"]), apis)


def test_wrapped_version_path_and_resource():
    assert (THINGS.versions, THINGS.version, THINGS.path, THINGS.resource) == (["v1"], "v1", "/v1/things", "things")
    assert (ACTIONS.versions, ACTIONS.version, ACTIONS.path, ACTIONS.resource) == (["v1", "v2"], None, "/actions/run", "actions")
    assert (BUILDINGS.versions, BUILDINGS.version, BUILDINGS.path, BUILDINGS.resource) == ([], None, "/buildings", "buildings")
    # Ten sorts after nine: by number, not by text.
    numbered = Wrapped("pro.n", "pro", "/n", sends(a=[("get", "/v10/n")], b=[("get", "/v9/n")]))
    assert numbered.versions == ["v9", "v10"]
    # An unversioned Pro path has no version, and the endpoint is not "per method".
    preview = Wrapped("pro.preview", "pro", "/preview/computers", sends(a=[("get", "/preview/computers")]))
    assert (preview.versions, preview.path) == ([], "/preview/computers")


# Resources and counts


@pytest.mark.parametrize(("api", "path", "expected"), [
    ("pro", "/v1/scripts/{id}", "scripts"),
    ("pro", "/v2/mdm/commands", "mdm"),
    ("pro", "/preview/computers", "preview"),
    ("pro", "/auth", "auth"),
    ("pro", "/v1", "v1"),
    ("classic", "/accounts/userid/{id}", "accounts"),
    ("classic", "/v2/things", "v2"),
])
def test_resource_is_the_first_segment_after_the_pro_version(api, path, expected):
    assert coverage_doc.resource(api, path) == expected


def test_schema_resources_are_the_sorted_top_level_groups():
    assert coverage_doc.schema_resources("pro", PRO) == ["actions", "auth", "drafts", "mixed", "named", "preview", "probed", "things"]
    assert coverage_doc.schema_resources("classic", CLASSIC) == ["accounts", "buildings", "printers"]


def test_supplement_only_needs_every_path_of_the_resource_probed():
    assert coverage_doc.supplement_only(PRO) == ["probed"]


def test_supplement_only_lists_every_such_resource_sorted_whatever_the_schema_order():
    schema = {"paths": {
        "/v1/zeta": {"get": {}, **PROBED},
        "/v1/things": {"get": {}},
        "/v2/alpha/items": {"get": {}, **PROBED},
        "/v1/alpha": {"get": {}, **PROBED},
        "/v1/partial": {"get": {}, **PROBED},
        "/v1/partial/more": {"get": {}},
    }}

    assert coverage_doc.supplement_only(schema) == ["alpha", "zeta"]


def test_covered_and_not_covered_split_the_schema_resources():
    endpoints = [*ENDPOINTS, Wrapped("pro.gone", "pro", "/gone", sends())]

    assert coverage_doc.covered("pro", PRO, endpoints) == ["actions", "things"]
    assert coverage_doc.not_covered("pro", PRO, endpoints) == ["auth", "drafts", "mixed", "named", "preview", "probed"]
    assert coverage_doc.covered("classic", CLASSIC, endpoints) == ["accounts", "buildings"]
    assert coverage_doc.not_covered("classic", CLASSIC, endpoints) == ["printers"]


# Sent paths per endpoint


@pytest.mark.parametrize(("endpoint", "expected"), [
    # Only what the methods send: the schema's other verbs and paths (POST on /v1/things/{id}...) stay out.
    (THINGS, [SentPath("/v1/things", ["get", "post"], ["get", "post"], False)]),
    (Wrapped("pro.things", "pro", "/things", pro_crud("/v1/things")),
     [SentPath("/v1/things", ["get", "post"], ["get", "post"], False),
      SentPath("/v1/things/{id}", ["delete", "get", "put"], ["delete", "get", "put"], False)]),
    (ACTIONS, [SentPath("/v1/actions/run", ["post"], ["post"], False), SentPath("/v2/actions/run", ["get", "post"], ["get", "post"], False)]),
    # POST only, though the schema also has GET: the sent verbs are shown, not the schema's.
    (Wrapped("pro.actions", "pro", "/actions/run", sends(send=[("post", "/v2/actions/run")])),
     [SentPath("/v2/actions/run", ["post"], ["get", "post"], False)]),
    (Wrapped("pro.probed", "pro", "/probed/items", sends(get_all=[("get", "/v1/probed/items")])),
     [SentPath("/v1/probed/items", ["get"], ["get"], True)]),
    (Wrapped("pro.mixed", "pro", "/mixed", sends(a=[("get", "/v1/mixed")], b=[("get", "/v1/mixed/extra")])),
     [SentPath("/v1/mixed", ["get"], ["get"], False), SentPath("/v1/mixed/extra", ["get"], ["get"], True)]),
    # A schema parameter named {thingName} matches the {id} a sent path is normalised to.
    (Wrapped("pro.named", "pro", "/named", sends(get_by_id=[("get", "/v1/named/{id}")])),
     [SentPath("/v1/named/{id}", ["get"], ["get"], False)]),
    (BUILDINGS, [SentPath("/buildings", ["get"], ["get"], False), SentPath("/buildings/id/{id}", ALL_FOUR, ALL_FOUR, False)]),
    (USERS, [SentPath("/accounts", ["get"], ["get"], False), SentPath("/accounts/userid/{id}", ALL_FOUR, ALL_FOUR, False)]),
    # A path or a verb the schema lacks is listed, not dropped.
    (Wrapped("classic.printers", "classic", "/printers", classic_crud("/printers", "/printers/id")),
     [SentPath("/printers", ["get"], ["get"], False), SentPath("/printers/id/{id}", ALL_FOUR, None, False)]),
    (Wrapped("pro.drafts", "pro", "/drafts", sends(get_all=[("get", "/v1/drafts")])), [SentPath("/v1/drafts", ["get"], ["post"], False)]),
    (Wrapped("pro.gone", "pro", "/gone", sends(get_all=[("get", "/v1/gone")])), [SentPath("/v1/gone", ["get"], None, False)]),
    (Wrapped("pro.silent", "pro", "/silent", sends(quiet=[])), []),
], ids=lambda value: value.accessor if isinstance(value, Wrapped) else "")
def test_sent_paths_list_the_paths_sent_to_with_the_verbs_sent_and_the_schemas(endpoint, expected):
    assert coverage_doc.sent_paths(endpoint, SCHEMAS[endpoint.api]) == expected


# Live table


def test_live_rows_from_specs_and_reasons():
    specs = {
        "classic": [{"id": "buildings", "accessor": "buildings", "min": builder, "max": builder}],
        "pro": [
            {"id": "things", "accessor": "things", "min": builder},
            {"id": "noted", "accessor": "noted", "min": builder, "max": builder, "notes": "Sent | not\n asserted"},
        ],
    }
    reasons = {"classic": {"accounts": "Parent only"}, "pro": {"actions": "Verb endpoint"}}
    accessors = ["pro.things", "classic.buildings", "pro.noted", "classic.accounts", "pro.actions"]

    assert coverage_doc.live_rows(accessors, specs, reasons) == [
        LiveRow("classic.accounts", "N/A", "N/A", "Parent only"),
        LiveRow("classic.buildings", "✅", "✅", ""),
        LiveRow("pro.actions", "N/A", "N/A", "Verb endpoint"),
        LiveRow("pro.noted", "✅", "✅", "Sent \\| not asserted"),
        LiveRow("pro.things", "✅", "❌", ""),
    ]


def test_a_scaffolded_placeholder_spec_is_not_counted_as_covered():
    specs = {"pro": [{"id": "things", "accessor": "things", "min": placeholder(), "max": placeholder(), "notes": "Check root."}]}

    assert coverage_doc.live_rows(["pro.things"], specs, {}) == [
        LiveRow("pro.things", "❌", "❌", "Scaffolded: the builders are not written yet, so the live test fails. Check root."),
    ]


def test_is_placeholder_recognises_only_the_scaffolded_builder():
    assert coverage_doc.is_placeholder(placeholder())
    assert not coverage_doc.is_placeholder(builder)
    assert not coverage_doc.is_placeholder(lambda n: {"name": n})
    assert not coverage_doc.is_placeholder(None)


@pytest.mark.parametrize(("accessors", "specs", "reasons", "message"), [
    (["pro.things"], {}, {},
     f"pro.things has no live spec and no reason: add a spec to SPECS, or why it has none to LIVE_NOT_COVERED, in {PRO_LIVE}"),
    (["pro.things"], {"pro": [{"accessor": "things", "min": builder}, {"accessor": "ghost", "min": builder}]}, {},
     f"{PRO_LIVE}: SPECS names pro.ghost, which is not a wired endpoint"),
    (["classic.buildings"], {"classic": [{"accessor": "buildings", "min": builder}]}, {"classic": {"ghost": "gone"}},
     f"{CLASSIC_LIVE}: LIVE_NOT_COVERED names classic.ghost, which is not a wired endpoint"),
    (["pro.things"], {"pro": [{"accessor": "things", "min": builder}]}, {"pro": {"things": "why"}},
     f"{PRO_LIVE}: pro.things has a live spec and a LIVE_NOT_COVERED reason; keep one"),
    (["pro.things"], {"pro": [{"accessor": "things", "min": builder}, {"accessor": "things", "min": builder}]}, {},
     f"{PRO_LIVE}: pro.things has 2 live specs; keep one"),
    # No accessor to name: the spec is named by its id, or by its place in the list when it has none.
    (["pro.things"], {"pro": [{"accessor": "things", "min": builder}, {"id": "orphan", "min": builder}]}, {},
     f"{PRO_LIVE}: SPECS entry 'orphan' has no accessor"),
    (["classic.buildings"], {"classic": [{"min": builder}, {"accessor": "buildings", "min": builder}]}, {},
     f"{CLASSIC_LIVE}: SPECS[0] has no accessor"),
    (["pro.things"], {"pro": [{"id": "blank", "accessor": "", "min": builder}, {"accessor": "things", "min": builder}]}, {},
     f"{PRO_LIVE}: SPECS entry 'blank' has no accessor"),
], ids=["neither", "unwired-spec", "unwired-reason", "both", "two-specs", "no-accessor-by-id", "no-accessor-by-index", "empty-accessor"])
def test_live_rows_refuse_with_one_line_naming_the_accessor(accessors, specs, reasons, message):
    with pytest.raises(CoverageDocError) as raised:
        coverage_doc.live_rows(accessors, specs, reasons)

    assert str(raised.value) == message


def test_live_rows_report_every_problem_one_per_line():
    with pytest.raises(CoverageDocError) as raised:
        coverage_doc.live_rows(["classic.printers", "pro.things"], {}, {})

    assert [line.split(" ", 1)[0] for line in str(raised.value).splitlines()] == ["classic.printers", "pro.things"]


def test_real_live_modules_import_without_a_tenant_and_give_specs_and_reasons(monkeypatch):
    for name in ("JAMFPRO_INSTANCE_FQDN", "JAMFPRO_CLIENT_ID", "JAMFPRO_CLIENT_SECRET"):
        monkeypatch.delenv(name, raising=False)

    specs, reasons = coverage_doc.load_live(REPO_ROOT)

    # A subset: adding a reason for a new endpoint must not break this test.
    assert set(reasons) == {"pro", "classic"}
    assert "mdm" in reasons["pro"] and "accounts" in reasons["classic"]
    assert "notes" in next(spec for spec in specs["pro"] if spec["accessor"] == "app_installers")
    assert {"buildings", "accounts.users", "accounts.groups"} <= {spec["accessor"] for spec in specs["classic"]}


@pytest.mark.parametrize(("module", "message"), [
    (types.SimpleNamespace(), f"{PRO_LIVE} has no SPECS list"),
    (types.SimpleNamespace(SPECS={"accessor": "things"}), f"{PRO_LIVE} has no SPECS list"),
    (types.SimpleNamespace(SPECS=[]), f"{PRO_LIVE} has no LIVE_NOT_COVERED dict of accessor to reason"),
    (types.SimpleNamespace(SPECS=[], LIVE_NOT_COVERED=["mdm"]), f"{PRO_LIVE} has no LIVE_NOT_COVERED dict of accessor to reason"),
    (types.SimpleNamespace(SPECS=[{}, "not a dict"], LIVE_NOT_COVERED={}), f"{PRO_LIVE}: SPECS[1] is not a dict"),
    # An empty reason, a whitespace-only one and a non-string one each name the accessor, one line each.
    (types.SimpleNamespace(SPECS=[], LIVE_NOT_COVERED={"mdm": ""}),
     f"{PRO_LIVE}: LIVE_NOT_COVERED has no reason for pro.mdm: give a string with something in it"),
    (types.SimpleNamespace(SPECS=[], LIVE_NOT_COVERED={"mdm": " \t\n ", "ok": "why", "none": None}),
     f"{PRO_LIVE}: LIVE_NOT_COVERED has no reason for pro.mdm: give a string with something in it\n"
     f"{PRO_LIVE}: LIVE_NOT_COVERED has no reason for pro.none: give a string with something in it"),
])
def test_load_live_refuses_a_module_without_its_lists_or_with_a_blank_reason(monkeypatch, module, message):
    good = types.SimpleNamespace(SPECS=[], LIVE_NOT_COVERED={})
    monkeypatch.setattr(coverage_doc, "_import_from", lambda root, name: module if name.endswith("pro_resources_live_test") else good)

    with pytest.raises(CoverageDocError) as raised:
        coverage_doc.load_live(REPO_ROOT)

    assert str(raised.value) == message


# Rendering


def test_render_on_fixtures():
    live = [LiveRow(e.accessor, "✅", "❌", "") for e in sorted(ENDPOINTS, key=lambda e: e.accessor)]

    text = coverage_doc.render(sorted(ENDPOINTS, key=lambda e: e.accessor), SCHEMAS, live)

    assert text == coverage_doc.render(sorted(ENDPOINTS, key=lambda e: e.accessor), SCHEMAS, live)
    lines = text.splitlines()
    assert "| **Classic** (`tenant.classic.*`) | 2 | 2 | 3 | ~67% |" in lines
    assert "| **Pro** (`tenant.pro.*`) | 2 | 2 | 8 | ~25% |" in lines
    assert any(line.startswith("Pro's 8 resources include 1 whose paths are only in `pro-supplement.json` (`probed`)") for line in lines)
    assert "| `pro.things` | `/v1/things` | v1 | `create`, `get_all` | `/v1/things` GET POST |" in lines
    assert "| `pro.actions` | `/actions/run` | per method | `send`, `send_v2` | `/v1/actions/run` POST; `/v2/actions/run` GET POST |" in lines
    assert ("| `classic.accounts.users` | `/accounts` | `create`, `delete_by_id`, `get_all`, `get_by_id`, `update_by_id` | "
            "`/accounts` GET; `/accounts/userid/{id}` DELETE GET POST PUT |") in lines
    assert "| `classic.buildings` | Classic | ✅ | ❌ |  |" in lines
    assert lines[lines.index("### Classic (1)") + 2: lines.index("### Classic (1)") + 5] == ["```", "printers", "```"]
    assert lines[lines.index("### Pro (6)") + 3] == "auth, drafts, mixed, named, preview, probed"
    assert text.endswith("```\n") and not text.endswith("\n\n")


def test_render_marks_probed_missing_and_unsent_paths_and_empty_lists():
    endpoints = [
        Wrapped("classic.printers", "classic", "/printers", classic_crud("/printers", "/printers/id")),
        Wrapped("classic.quiet", "classic", "/quiet", sends(close=[])),
        Wrapped("pro.probed", "pro", "/probed/items", sends(get_all=[("get", "/v1/probed/items")])),
        Wrapped("pro.verbs", "pro", "/verbs", sends(get_all=[("get", "/v1/verbs"), ("delete", "/v1/verbs")], silent=[])),
        Wrapped("pro.unversioned", "pro", "/preview/computers", sends(get_all=[("get", "/preview/computers")])),
        Wrapped("pro.nothing", "pro", "/nothing", {}),
    ]
    schemas = {
        "classic": {"paths": {"/printers": {"get": {}}, "/quiet": {"get": {}}}},
        "pro": {"paths": {"/v1/probed/items": {"get": {}, **PROBED}, "/v1/verbs": {"get": {}}, "/preview/computers": {"get": {}}}},
    }

    lines = coverage_doc.render(endpoints, schemas, []).splitlines()

    assert ("| `classic.printers` | `/printers` | `create`, `delete_by_id`, `get_all`, `get_by_id`, `update_by_id` | "
            "`/printers` GET; `/printers/id/{id}` DELETE GET POST PUT *not in schema* |") in lines
    assert "| `classic.quiet` | `/quiet` | `close` (no request) | no request |" in lines
    assert "| `pro.probed` | `/v1/probed/items` | v1 | `get_all` | `/v1/probed/items` GET [options-probe] |" in lines
    assert "| `pro.verbs` | `/v1/verbs` | v1 | `get_all`, `silent` (no request) | `/v1/verbs` DELETE GET *not in schema: DELETE* |" in lines
    assert "| `pro.unversioned` | `/preview/computers` | none | `get_all` | `/preview/computers` GET |" in lines
    assert "| `pro.nothing` | `/nothing` | none | none | no request |" in lines
    assert lines.count("(none)") == 2


def test_the_summary_names_every_supplement_only_resource_and_says_nothing_without_any():
    endpoints = [Wrapped("pro.things", "pro", "/things", sends(get_all=[("get", "/v1/things")]))]
    with_two = {"paths": {"/v1/zeta": {"get": {}, **PROBED}, "/v1/alpha": {"get": {}, **PROBED}, "/v1/things": {"get": {}}}}
    without = {"paths": {"/v1/things": {"get": {}}, "/v1/alpha": {"get": {}}}}

    two = coverage_doc.render(endpoints, {"classic": CLASSIC, "pro": with_two}, []).splitlines()
    none = coverage_doc.render(endpoints, {"classic": CLASSIC, "pro": without}, []).splitlines()

    assert (
        "Pro's 3 resources include 2 whose paths are only in `pro-supplement.json` (`alpha`, `zeta`): "
        "the tenant serves those paths, but Jamf's published schema leaves them out."
    ) in two
    assert not any(line.startswith("Pro's ") for line in none)
    assert "| **Pro** (`tenant.pro.*`) | 1 | 1 | 2 | ~50% |" in none


# The real repo, end to end


@pytest.fixture(scope="module")
def generated():
    return coverage_doc.generate(REPO_ROOT)


def test_generate_is_deterministic(generated):
    assert coverage_doc.generate(REPO_ROOT) == generated


def test_generated_file_has_every_endpoint_in_a_covered_row_and_a_live_row(generated):
    for accessor in DISCOVERED:
        assert generated.count(f"| `{accessor}` |") == 2, accessor


def test_generated_file_has_no_timestamp_and_one_final_newline(generated):
    assert not re.search(r"\d{4}-\d{2}-\d{2}|\b\d{1,2}:\d{2}\b", generated)
    assert generated.endswith("\n") and not generated.endswith("\n\n")
    assert "do not edit by hand" in generated and "make coverage-doc" in generated


def test_generate_refuses_a_root_whose_code_is_not_the_code_imported(tmp_path):
    with pytest.raises(CoverageDocError, match=r"^jamfpy is imported from .*, not from .*: run the generator in "):
        coverage_doc.generate(tmp_path)


def test_main_fails_with_one_line_naming_an_endpoint_without_spec_or_reason(monkeypatch, capsys):
    specs, reasons = coverage_doc.load_live(REPO_ROOT)
    del reasons["pro"]["mdm"]
    monkeypatch.setattr(coverage_doc, "load_live", lambda root: (specs, reasons))

    assert coverage_doc.main(["--check"]) == 1

    out, err = capsys.readouterr()
    assert out == ""
    assert err == (
        "coverage-doc: pro.mdm has no live spec and no reason: add a spec to SPECS, or why it has none to LIVE_NOT_COVERED, "
        f"in {PRO_LIVE}\n"
    )


# --check and writing


@pytest.fixture
def fixed(monkeypatch):
    """``generate`` returning fixed text, so the CLI's write and check can run against a tmp root."""
    monkeypatch.setattr(coverage_doc, "generate", lambda root: "one\ntwo\n")


@pytest.mark.usefixtures("fixed")
def test_check_exits_0_when_the_file_is_current(tmp_path, capsys):
    (tmp_path / "COVERAGE.md").write_text("one\ntwo\n", encoding="utf-8")

    assert coverage_doc.main(["--check", "--root", str(tmp_path)]) == 0

    assert capsys.readouterr().out == "COVERAGE.md is up to date\n"


@pytest.mark.usefixtures("fixed")
def test_check_exits_1_with_a_diff_and_a_hint_when_one_line_differs(tmp_path, capsys):
    target = tmp_path / "COVERAGE.md"
    target.write_text("one\nTWO\n", encoding="utf-8")

    assert coverage_doc.main(["--check", "--root", str(tmp_path)]) == 1

    out, err = capsys.readouterr()
    assert out.splitlines()[:2] == ["--- COVERAGE.md (committed)", "+++ COVERAGE.md (generated)"]
    assert "-TWO" in out.splitlines() and "+two" in out.splitlines()
    assert err == "coverage-doc: COVERAGE.md is stale; run make coverage-doc\n"
    assert target.read_text(encoding="utf-8") == "one\nTWO\n"


@pytest.mark.usefixtures("fixed")
def test_check_exits_1_when_the_file_is_missing(tmp_path, capsys):
    assert coverage_doc.main(["--check", "--root", str(tmp_path)]) == 1

    assert "+one" in capsys.readouterr().out.splitlines()
    assert not (tmp_path / "COVERAGE.md").exists()


@pytest.mark.usefixtures("fixed")
def test_write_then_rerun_leaves_the_file_unchanged(tmp_path, capsys):
    assert coverage_doc.main(["--root", str(tmp_path)]) == 0
    assert (tmp_path / "COVERAGE.md").read_bytes() == b"one\ntwo\n"
    assert coverage_doc.main(["--root", str(tmp_path)]) == 0

    assert capsys.readouterr().out == "wrote COVERAGE.md\nCOVERAGE.md is up to date\n"


def test_stale_is_none_only_for_identical_bytes(tmp_path):
    target = tmp_path / "COVERAGE.md"
    target.write_bytes(b"one\ntwo")

    assert coverage_doc.stale("one\ntwo", target) is None
    assert coverage_doc.stale("one\ntwo\n", target) is not None
