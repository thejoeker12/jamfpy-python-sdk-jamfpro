"""Unit tests for tools/scaffold.py: the shape rules, each refusal, the files it generates and the all-or-nothing write.

Every test scaffolds into a tmp tree that mimics the repo layout (a client.py with its import blocks and two
``__init__``s, a clc_endpoints.py with two classes, the live modules' ``SPECS``, contract_test.py's count) over small
fixture schemas; none reads or writes the real tree. The generated tests are also run, against the real SDK stack and
the ``responses`` harness, with the generated endpoint attached to the ``pro_api`` / ``classic_api`` fixtures.
"""
# pylint: disable=missing-function-docstring,redefined-outer-name,protected-access,too-many-lines
import ast
import importlib.util
import inspect
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from jamfpy.endpoints.models import Endpoint, ProEndpoint
from tools import scaffold

REPO_ROOT = Path(__file__).resolve().parent.parent

ID = [{"name": "id", "in": "path", "required": True, "schema": {"type": "string"}}]
JSON_BODY = {"requestBody": {"required": True, "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Thing"}}}}}


def body(content_type, schema=None):
    return {"requestBody": {"content": {content_type: {"schema": schema or {"type": "object"}}}}}


def crud(*verbs):
    return {"parameters": ID, **{verb: (JSON_BODY if verb == "put" else {}) for verb in verbs}}


PAGING = [{"name": "page", "in": "query", "schema": {"type": "integer"}}, {"name": "page-size", "in": "query", "schema": {"type": "integer"}}]
PAGED = {"parameters": PAGING}
# Posts JSON on the wire in the SDK's eyes: a Classic body that is not XML.
JSON_ONLY_POST = {"consumes": ["application/json"], "parameters": [{"name": "thing", "in": "body", "schema": {"type": "object"}}]}


def ok(schema):
    """A collection GET whose 200 response is ``schema``, as JSON."""
    return {"responses": {"200": {"content": {"application/json": {"schema": schema}}}}}


PRO = {
    "openapi": "3.0.1",
    "paths": {
        "/v1/widgets": {"get": PAGED, "post": JSON_BODY},
        "/v1/widgets/{id}": {**crud("get", "put", "delete"), "patch": {}},
        # The three signals that a collection GET is paginated, and the shapes that are not.
        "/v1/pathlevel": {"parameters": PAGING, "get": {}},
        "/v1/pathlevel/{id}": crud("get"),
        "/v1/enveloped": {"get": ok({"$ref": "#/components/schemas/Envelope"})},
        "/v1/enveloped/{id}": crud("get"),
        "/v1/lists": {"get": ok({"type": "array", "items": {}})},
        "/v1/lists/{id}": crud("get", "delete"),
        "/v1/bare": {"get": {}},
        "/v1/bare/{id}": crud("get"),
        "/v1/halfpaged": {"get": {"parameters": PAGING[:1], **ok({"type": "array"})}},
        "/v1/halfpaged/{id}": crud("get"),
        "/v1/countonly": {"get": ok({"type": "object", "properties": {"totalCount": {"type": "integer"}}})},
        "/v1/countonly/{id}": crud("get"),
        "/v1/lonely": {"get": ok({"type": "array"})},
        "/v1/lonely/{id}": {"parameters": ID, "patch": {}},
        "/v1/xmlposts": {"get": PAGED, "post": body("application/xml")},
        "/v1/xmlposts/{id}": crud("get"),
        "/v1/xmlputs": {"get": PAGED},
        "/v1/xmlputs/{id}": {"parameters": ID, "get": {}, "put": body("application/xml")},
        "/v2/scripts": {"get": PAGED, "post": JSON_BODY},
        "/v2/scripts/{id}": crud("get", "put", "delete"),
        "/v1/gadgets": {"post": JSON_BODY},
        "/v1/gadgets/{id}": crud("get", "delete"),
        "/v1/app-installers/deployments": {"get": {}, "post": JSON_BODY},
        "/v1/app-installers/deployments/{id}": crud("get", "put", "delete"),
        "/v2/actions/run": {"post": JSON_BODY},
        "/v2/commands": {"get": {}, "post": JSON_BODY},
        "/v1/scripts": {"get": {}, "post": JSON_BODY},
        "/v1/scripts/{id}": crud("get", "put", "delete"),
        "/v1/auth": {"post": JSON_BODY},
        "/v1/settings": {"get": {}, "patch": JSON_BODY},
        "/v1/singleton": {"get": {}, "post": JSON_BODY, "delete": {}},
        "/v1/patchy": {"patch": {}},
        "/v1/patchy/{id}": {"parameters": ID, "patch": {}},
        "/v1/files": {"get": {}, "post": JSON_BODY},
        "/v1/files/{fileName}": {"get": {}},
        "/v1/parents/{id}/children": {"get": {}, "post": JSON_BODY},
        "/v1/parents/{id}/children/{childId}": {"get": {}},
        "/v1/parents/{id}/retry": {"post": JSON_BODY},
        "/v1/uploads": {"post": body("multipart/form-data")},
        "/v1/blobs": {"post": body("application/octet-stream", {"type": "string", "format": "binary"})},
        "/v1/forms": {"post": body("application/x-www-form-urlencoded")},
        "/auth/current": {"post": {}},
    },
    "components": {"schemas": {
        "Thing": {"type": "object", "required": ["name"], "properties": {"name": {"type": "string"}}},
        "Envelope": {"type": "object", "properties": {"totalCount": {"type": "integer"}, "results": {"type": "array", "items": {}}}},
    }},
}

ITEM = {"get": {}, "put": {}, "post": {}, "delete": {}}
CLASSIC = {
    "swagger": "2.0",
    "consumes": ["application/xml", "application/json"],
    "paths": {
        "/printers": {"get": {}},
        "/printers/id/{id}": ITEM,
        "/printers/name/{name}": {"get": {}},
        "/aardvarks": {"get": {}},
        "/aardvarks/id/{id}": ITEM,
        "/zebras": {"get": {}},
        "/zebras/id/{id}": ITEM,
        "/buildings": {"get": {}},
        "/buildings/id/{id}": ITEM,
        "/teams": {"get": {}},
        "/teams/memberid/{id}": ITEM,
        "/teams/membername/{name}": {"get": {}},
        "/teams/leadid/{id}": ITEM,
        "/reports": {"get": {}},
        "/reports/id/{id}": {"get": {}},
        "/commands": {"get": {}},
        "/commands/name/{name}": {"get": {}},
        "/things": {"get": {}},
        "/things/id/{thingId}": ITEM,
        "/jsononly": {"get": {}},
        "/jsononly/id/{id}": {**ITEM, "post": JSON_ONLY_POST},
        "/jsonteams": {"get": {}},
        "/jsonteams/memberid/{id}": {**ITEM, "post": JSON_ONLY_POST},
        "/advancedmobiledevicesearches": {"get": {}},
        "/advancedmobiledevicesearches/id/{id}": ITEM,
        "/computerextensionattributes": {
            "get": {"responses": {"200": {"schema": {"properties": {"computer_extension_attributes": {"type": "array"}}}}}},
        },
        "/computerextensionattributes/id/{id}": ITEM,
        "/mobiledevicegroups": {"get": {"responses": {"200": {"schema": {"$ref": "#/definitions/MobileDeviceGroups"}}}}},
        "/mobiledevicegroups/id/{id}": ITEM,
    },
    "definitions": {"MobileDeviceGroups": {"type": "object", "properties": {"size": {}, "mobile_device_group": {}}}},
}

CLIENT = '''"""Fixture client.py."""
from .api import API

from ..endpoints.clc_endpoints import (
    Sites,
    Buildings
)

from ..endpoints.clc_endpoints_accounts import Accounts

from ..endpoints.pro_scripts import Scripts as ProScripts


class ClassicAPI(API):
    """Classic."""

    def __init__(self) -> None:
        super().__init__()
        self.sites = Sites(self)
        self.buildings = Buildings(self)
        self.accounts = Accounts(self)



class ProAPI(API):
    """Pro."""

    def __init__(self) -> None:
        super().__init__()
        self.scripts = ProScripts(self)

    def __str__(self) -> str:
        return "pro"
'''

API = '''class API:
    """Fixture API."""

    def __init__(self) -> None:
        self.auth = None

    def do(self) -> None:
        """Send."""
'''

CLC = '''"""Fixture Classic endpoints."""
from .models import ClassicEndpoint


class Buildings(ClassicEndpoint):
    """Buildings."""
    _uri = "/buildings"
    _name = "buildings"


class Sites(ClassicEndpoint):
    """Sites."""
    _uri = "/sites"
    _name = "sites"
'''

PRO_SCRIPTS = '''from .models import ProEndpoint


class Scripts(ProEndpoint):
    """Scripts."""
    _uri = "/scripts"
    _name = "scripts"
    _version = "1"
'''

CLC_TEST = '''"""Fixture clc_endpoints_test.py."""
from jamfpy.endpoints import clc_endpoints as clc

CLASSIC_ENDPOINTS = [
    (clc.Buildings, "/buildings", "buildings"),
    (clc.Sites, "/sites", "sites"),
]

EXPECTED_ATTRS = [
    "sites", "buildings",
    "accounts"
]
'''

CONTRACT = '''"""Fixture contract_test.py."""

# Bump when wiring an endpoint in client.py.
EXPECTED_ENDPOINT_COUNT = 5
'''


def live(spec_id, root=None):
    root_line = f'        "root": "{root}",\n' if root else ""
    return (
        f'"""Fixture live module."""\nimport pytest\n\npytestmark = pytest.mark.integration\n\nSPECS = [\n    {{\n'
        f'        "id": "{spec_id}",\n        "accessor": "{spec_id}",\n{root_line}'
        '        "min": lambda n: {"name": n},\n        "max": lambda n: {"name": n},\n    },\n]\n'
    )


FILES = {
    "api_schemas/pro.json": json.dumps(PRO),
    "api_schemas/classic.json": json.dumps(CLASSIC),
    "jamfpy/client/client.py": CLIENT,
    "jamfpy/client/api.py": API,
    "jamfpy/endpoints/clc_endpoints.py": CLC,
    "jamfpy/endpoints/pro_scripts.py": PRO_SCRIPTS,
    "tests/clc_endpoints_test.py": CLC_TEST,
    "tests/contract_test.py": CONTRACT,
    "tests/integration/clc_resources_live_test.py": live("buildings", root="building"),
    "tests/integration/pro_resources_live_test.py": live("scripts"),
}


@pytest.fixture
def tree(tmp_path):
    """A tmp tree laid out like the repo, holding only what the scaffolder reads or edits."""
    for relative, text in FILES.items():
        file = tmp_path / relative
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(text, encoding="utf-8")
    return tmp_path


def snapshot(root):
    """Every file under ``root`` with its bytes, to show a run changed nothing."""
    return {str(file.relative_to(root)): file.read_bytes() for file in sorted(root.rglob("*")) if file.is_file()}


def run(root, api, key, *extra):
    return scaffold.main(["--api", api, "--path", key, "--root", str(root), *extra])


def text(root, relative):
    return (root / relative).read_text(encoding="utf-8")


def plan_for(api, key, name=None):
    return scaffold.classify(api, key, PRO if api == "pro" else CLASSIC, name)


# Shapes


@pytest.mark.parametrize(("api", "key", "expected"), [
    # (shape, class name, attribute, _uri, _version)
    ("classic", "/printers", ("Classic simple", "Printers", "printers", "/printers", None)),
    ("classic", "/teams", ("Classic composite", "Teams", "teams", "/teams", None)),
    ("pro", "/v1/widgets", ("Pro CRUD", "Widgets", "widgets", "/widgets", "1")),
    ("pro", "/v1/gadgets", ("Pro CRUD", "Gadgets", "gadgets", "/gadgets", "1")),
    ("pro", "/v1/app-installers/deployments",
     ("Pro CRUD", "AppInstallersDeployments", "app_installers_deployments", "/app-installers/deployments", "1")),
    ("pro", "/v2/actions/run", ("Pro action", "ActionsRun", "actions_run", "/actions/run", "2")),
    # GET and POST with no {id} sibling is still the action shape, as pro.mdm's /v2/mdm/commands is.
    ("pro", "/v2/commands", ("Pro action", "Commands", "commands", "/commands", "2")),
])
def test_classify_picks_the_shape_and_names(api, key, expected):
    plan = plan_for(api, key)
    assert (plan.shape, plan.class_name, plan.attr, plan.uri, plan.version) == expected


def test_pro_crud_with_all_five_verbs_uses_every_mixin_and_names_unmapped_verbs():
    plan = plan_for("pro", "/v1/widgets")
    assert plan.mixins == ("ProGetAll", "ProGetById", "ProCreate", "ProUpdateById", "ProDeleteById")
    assert plan.unmapped == ("PATCH /v1/widgets/{id}",)
    assert plan.summary() == (
        "shape: Pro CRUD -> Widgets(ProEndpoint): get_all, get_by_id, create, update_by_id, delete_by_id; "
        "no method for PATCH /v1/widgets/{id}"
    )


def test_pro_crud_composes_exactly_the_mixins_the_verbs_back():
    plan = plan_for("pro", "/v1/gadgets")
    assert plan.mixins == ("ProGetById", "ProCreate", "ProDeleteById")
    assert plan.methods == ("get_by_id", "create", "delete_by_id")
    assert not plan.has_lifecycle


def test_classic_composite_derives_one_child_per_id_style_sibling():
    plan = plan_for("classic", "/teams")
    assert plan.children == (
        scaffold.Child(attr="leads", class_name="TeamsLeads", by_id_uri="/teams/leadid", by_name_uri=None),
        scaffold.Child(attr="members", class_name="TeamsMembers", by_id_uri="/teams/memberid", by_name_uri="/teams/membername"),
    )
    assert plan.endpoint_count == 3


def test_composite_children_say_their_get_all_returns_the_whole_collection(tree, capsys):
    assert run(tree, "classic", "/teams") == 0
    assert (
        "next: the children's get_all returns the whole collection; override it like clc_endpoints_accounts.py if the resource needs slicing"
    ) in capsys.readouterr().out.splitlines()
    classes = {n.name: n for n in ast.parse(text(tree, "jamfpy/endpoints/clc_endpoints_teams.py")).body if isinstance(n, ast.ClassDef)}
    for child in ("TeamsLeads", "TeamsMembers"):
        assert ast.get_docstring(classes[child]).endswith(  # type: ignore[union-attr]
            "``get_all`` is the inherited one and returns the whole collection, not only these records; override it, as\n"
            "``AccountUsers`` does, if the resource needs slicing."
        )
    assert "get_all" not in [n.name for n in classes["TeamsMembers"].body if isinstance(n, ast.FunctionDef)]


@pytest.mark.parametrize(("key", "name"), [
    ("/computerextensionattributes", "computer_extension_attributes"),
    ("/mobiledevicegroups", "mobile_device_groups"),
    ("/printers", "printers"),
])
def test_classic_name_is_the_response_key_when_the_schema_names_one(key, name):
    assert plan_for("classic", key).name == name


# Pagination


@pytest.mark.parametrize(("key", "mixins"), [
    pytest.param("/v1/widgets", ("ProGetAll", "ProGetById", "ProCreate", "ProUpdateById", "ProDeleteById"), id="page-params"),
    # Path-level parameters count, as tools.schemas.path merges them into the operation.
    pytest.param("/v1/pathlevel", ("ProGetAll", "ProGetById"), id="path-level-page-params"),
    # No page parameters, but the 200 response (through a $ref) is the totalCount/results envelope ProGetAll aggregates.
    pytest.param("/v1/enveloped", ("ProGetAll", "ProGetById"), id="envelope-response"),
])
def test_get_all_is_composed_when_the_collection_get_is_paginated(key, mixins):
    plan = plan_for("pro", key)
    assert plan.mixins == mixins
    assert not plan.unpaginated


@pytest.mark.parametrize(("key", "mixins"), [
    pytest.param("/v1/lists", ("ProGetById", "ProDeleteById"), id="array"),
    pytest.param("/v1/bare", ("ProGetById",), id="no-signal"),
    pytest.param("/v1/halfpaged", ("ProGetById",), id="page-without-page-size"),
    pytest.param("/v1/countonly", ("ProGetById",), id="envelope-without-results"),
])
def test_get_all_is_left_out_when_the_collection_get_is_not_paginated(key, mixins):
    plan = plan_for("pro", key)
    assert plan.shape == "Pro CRUD"
    assert plan.mixins == mixins
    assert "get_all" not in plan.methods
    assert plan.unpaginated


def test_an_unpaginated_collection_get_is_named_in_a_next_line_and_the_docstring(tree, capsys):
    assert run(tree, "pro", "/v1/lists") == 0
    assert (
        "next: GET /v1/lists is not paginated (an array or another shape), so there is no get_all; write one by hand if needed"
    ) in capsys.readouterr().out.splitlines()
    source = text(tree, "jamfpy/endpoints/pro_lists.py")
    assert "ProGetAll" not in source
    doc = ast.get_docstring(next(n for n in ast.parse(source).body if isinstance(n, ast.ClassDef)))
    assert doc == (
        "Endpoint for managing lists in the modern Jamf Pro API.\n\n"
        "Composes only the verbs the schema has, so there is no ``create`` or ``update_by_id``.\n"
        "The collection GET is not paginated, so ``get_all`` is not composed; write it by hand if it is needed."
    )


def test_a_paginated_collection_get_prints_no_pagination_line(tree, capsys):
    assert run(tree, "pro", "/v1/widgets", "--dry-run") == 0
    assert "not paginated" not in capsys.readouterr().out


# Names


@pytest.mark.parametrize(("name", "attr"), [
    ("AdvancedMobileDeviceSearches", "advanced_mobile_device_searches"),
    ("Things", "things"),
    ("MDMCommands", "mdm_commands"),
    ("ScimV2", "scim_v2"),
    ("ABC", "abc"),
])
def test_the_attribute_is_the_snake_case_of_the_name(name, attr):
    plan = plan_for("pro", "/v1/widgets", name)
    assert (plan.class_name, plan.attr, plan.slug, plan.name, plan.named) == (name, attr, attr, attr, True)


def test_a_pro_name_sets_the_class_attribute_module_and_name_key(tree):
    assert run(tree, "pro", "/v1/widgets", "--name", "WidgetThings") == 0
    module = text(tree, "jamfpy/endpoints/pro_widget_things.py")
    assert "class WidgetThings(ProEndpoint):\n" in module
    assert '"""Endpoint for managing widget things in the modern Jamf Pro API."""' in module
    # The URI and version still come from the path.
    assert '    _uri = "/widgets"\n    _name = "widget_things"\n    _version = "1"\n' in module
    client = text(tree, "jamfpy/client/client.py")
    assert "from ..endpoints.pro_widget_things import WidgetThings as ProWidgetThings\n" in client
    assert init_tail(client, "ProAPI") == "self.widget_things = ProWidgetThings(self)"
    assert "from jamfpy.endpoints.pro_widget_things import WidgetThings\n" in text(tree, "tests/pro_widget_things_test.py")
    assert {k: v for k, v in specs(text(tree, "tests/integration/pro_resources_live_test.py"))[-1].items() if k in ("id", "accessor")} == {
        "id": "widget_things", "accessor": "widget_things",
    }


def test_a_classic_name_renames_the_class_and_attribute_but_not_jamfs_key(tree):
    assert run(tree, "classic", "/advancedmobiledevicesearches", "--name", "AdvancedMobileDeviceSearches") == 0
    source = text(tree, "jamfpy/endpoints/clc_endpoints.py")
    assert class_names(source) == ["AdvancedMobileDeviceSearches", "Buildings", "Sites"]
    assert (
        "class AdvancedMobileDeviceSearches(ClassicEndpoint):\n"
        '    """Endpoint for managing advanced mobile device searches in Jamf Pro."""\n'
        '    _uri = "/advancedmobiledevicesearches"\n'
        '    _name = "advancedmobiledevicesearches"\n'
    ) in source
    client = text(tree, "jamfpy/client/client.py")
    assert clc_import_names(client) == ["AdvancedMobileDeviceSearches", "Sites", "Buildings"]
    assert init_tail(client, "ClassicAPI") == "self.advanced_mobile_device_searches = AdvancedMobileDeviceSearches(self)"
    rows = text(tree, "tests/clc_endpoints_test.py")
    assert '    (clc.AdvancedMobileDeviceSearches, "/advancedmobiledevicesearches", "advancedmobiledevicesearches"),\n' in rows
    assert '    "advanced_mobile_device_searches",\n]\n' in rows
    spec = specs(text(tree, "tests/integration/clc_resources_live_test.py"))[-1]
    assert (spec["id"], spec["accessor"], spec["root"]) == (
        "advanced_mobile_device_searches", "advanced_mobile_device_searches", "advancedmobiledevicesearches",
    )


def test_a_composite_name_prefixes_the_children_and_names_the_module(tree):
    assert run(tree, "classic", "/teams", "--name", "TeamRoster") == 0
    source = text(tree, "jamfpy/endpoints/clc_endpoints_team_roster.py")
    assert class_names(source) == ["TeamRosterChild", "TeamRosterLeads", "TeamRosterMembers", "TeamRoster"]
    assert '    _uri = "/teams"\n    _name = "teams"\n' in source
    client = text(tree, "jamfpy/client/client.py")
    assert "from ..endpoints.clc_endpoints_team_roster import TeamRoster\n" in client
    assert init_tail(client, "ClassicAPI") == "self.team_roster = TeamRoster(self)"
    assert [(s["id"], s["accessor"]) for s in specs(text(tree, "tests/integration/clc_resources_live_test.py"))[1:]] == [
        ("team_roster_leads", "team_roster.leads"), ("team_roster_members", "team_roster.members"),
    ]
    assert (tree / "tests/clc_endpoints_team_roster_test.py").exists()


@pytest.mark.parametrize("name", ["widgets", "Widget_Things", "Widget-Things", "Widget Things", "9Widgets", "Wîdgets", ""])
def test_a_name_that_is_not_pascal_case_is_refused(tree, capsys, name):
    before = snapshot(tree)
    assert run(tree, "pro", "/v1/widgets", "--name", name) == 1
    assert capsys.readouterr().err == f"scaffold: refused: NAME={name} is not a PascalCase class name (a capital, then letters and digits)\n"
    assert snapshot(tree) == before


@pytest.mark.parametrize(("name", "got"), [("Class", "class"), ("Import", "import"), ("None", "none"), ("True", "true")])
def test_a_name_that_is_a_python_keyword_is_refused(tree, capsys, name, got):
    assert run(tree, "pro", "/v1/widgets", "--name", name) == 1
    assert capsys.readouterr().err == f"scaffold: refused: cannot derive a Python name from NAME={name} (got {got!r})\n"


@pytest.mark.parametrize(("key", "name", "attr"), [("/v1/widgets", "Scripts", "scripts"), ("/v1/widgets", "Auth", "auth")])
def test_a_name_that_is_already_an_attribute_is_refused(tree, capsys, key, name, attr):
    before = snapshot(tree)
    assert run(tree, "pro", key, "--name", name) == 1
    assert capsys.readouterr().err == f"scaffold: refused: pro.{attr} already exists (ProAPI has {attr}); pass a different NAME=...\n"
    assert snapshot(tree) == before


def test_a_name_that_is_already_a_classic_class_is_refused(tree, capsys):
    assert run(tree, "classic", "/printers", "--name", "Buildings") == 1
    assert capsys.readouterr().err == "scaffold: refused: class Buildings already exists in jamfpy/endpoints/clc_endpoints.py\n"


def test_a_second_version_is_refused_without_a_name_and_scaffolded_with_one(tree, capsys):
    assert run(tree, "pro", "/v2/scripts") == 1
    assert capsys.readouterr().err == (
        "scaffold: refused: pro.scripts already exists (ProAPI has scripts); pass NAME=... to scaffold a second version alongside it\n"
    )
    assert run(tree, "pro", "/v2/scripts", "--name", "ScriptsV2") == 0
    module = text(tree, "jamfpy/endpoints/pro_scripts_v2.py")
    assert '    _uri = "/scripts"\n    _name = "scripts_v2"\n    _version = "2"\n' in module
    client = text(tree, "jamfpy/client/client.py")
    assert "from ..endpoints.pro_scripts_v2 import ScriptsV2 as ProScriptsV2\n" in client
    assert init_tail(client, "ProAPI") == "self.scripts_v2 = ProScriptsV2(self)"


@pytest.mark.parametrize(("api", "key", "hinted"), [
    ("classic", "/printers", True),
    ("classic", "/teams", True),
    # A Pro slug is hinted only when it has no word break; a hyphenated path already split into words.
    ("pro", "/v1/widgets", True),
    ("pro", "/v1/app-installers/deployments", False),
])
def test_names_taken_from_the_path_alone_get_a_name_hint(tree, capsys, api, key, hinted):
    assert run(tree, api, key, "--dry-run") == 0
    lines = capsys.readouterr().out.splitlines()
    hint = [line for line in lines if line.startswith("next: names come from the path alone")]
    assert bool(hint) == hinted
    if hinted:
        plan = plan_for(api, key)
        assert hint == [
            f"next: names come from the path alone (class {plan.class_name}, attribute {plan.attr}); for a multi-word resource "
            "use NAME=<PascalCaseName> instead (undo this run first if it wrote)"
        ]


@pytest.mark.parametrize(("api", "key", "name"), [("classic", "/printers", "Printers"), ("pro", "/v1/widgets", "Widgets")])
def test_a_given_name_gets_no_name_hint(tree, capsys, api, key, name):
    assert run(tree, api, key, "--name", name, "--dry-run") == 0
    assert "names come from the path alone" not in capsys.readouterr().out


# Refusals


@pytest.mark.parametrize(("api", "key", "message"), [
    ("pro", "/v1/nope", "refused: the pro schema has no path /v1/nope"),
    ("pro", "/auth/current", "refused: /auth/current has no /v<n> version prefix, so there is no _version to set"),
    ("pro", "/v1/parents/{id}/children", "refused: /v1/parents/{id}/children has more than one path parameter ({id}, {childId})"),
    ("pro", "/v1/files", "refused: path parameter {fileName} in /v1/files/{fileName} is not named id"),
    ("classic", "/things", "refused: path parameter {thingId} in /things/id/{thingId} is not named id"),
    ("pro", "/v1/parents/{id}/retry",
     "refused: /v1/parents/{id}/retry has a path parameter of its own; scaffold a collection path (an endpoint's _uri has none)"),
    ("pro", "/v1/uploads", "refused: POST /v1/uploads takes a multipart or binary body (multipart/form-data)"),
    ("pro", "/v1/blobs", "refused: POST /v1/blobs takes a multipart or binary body (application/octet-stream)"),
    ("pro", "/v1/forms", "refused: POST /v1/forms takes application/x-www-form-urlencoded, not JSON"),
    ("classic", "/jsononly", "refused: POST /jsononly/id/{id} takes application/json, not XML"),
    # The body checks on each shape's sends: a Pro CRUD POST and PUT, and a composite sibling.
    ("pro", "/v1/xmlposts", "refused: POST /v1/xmlposts takes application/xml, not JSON"),
    ("pro", "/v1/xmlputs", "refused: PUT /v1/xmlputs/{id} takes application/xml, not JSON"),
    ("classic", "/jsonteams", "refused: POST /jsonteams/memberid/{id} takes application/json, not XML"),
    ("pro", "/v1/lonely",
     "refused: no shape rule matches /v1/lonely (GET) and /v1/lonely/{id} (PATCH): "
     "the collection GET is not paginated, so there is no get_all, and no other verb backs a method"),
    ("pro", "/v1/settings",
     "refused: no shape rule matches /v1/settings (GET PATCH) with no {id} sibling: the Pro action shape needs POST, and at most GET besides"),
    ("pro", "/v1/singleton",
     "refused: no shape rule matches /v1/singleton (DELETE GET POST) with no {id} sibling: the Pro action shape needs POST, and at most GET besides"),
    ("pro", "/v1/patchy",
     "refused: no shape rule matches /v1/patchy (PATCH) and /v1/patchy/{id} (PATCH): "
     "Pro CRUD needs GET or POST on the collection or GET, PUT or DELETE by id"),
    ("classic", "/reports",
     "refused: no shape rule matches /reports (GET) and /reports/id/{id} (GET): Classic simple (ClassicEndpoint) needs GET "
     "on the collection and DELETE GET POST PUT by id"),
    ("classic", "/commands",
     "refused: no shape rule matches /commands (GET): Classic needs /commands/id/{id} (simple) or id-style siblings such as "
     "/commands/<thing>id/{id} (composite)"),
    ("pro", "/v1/scripts", "refused: /v1/scripts already exists: Scripts in jamfpy/endpoints/pro_scripts.py wraps it"),
    ("classic", "/buildings", "refused: class Buildings already exists in jamfpy/endpoints/clc_endpoints.py"),
    ("pro", "/v1/auth", "refused: pro.auth already exists (ProAPI has auth); pass NAME=... to scaffold a second version alongside it"),
    ("pro", "/v2/scripts", "refused: pro.scripts already exists (ProAPI has scripts); pass NAME=... to scaffold a second version alongside it"),
])
def test_refusal_prints_one_line_and_writes_nothing(tree, capsys, api, key, message):
    before = snapshot(tree)
    assert run(tree, api, key) == 1
    out, err = capsys.readouterr()
    assert err.startswith(f"scaffold: {message}")
    assert err.count("\n") == 1 and not out
    assert snapshot(tree) == before


@pytest.mark.parametrize("existing", ["jamfpy/endpoints/pro_widgets.py", "tests/pro_widgets_test.py"])
def test_refuses_when_the_module_or_test_module_exists(tree, capsys, existing):
    (tree / existing).write_text("", encoding="utf-8")
    before = snapshot(tree)
    assert run(tree, "pro", "/v1/widgets") == 1
    assert capsys.readouterr().err == f"scaffold: refused: {existing} already exists\n"
    assert snapshot(tree) == before


def test_refuses_when_the_live_spec_exists(tree, capsys):
    (tree / "tests/integration/pro_resources_live_test.py").write_text(live("widgets"), encoding="utf-8")
    assert run(tree, "pro", "/v1/widgets") == 1
    assert capsys.readouterr().err == (
        "scaffold: refused: a live spec with id 'widgets' already exists in tests/integration/pro_resources_live_test.py\n"
    )


def test_a_second_run_for_the_same_path_is_refused(tree, capsys):
    assert run(tree, "pro", "/v1/widgets") == 0
    before = snapshot(tree)
    assert run(tree, "pro", "/v1/widgets") == 1
    assert capsys.readouterr().err == "scaffold: refused: /v1/widgets already exists: Widgets in jamfpy/endpoints/pro_widgets.py wraps it\n"
    assert snapshot(tree) == before


def test_a_missing_file_fails_with_one_line_and_writes_nothing(tree, capsys):
    (tree / "tests/contract_test.py").unlink()
    before = snapshot(tree)
    assert run(tree, "pro", "/v1/widgets") == 1
    assert capsys.readouterr().err.startswith("scaffold: cannot read tests/contract_test.py under ")
    assert snapshot(tree) == before


# What it writes


def class_names(source):
    return [node.name for node in ast.parse(source).body if isinstance(node, ast.ClassDef)]


def clc_import_names(source):
    block = next(n for n in ast.parse(source).body if isinstance(n, ast.ImportFrom) and n.module == "endpoints.clc_endpoints")
    return [alias.name for alias in block.names]


@pytest.mark.parametrize(("key", "order"), [
    ("/aardvarks", ["Aardvarks", "Buildings", "Sites"]),
    ("/printers", ["Buildings", "Printers", "Sites"]),
    ("/zebras", ["Buildings", "Sites", "Zebras"]),
])
def test_classic_simple_class_goes_in_alphabetical_position(tree, key, order):
    assert run(tree, "classic", key) == 0
    source = text(tree, "jamfpy/endpoints/clc_endpoints.py")
    assert class_names(source) == order
    new = order[order.index(next(name for name in order if name not in ("Buildings", "Sites")))]
    # Two blank lines before it, and before the class after it.
    assert f"\n\n\nclass {new}(ClassicEndpoint):\n" in source
    assert "\n\n\n\n" not in source and source.endswith("\n") and not source.endswith("\n\n")


@pytest.mark.parametrize(("key", "names", "last_lines"), [
    ("/aardvarks", ["Aardvarks", "Sites", "Buildings"], "    Buildings\n)\n"),
    ("/printers", ["Printers", "Sites", "Buildings"], "    Buildings\n)\n"),
    # Appended last: the previous last name gains the trailing comma it lacked.
    ("/zebras", ["Sites", "Buildings", "Zebras"], "    Buildings,\n    Zebras,\n)\n"),
])
def test_classic_import_goes_before_the_first_name_sorting_after_it(tree, key, names, last_lines):
    assert run(tree, "classic", key) == 0
    source = text(tree, "jamfpy/client/client.py")
    assert clc_import_names(source) == names
    assert last_lines in source


def init_tail(source, class_name):
    api_class = next(n for n in ast.parse(source).body if isinstance(n, ast.ClassDef) and n.name == class_name)
    init = next(n for n in api_class.body if isinstance(n, ast.FunctionDef) and n.name == "__init__")
    return ast.unparse(init.body[-1])


def test_classic_simple_wiring_rows_and_count(tree):
    assert run(tree, "classic", "/printers") == 0
    client = text(tree, "jamfpy/client/client.py")
    assert init_tail(client, "ClassicAPI") == "self.printers = Printers(self)"
    assert init_tail(client, "ProAPI") == "self.scripts = ProScripts(self)"
    rows = text(tree, "tests/clc_endpoints_test.py")
    assert '    (clc.Buildings, "/buildings", "buildings"),\n    (clc.Printers, "/printers", "printers"),\n    (clc.Sites,' in rows
    assert '    "accounts",\n    "printers",\n]\n' in rows
    ast.parse(rows)
    assert "EXPECTED_ENDPOINT_COUNT = 6\n" in text(tree, "tests/contract_test.py")


def test_pro_wiring_imports_after_the_last_pro_import_with_an_alias(tree):
    assert run(tree, "pro", "/v1/widgets") == 0
    client = text(tree, "jamfpy/client/client.py")
    assert (
        "from ..endpoints.pro_scripts import Scripts as ProScripts\n"
        "from ..endpoints.pro_widgets import Widgets as ProWidgets\n"
    ) in client
    assert init_tail(client, "ProAPI") == "self.widgets = ProWidgets(self)"
    assert init_tail(client, "ClassicAPI") == "self.accounts = Accounts(self)"
    # The method after __init__ is untouched.
    assert '        self.widgets = ProWidgets(self)\n\n    def __str__(self) -> str:\n' in client


def test_composite_wiring_imports_after_the_other_composite(tree):
    assert run(tree, "classic", "/teams") == 0
    client = text(tree, "jamfpy/client/client.py")
    assert (
        "from ..endpoints.clc_endpoints_accounts import Accounts\n"
        "from ..endpoints.clc_endpoints_teams import Teams\n"
    ) in client
    assert init_tail(client, "ClassicAPI") == "self.teams = Teams(self)"
    assert "EXPECTED_ENDPOINT_COUNT = 8\n" in text(tree, "tests/contract_test.py")


def test_a_long_import_is_wrapped_in_parentheses(tree):
    # A name long enough to push the one-line import past MAX_LINE.
    long_key = "/v1/" + "-".join(["segment"] * 7)
    schema = json.loads(text(tree, "api_schemas/pro.json"))
    schema["paths"][long_key] = {"post": JSON_BODY}
    (tree / "api_schemas/pro.json").write_text(json.dumps(schema), encoding="utf-8")
    assert run(tree, "pro", long_key) == 0
    client = text(tree, "jamfpy/client/client.py")
    assert all(len(line) <= scaffold.MAX_LINE for line in client.splitlines())
    assert "import (\n    Segment" in client
    ast.parse(client)


def generated_files(root, before):
    after = snapshot(root)
    return [name for name in after if name.endswith(".py") and after[name] != before.get(name)]


@pytest.mark.parametrize(("api", "key"), [
    ("classic", "/printers"), ("classic", "/teams"), ("pro", "/v1/widgets"), ("pro", "/v1/gadgets"), ("pro", "/v1/lists"),
    ("pro", "/v2/actions/run"),
])
def test_every_generated_or_changed_python_file_parses(tree, api, key):
    before = snapshot(tree)
    assert run(tree, api, key) == 0
    changed = generated_files(tree, before)
    assert changed
    for name in changed:
        ast.parse(text(tree, name), filename=name)


def specs(source):
    namespace = {}
    exec(compile(source, "live", "exec"), namespace)  # pylint: disable=exec-used
    return namespace["SPECS"]


@pytest.mark.parametrize(("api", "key", "expected"), [
    ("pro", "/v1/widgets", [{"id": "widgets", "accessor": "widgets"}]),
    ("classic", "/printers", [{"id": "printers", "accessor": "printers", "root": "printers"}]),
    ("classic", "/teams", [
        {"id": "teams_leads", "accessor": "teams.leads", "root": "leads"},
        {"id": "teams_members", "accessor": "teams.members", "root": "members"},
    ]),
])
def test_live_spec_is_appended_inside_specs_and_fails_until_filled_in(tree, api, key, expected):
    module = scaffold.LIVE_TESTS[api]
    assert run(tree, api, key) == 0
    loaded = specs(text(tree, module))
    assert len(loaded) == 1 + len(expected)
    for spec, want in zip(loaded[1:], expected):
        assert {k: v for k, v in spec.items() if k not in ("min", "max")} == want
        for kind in ("min", "max"):
            with pytest.raises(pytest.fail.Exception, match="fill in the builders"):
                spec[kind]("jamfpy-it-x")


@pytest.mark.parametrize("key", ["/v1/gadgets", "/v2/actions/run"])
def test_no_live_spec_without_the_full_lifecycle(tree, capsys, key):
    before = text(tree, "tests/integration/pro_resources_live_test.py")
    assert run(tree, "pro", key) == 0
    assert text(tree, "tests/integration/pro_resources_live_test.py") == before
    assert "next: no live spec (the lifecycle needs create, get_by_id, update_by_id, delete_by_id)" in capsys.readouterr().out


@pytest.mark.parametrize(("api", "key", "line"), [
    # A Pro action has no CRUD to drive the lifecycle runner with, so it gets no spec and the generator wants a reason.
    ("pro", "/v2/actions/run",
     'next: make coverage-doc will refuse pro.actions_run until it has a reason: add "actions_run": "<why it has no live spec>" '
     "to LIVE_NOT_COVERED in tests/integration/pro_resources_live_test.py"),
    # A composite's children get specs; the parent, which only has get_all, does not.
    ("classic", "/teams",
     'next: make coverage-doc will refuse classic.teams (the parent; only its children get live specs) until it has a reason: '
     'add "teams": "<why it has no live spec>" to LIVE_NOT_COVERED in tests/integration/clc_resources_live_test.py'),
])
def test_an_endpoint_with_no_live_spec_says_coverage_doc_wants_a_reason(tree, capsys, api, key, line):
    assert run(tree, api, key, "--dry-run") == 0
    assert capsys.readouterr().out.splitlines().count(line) == 1


@pytest.mark.parametrize(("api", "key"), [("pro", "/v1/widgets"), ("classic", "/printers")])
def test_an_endpoint_with_a_live_spec_gets_no_reason_line(tree, capsys, api, key):
    assert run(tree, api, key, "--dry-run") == 0
    assert "LIVE_NOT_COVERED" not in capsys.readouterr().out


def load_module(file, name, monkeypatch):
    spec = importlib.util.spec_from_file_location(name, file)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    return module


def run_generated_tests(module, fixtures):
    """Call every test in a generated module with the fixtures it names; a ``child`` parameter is run per ``BY_ID`` key."""
    ran = []
    for name, function in inspect.getmembers(module, inspect.isfunction):
        if not name.startswith("test_"):
            continue
        params = inspect.signature(function).parameters
        for child in (module.BY_ID if "child" in params else [None]):
            kwargs = {key: fixtures[key] for key in params if key != "child"}
            function(**kwargs, **({"child": child} if child else {}))
            ran.append(name)
    return ran


@pytest.mark.parametrize("case", [
    # (path, module, class name, attribute, how many tests it generates, --name)
    pytest.param(("/v1/widgets", "pro_widgets", "Widgets", "widgets", 7, None), id="crud"),
    pytest.param(("/v1/gadgets", "pro_gadgets", "Gadgets", "gadgets", 5, None), id="partial-crud"),
    pytest.param(("/v1/lists", "pro_lists", "Lists", "lists", 4, None), id="unpaginated-crud"),
    pytest.param(("/v2/actions/run", "pro_actions_run", "ActionsRun", "actions_run", 1, None), id="action"),
    pytest.param(("/v1/widgets", "pro_widget_things", "WidgetThings", "widget_things", 7, "WidgetThings"), id="named-crud"),
])
def test_generated_pro_tests_import_and_pass(tree, monkeypatch, pro_api, mocked_responses, case):
    key, module, class_name, attr, expected_tests, name = case
    assert run(tree, "pro", key, *(["--name", name] if name else [])) == 0
    endpoint = load_module(tree / f"jamfpy/endpoints/{module}.py", f"jamfpy.endpoints.{module}", monkeypatch)
    generated = load_module(tree / f"tests/{module}_test.py", f"scaffolded_{module}_test", monkeypatch)
    cls = getattr(endpoint, class_name)
    assert issubclass(cls, Endpoint)
    setattr(pro_api, attr, cls(pro_api))
    ran = run_generated_tests(generated, {"pro_api": pro_api, "mocked_responses": mocked_responses})
    assert len(ran) == expected_tests


def test_generated_pro_crud_with_all_verbs_subclasses_pro_endpoint(tree, monkeypatch):
    assert run(tree, "pro", "/v1/widgets") == 0
    endpoint = load_module(tree / "jamfpy/endpoints/pro_widgets.py", "jamfpy.endpoints.pro_widgets", monkeypatch)
    assert endpoint.Widgets.__bases__ == (ProEndpoint,)
    assert (endpoint.Widgets._uri, endpoint.Widgets._name, endpoint.Widgets._version) == ("/widgets", "widgets", "1")


def test_generated_composite_imports_and_its_tests_pass(tree, monkeypatch, classic_api, mocked_responses):
    assert run(tree, "classic", "/teams") == 0
    endpoint = load_module(tree / "jamfpy/endpoints/clc_endpoints_teams.py", "jamfpy.endpoints.clc_endpoints_teams", monkeypatch)
    generated = load_module(tree / "tests/clc_endpoints_teams_test.py", "scaffolded_clc_endpoints_teams_test", monkeypatch)
    classic_api.teams = endpoint.Teams(classic_api)
    assert (classic_api.teams.members._by_id_uri, classic_api.teams.members._by_name_uri) == ("/teams/memberid", "/teams/membername")
    assert classic_api.teams.leads._by_name_uri is None
    ran = run_generated_tests(generated, {"classic_api": classic_api, "mocked_responses": mocked_responses})
    # The parent's get_all, then six child tests for each of the two children.
    assert len(ran) == 1 + 6 * 2


# Writing and the CLI


def test_dry_run_prints_the_shape_and_files_and_writes_nothing(tree, capsys):
    before = snapshot(tree)
    assert run(tree, "pro", "/v1/widgets", "--dry-run") == 0
    assert snapshot(tree) == before
    assert capsys.readouterr().out.splitlines() == [
        "shape: Pro CRUD -> Widgets(ProEndpoint): get_all, get_by_id, create, update_by_id, delete_by_id; "
        "no method for PATCH /v1/widgets/{id}",
        "would write:",
        "  new      jamfpy/endpoints/pro_widgets.py",
        "  changed  jamfpy/client/client.py",
        "  new      tests/pro_widgets_test.py",
        "  changed  tests/integration/pro_resources_live_test.py",
        "  changed  tests/contract_test.py",
        "next: fill in the live builders in tests/integration/pro_resources_live_test.py; review _name ('widgets') and the docstrings",
        "next: names come from the path alone (class Widgets, attribute widgets); for a multi-word resource "
        "use NAME=<PascalCaseName> instead (undo this run first if it wrote)",
        "regenerate COVERAGE.md with make coverage-doc",
    ]


def test_a_write_failure_midway_puts_every_file_back(tree, capsys, monkeypatch):
    before = snapshot(tree)
    real_replace = os.replace
    calls = []

    def failing_replace(src, dst):
        calls.append(dst)
        if len(calls) == 3:
            raise OSError(28, "No space left on device", str(dst))
        real_replace(src, dst)

    monkeypatch.setattr(os, "replace", failing_replace)
    assert run(tree, "pro", "/v1/widgets") == 1
    # The new module and client.py were swapped in before the third write failed; both are undone.
    assert len(calls) == 3
    assert capsys.readouterr().err.endswith("No space left on device; nothing was changed\n")
    assert snapshot(tree) == before


def test_a_staging_failure_leaves_no_temp_files(tree, capsys, monkeypatch):
    before = snapshot(tree)
    real_write_text = Path.write_text
    calls = []

    def failing_write_text(self, data, *args, **kwargs):
        calls.append(self)
        if len(calls) == 2:
            raise OSError(13, "Permission denied", str(self))
        return real_write_text(self, data, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", failing_write_text)
    assert run(tree, "classic", "/printers") == 1
    assert "Permission denied; nothing was changed" in capsys.readouterr().err
    assert snapshot(tree) == before


def test_missing_arguments_are_a_usage_error():
    with pytest.raises(SystemExit) as exc:
        scaffold.main(["--api", "pro"])
    assert exc.value.code == 2


def test_cli_runs_as_a_module(tree):
    result = subprocess.run(
        [sys.executable, "-m", "tools.scaffold", "--api", "classic", "--path", "/printers", "--root", str(tree), "--dry-run"],
        cwd=REPO_ROOT, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("shape: Classic simple -> Printers(ClassicEndpoint)\nwould write:\n")
