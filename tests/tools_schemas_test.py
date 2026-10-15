"""Unit tests for tools/schemas.py: loading, lookup, pull, probe, drift and the CLI.

Behaviour tests use small fixture schemas and tmp paths; only the two CLI smoke tests read the committed files, and
they assert structure rather than Jamf's current verbs, so a schema refresh can't break them.
Network calls go through ``mocked_responses``, and the probe runs through a real ``Tenant`` from ``tests/conftest.py``.
"""
# pylint: disable=missing-function-docstring,redefined-outer-name,too-many-lines
import copy
import datetime as dt
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest
import responses
from conftest import FAKE_TOKEN, FQDN, register_oauth_token

from tools import schemas

REPO_ROOT = Path(__file__).resolve().parent.parent
NOW = dt.datetime(2026, 10, 15, 12, 0, tzinfo=dt.UTC)

OPENAPI = {
    "openapi": "3.0.1",
    "paths": {
        "/v1/scripts": {
            "get": {"summary": "List scripts", "parameters": [{"$ref": "#/components/parameters/page"}]},
            "post": {
                "summary": "Create a script",
                "x-required-privileges": ["Create Scripts"],
                "requestBody": {"required": True, "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Script"}}}},
            },
        },
        "/v1/scripts/{id}": {
            "parameters": [
                {"name": "id", "in": "path", "required": True, "schema": {"type": "string"}},
                {"name": "verbose", "in": "query", "schema": {"type": "boolean"}},
            ],
            "get": {"parameters": [{"name": "id", "in": "path", "required": True, "description": "own", "schema": {"type": "integer"}}]},
            "delete": {},
        },
        "/v1/parents": {"post": {"requestBody": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/Parent"}}}}}},
        "/v1/broken": {"post": {"requestBody": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/Nope"}}}}}},
    },
    "components": {
        "parameters": {"page": {"name": "page", "in": "query", "schema": {"type": "integer", "default": 0}}},
        "schemas": {
            "Script": {
                "type": "object",
                "required": ["name"],
                "properties": {"name": {"type": "string"}, "category": {"$ref": "#/components/schemas/Category"}},
            },
            "Category": {"type": "object", "properties": {"id": {"type": "string"}}},
            "Parent": {"type": "object", "properties": {"child": {"$ref": "#/components/schemas/Child"}}},
            "Child": {"type": "object", "properties": {"parent": {"$ref": "#/components/schemas/Parent"}}},
        },
    },
}

SWAGGER = {
    "swagger": "2.0",
    "consumes": ["application/xml", "application/json"],
    "paths": {
        "/buildings/id/{id}": {
            "get": {"summary": "Find a building", "parameters": [{"name": "id", "in": "path", "required": True, "type": "integer"}]},
            "post": {
                "parameters": [
                    {"name": "id", "in": "path", "required": True, "type": "integer"},
                    {"name": "building", "in": "body", "required": True, "schema": {"$ref": "#/definitions/Building"}},
                ],
            },
            " delete": {"summary": "Delete a building"},
        },
        "/buildings": {"get": {}},
        "/computers": {"get": {}},
    },
    "definitions": {
        "Building": {"type": "object", "properties": {"name": {"type": "string"}, "site": {"$ref": "#/definitions/Site"}}},
        "Site": {"type": "object", "properties": {"id": {"type": "integer"}}},
    },
}

# Jamf's Classic schema declares several in: body parameters on some operations; this is the shape of the real ones.
SWAGGER_BODIES = {
    "swagger": "2.0",
    "consumes": ["application/xml"],
    "paths": {
        "/commands/command": {
            "post": {
                "parameters": [
                    {"name": "command", "in": "body", "required": True, "schema": {"$ref": "#/definitions/Command"}},
                    {"name": "device_name", "in": "body", "required": False, "schema": {"type": "string"}},
                    {"name": "pin", "in": "body", "required": True, "schema": {"type": "integer"}},
                    {"name": "dry_run", "in": "query", "type": "boolean"},
                ],
            },
        },
        "/commands/optional": {
            "post": {
                "consumes": ["application/json"],
                "parameters": [
                    {"name": "a", "in": "body", "schema": {"type": "string"}},
                    {"name": "b", "in": "body", "schema": {"type": "string"}},
                ],
            },
        },
    },
    "definitions": {"Command": {"type": "string", "enum": ["Lock", "Wipe"]}},
}

CLASSIC_YAML = """\
swagger: '2.0'
info:
  title: Classic API Resource Documentation
paths:
  /patchexternalsources/id/{id}:
    ' delete':
      summary: Deletes a patch external source by id
    get:
      summary: Finds a patch external source by id
  /computers:
    get:
      summary: Finds all computers
      deprecated: true
      x-deprecation-date: 2025-02-11
"""


@pytest.fixture
def schema_dir(tmp_path, monkeypatch):
    """A tmp ``api_schemas/`` the CLI reads and writes instead of the committed one."""
    monkeypatch.setattr(schemas, "SCHEMA_DIR", tmp_path)
    return tmp_path


@pytest.fixture
def no_schema_env(monkeypatch):
    """Clear every variable the tools read, so a test sees only what it sets."""
    for name in (schemas.FQDN_ENV, schemas.CLIENT_ID_ENV, schemas.CLIENT_SECRET_ENV, *schemas.SOURCE_ENV.values()):
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def write_json(file, data):
    file.write_text(json.dumps(data), encoding="utf-8")
    return file


# Tolerant loading


@pytest.mark.parametrize(("text", "expected"), [
    ('{"a": 1,}', {"a": 1}),
    ('[1, 2, ]', [1, 2]),
    ('{"a": [1, {"b": [2,],},],\n}', {"a": [1, {"b": [2]}]}),
])
def test_strip_trailing_commas_before_closing_brackets(text, expected):
    assert json.loads(schemas.strip_trailing_commas(text)) == expected


def test_strip_trailing_commas_leaves_commas_inside_strings():
    text = '{"a": "x, }", "b": "y,]", "c": "say \\"hi\\", ]", "d": [1,],}'
    assert json.loads(schemas.strip_trailing_commas(text)) == {"a": "x, }", "b": "y,]", "c": 'say "hi", ]', "d": [1]}


def test_strip_trailing_commas_leaves_valid_json_unchanged():
    text = json.dumps({"a": "x, }", "b": [1, 2], "c": {"d": "e,]"}}, indent=2)
    assert schemas.strip_trailing_commas(text) == text


def test_load_classic_tolerates_trailing_commas_and_normalises_verbs(tmp_path):
    (tmp_path / "classic.json").write_text('{"paths": {"/a": {" delete": {"summary": "x, }"}, "get": {},},},}', encoding="utf-8")
    assert schemas.load_classic(tmp_path) == {"paths": {"/a": {"delete": {"summary": "x, }"}, "get": {}}}}


def test_load_raises_schema_error_for_a_missing_or_invalid_file(tmp_path):
    with pytest.raises(schemas.SchemaError, match="no schema file"):
        schemas.load_pro(tmp_path)
    (tmp_path / "pro.json").write_text('{"paths": {},}', encoding="utf-8")
    with pytest.raises(schemas.SchemaError, match="not valid JSON"):
        schemas.load_pro(tmp_path)
    write_json(tmp_path / "pro.json", {"openapi": "3.0.1"})
    with pytest.raises(schemas.SchemaError, match="no 'paths' object"):
        schemas.load_pro(tmp_path)


def test_load_rejects_an_unknown_api():
    with pytest.raises(ValueError, match="unknown API 'jss'"):
        schemas.load("jss")


# Supplement merge


SUPPLEMENT = {
    "x-jamfpy-generated": {"generatedAt": "2026-10-15T12:00:00+00:00"},
    "paths": {
        "/v1/scripts": {"x-jamfpy-source": "options-probe", "delete": {}},
        "/v1/app-installers": {"x-jamfpy-source": "options-probe", "get": {}},
    },
}


def test_load_pro_merges_the_supplement_and_the_main_schema_wins(tmp_path):
    write_json(tmp_path / "pro.json", OPENAPI)
    write_json(tmp_path / "pro-supplement.json", SUPPLEMENT)
    merged = schemas.load_pro(tmp_path)
    assert merged["paths"]["/v1/app-installers"] == {"x-jamfpy-source": "options-probe", "get": {}}
    assert merged["paths"]["/v1/scripts"] == OPENAPI["paths"]["/v1/scripts"]
    assert list(merged["paths"]) == [*OPENAPI["paths"], "/v1/app-installers"]
    assert "x-jamfpy-generated" not in merged


def test_load_pro_without_the_supplement(tmp_path):
    write_json(tmp_path / "pro.json", OPENAPI)
    write_json(tmp_path / "pro-supplement.json", SUPPLEMENT)
    assert schemas.load_pro(tmp_path, supplement=False) == OPENAPI


def test_load_pro_without_a_supplement_file(tmp_path):
    write_json(tmp_path / "pro.json", OPENAPI)
    assert schemas.load(api="pro", directory=tmp_path) == OPENAPI


# paths()


def test_paths_matches_case_insensitively_and_sorts():
    assert schemas.paths("pro", "SCRIPTS", schema=OPENAPI) == [("/v1/scripts", ["get", "post"]), ("/v1/scripts/{id}", ["delete", "get"])]


def test_paths_without_match_lists_every_path():
    assert [key for key, _ in schemas.paths("pro", schema=OPENAPI)] == sorted(OPENAPI["paths"])


def test_paths_normalises_the_stray_space_verb():
    assert schemas.paths("classic", "/id/", schema=SWAGGER) == [("/buildings/id/{id}", ["delete", "get", "post"])]


def test_operations_prefers_the_proper_key_over_a_stray_one():
    assert schemas.operations({" delete": "stray", "delete": "proper", "GET": "get", "parameters": []}) == {"delete": "proper", "get": "get"}
    assert schemas.operations({"delete": "proper", " delete": "stray"}) == {"delete": "proper"}


def test_normalise_verbs_keeps_key_position():
    schema = {"paths": {"/a": {"x-note": 1, " delete": {"s": 1}, "get": {}}, "/b": {"delete": {"s": 2}, " delete": {"s": 3}}}}
    schemas.normalise_verbs(schema)
    assert list(schema["paths"]["/a"].items()) == [("x-note", 1), ("delete", {"s": 1}), ("get", {})]
    assert schema["paths"]["/b"] == {"delete": {"s": 2}}


# path()


def test_path_resolves_openapi_refs_in_parameters_and_request_body():
    described = schemas.path("pro", "/v1/scripts", schema=OPENAPI)
    assert described["api"] == "pro"
    assert described["path"] == "/v1/scripts"
    assert described["methods"]["get"]["parameters"] == [
        {"x-jamfpy-ref": "#/components/parameters/page", "name": "page", "in": "query", "schema": {"type": "integer", "default": 0}}
    ]
    post = described["methods"]["post"]
    assert post["summary"] == "Create a script"
    assert post["x-required-privileges"] == ["Create Scripts"]
    assert post["requestBody"] == {
        "required": True,
        "contentTypes": ["application/json"],
        "schema": {
            "x-jamfpy-ref": "#/components/schemas/Script",
            "type": "object",
            "required": ["name"],
            "properties": {
                "name": {"type": "string"},
                "category": {"x-jamfpy-ref": "#/components/schemas/Category", "type": "object", "properties": {"id": {"type": "string"}}},
            },
        },
    }


def test_path_merges_path_level_parameters_and_the_operation_overrides():
    methods = schemas.path("pro", "/v1/scripts/{id}", schema=OPENAPI)["methods"]
    assert [(p["name"], p.get("description")) for p in methods["get"]["parameters"]] == [("verbose", None), ("id", "own")]
    assert [p["name"] for p in methods["delete"]["parameters"]] == ["id", "verbose"]
    assert "requestBody" not in methods["delete"]


def test_path_resolves_swagger_definitions_and_moves_the_body_parameter():
    described = schemas.path("classic", "/buildings/id/{id}", schema=SWAGGER)
    assert list(described["methods"]) == ["delete", "get", "post"]
    post = described["methods"]["post"]
    assert [p["name"] for p in post["parameters"]] == ["id"]
    assert post["requestBody"] == {
        "required": True,
        "contentTypes": ["application/xml", "application/json"],
        "schema": {
            "x-jamfpy-ref": "#/definitions/Building",
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "site": {"x-jamfpy-ref": "#/definitions/Site", "type": "object", "properties": {"id": {"type": "integer"}}},
            },
        },
    }
    assert described["methods"]["delete"] == {"summary": "Delete a building", "parameters": []}


def test_path_merges_several_body_parameters_into_one_object_schema():
    post = schemas.path("classic", "/commands/command", schema=SWAGGER_BODIES)["methods"]["post"]
    assert [p["name"] for p in post["parameters"]] == ["dry_run"]
    assert post["requestBody"] == {
        "required": True,
        "contentTypes": ["application/xml"],
        "schema": {
            "type": "object",
            "properties": {
                "command": {"x-jamfpy-ref": "#/definitions/Command", "type": "string", "enum": ["Lock", "Wipe"]},
                "device_name": {"type": "string"},
                "pin": {"type": "integer"},
            },
            "required": ["command", "pin"],
            "x-jamfpy-note": "3 in: body parameters merged into one object schema",
        },
    }


def test_path_merged_body_is_optional_when_no_body_parameter_is_required():
    body = schemas.path("classic", "/commands/optional", schema=SWAGGER_BODIES)["methods"]["post"]["requestBody"]
    assert body["required"] is False
    assert body["contentTypes"] == ["application/json"]
    assert body["schema"]["required"] == []
    assert sorted(body["schema"]["properties"]) == ["a", "b"]


@pytest.mark.parametrize(("api", "schema", "key"), [
    ("pro", OPENAPI, "/v1/scripts"),
    ("classic", SWAGGER, "/buildings/id/{id}"),
    ("classic", SWAGGER_BODIES, "/commands/command"),
])
def test_path_request_body_has_one_shape_whatever_the_source(api, schema, key):
    bodies = [method["requestBody"] for method in schemas.path(api, key, schema=schema)["methods"].values() if "requestBody" in method]
    assert bodies
    assert all(set(body) == {"required", "contentTypes", "schema"} for body in bodies)


def test_path_marks_a_cycle_instead_of_recursing():
    body = schemas.path("pro", "/v1/parents", schema=OPENAPI)["methods"]["post"]["requestBody"]["schema"]
    child = body["properties"]["child"]
    assert child["x-jamfpy-ref"] == "#/components/schemas/Child"
    assert child["properties"]["parent"] == {"$ref": "#/components/schemas/Parent", "x-jamfpy-unresolved": "cycle"}


def test_path_marks_a_missing_ref():
    body = schemas.path("pro", "/v1/broken", schema=OPENAPI)["methods"]["post"]["requestBody"]["schema"]
    assert body == {"$ref": "#/components/schemas/Nope", "x-jamfpy-unresolved": "missing"}


def test_resolve_stops_at_the_depth_limit():
    depth = schemas.MAX_REF_DEPTH + 2
    defs = {f"L{i}": {"properties": {"next": {"$ref": f"#/definitions/L{i + 1}"}}} for i in range(depth)}
    resolved = schemas.resolve({"$ref": "#/definitions/L0"}, {"paths": {}, "definitions": defs})
    for i in range(schemas.MAX_REF_DEPTH):
        assert resolved["x-jamfpy-ref"] == f"#/definitions/L{i}"
        resolved = resolved["properties"]["next"]
    assert resolved == {"$ref": f"#/definitions/L{schemas.MAX_REF_DEPTH}", "x-jamfpy-unresolved": "depth"}


def test_resolve_keeps_siblings_and_unescapes_pointers():
    schema = {"paths": {}, "definitions": {"a/b": {"type": "string"}}}
    assert schemas.resolve({"$ref": "#/definitions/a~1b", "description": "d"}, schema) == {
        "x-jamfpy-ref": "#/definitions/a~1b", "type": "string", "description": "d"
    }
    assert schemas.resolve({"$ref": "other.json#/x"}, schema) == {"$ref": "other.json#/x", "x-jamfpy-unresolved": "missing"}


def test_path_raises_on_an_unknown_path_with_close_matches():
    with pytest.raises(schemas.SchemaError, match=r"the pro schema has no path /v1/script; closest: /v1/scripts"):
        schemas.path("pro", "/v1/script", schema=OPENAPI)
    with pytest.raises(schemas.SchemaError, match=r"no path /zzz$"):
        schemas.path("pro", "/zzz", schema=OPENAPI)


def test_path_reports_supplement_markers():
    schema = schemas.merge_supplement(copy.deepcopy(OPENAPI), {"paths": {
        "/v1/retry": {"x-jamfpy-source": "options-probe", "x-jamfpy-probe": "allow-header-missing", "post": {}},
    }})
    assert schemas.path("pro", "/v1/retry", schema=schema) == {
        "api": "pro", "path": "/v1/retry", "x-jamfpy-source": "options-probe", "x-jamfpy-probe": "allow-header-missing",
        "methods": {"post": {"parameters": []}},
    }


# Pull


def test_pull_from_a_local_path(tmp_path):
    file = write_json(tmp_path / "schema.json", OPENAPI)
    assert schemas.pull("pro", str(file)) == OPENAPI


def test_pull_pro_decodes_utf8_whatever_the_charset_header_says(mocked_responses):
    url = f"{FQDN}/api/schema/"
    body = json.dumps({"openapi": "3.0.1", "info": {"description": "Café – naïve"}, "paths": {}}, ensure_ascii=False).encode("utf-8")
    mocked_responses.get(url, body=body, content_type="application/json;charset=ISO-8859-1")
    assert schemas.pull("pro", url)["info"]["description"] == "Café – naïve"


def test_pull_classic_yaml_writes_valid_json(mocked_responses, tmp_path):
    url = f"{FQDN}/classicapi/doc/swagger.yaml"
    mocked_responses.get(url, body=CLASSIC_YAML.encode("utf-8"), content_type=None)
    file = tmp_path / "classic.json"
    schemas.save(schemas.pull("classic", url), file)
    text = file.read_text(encoding="utf-8")
    assert text.endswith("}\n")
    saved = json.loads(text)
    # Source order, not sorted: /patchexternalsources comes first in the YAML.
    assert list(saved["paths"]) == ["/patchexternalsources/id/{id}", "/computers"]
    assert list(saved["paths"]["/patchexternalsources/id/{id}"]) == ["delete", "get"]
    assert saved["paths"]["/computers"]["get"]["x-deprecation-date"] == "2025-02-11"
    assert text.startswith('{\n  "swagger": "2.0",\n')


def test_save_writes_datetimes_as_iso_and_refuses_other_types(tmp_path):
    file = tmp_path / "out.json"
    schemas.save({"paths": {}, "when": dt.datetime(2025, 2, 11, 10, 0, tzinfo=dt.UTC)}, file)
    assert json.loads(file.read_text(encoding="utf-8"))["when"] == "2025-02-11T10:00:00+00:00"
    with pytest.raises(TypeError, match="set is not JSON serialisable"):
        schemas.save({"paths": {}, "bad": {1}}, file)


def test_pull_raises_schema_error_on_http_failure(mocked_responses):
    url = f"{FQDN}/api/schema/"
    mocked_responses.get(url, status=503)
    with pytest.raises(schemas.SchemaError, match=r"could not fetch .*/api/schema/: 503"):
        schemas.pull("pro", url)


def test_pull_raises_schema_error_on_a_body_that_is_not_a_schema(mocked_responses, tmp_path):
    url = f"{FQDN}/api/schema/"
    mocked_responses.get(url, body=b"<html>login</html>", content_type="text/html")
    with pytest.raises(schemas.SchemaError, match="could not parse the pro schema"):
        schemas.pull("pro", url)
    (tmp_path / "bad.yaml").write_text("paths: [unclosed\n", encoding="utf-8")
    with pytest.raises(schemas.SchemaError, match="could not parse the classic schema") as excinfo:
        schemas.pull("classic", str(tmp_path / "bad.yaml"))
    assert "\n" not in str(excinfo.value)
    (tmp_path / "list.yaml").write_text("- a\n- b\n", encoding="utf-8")
    with pytest.raises(schemas.SchemaError, match="no 'paths' object"):
        schemas.pull("classic", str(tmp_path / "list.yaml"))


def test_pull_raises_schema_error_for_a_missing_local_file(tmp_path):
    with pytest.raises(schemas.SchemaError, match="could not read .*nope.json"):
        schemas.pull("pro", str(tmp_path / "nope.json"))


@pytest.mark.parametrize("fqdn", ["acme.jamfcloud.com", "http://acme.jamfcloud.com/", "HTTPS://acme.jamfcloud.com", " acme.jamfcloud.com/ "])
def test_default_source_builds_https_urls_from_the_fqdn(fqdn):
    env = {"JAMFPRO_INSTANCE_FQDN": fqdn}
    assert schemas.default_source("pro", env) == "https://acme.jamfcloud.com/api/schema/"
    assert schemas.default_source("classic", env) == "https://acme.jamfcloud.com/classicapi/doc/swagger.yaml"


def test_default_source_prefers_the_override():
    env = {"JAMFPRO_INSTANCE_FQDN": "acme.jamfcloud.com", "JAMFPY_CLASSIC_SCHEMA_SOURCE": "/tmp/classic.yaml"}
    assert schemas.default_source("classic", env) == "/tmp/classic.yaml"
    assert schemas.default_source("pro", env) == "https://acme.jamfcloud.com/api/schema/"


@pytest.mark.usefixtures("no_schema_env")
def test_default_source_without_fqdn_or_override_says_what_to_set():
    with pytest.raises(schemas.SchemaError) as excinfo:
        schemas.default_source("pro")
    assert str(excinfo.value) == (
        "no source for the pro schema: set JAMFPRO_INSTANCE_FQDN (copy .env.example to .env) or JAMFPY_PRO_SCHEMA_SOURCE"
    )


# Probe


RETRY = "/v1/app-installers/deployments/{id}/computers/installation-retry"
PROBE_INPUT = {
    "paths": {
        "/v1/app-installers": {"x-jamfpy-source": "options-probe", "get": {}},
        "/v1/app-installers/deployments/{id}": {"get": {}},
        RETRY: {"x-jamfpy-source": "options-probe", "post": {}},
    }
}


def register_probe_answers(mocked_responses):
    base = f"{FQDN}/api/v1/app-installers"
    mocked_responses.add(responses.OPTIONS, base, headers={"Allow": "GET,HEAD,OPTIONS"})
    mocked_responses.add(responses.OPTIONS, f"{base}/deployments/0", headers={"Allow": "PUT, GET, HEAD, DELETE, OPTIONS"})
    # No Allow header at all, as the installation-retry route has answered before.
    mocked_responses.add(responses.OPTIONS, f"{base}/deployments/0/computers/installation-retry")


def test_probe_reads_verbs_from_the_allow_header(tenant, mocked_responses):
    register_probe_answers(mocked_responses)
    probed = schemas.probe(PROBE_INPUT, tenant, now=NOW)
    id_param = [{"name": "id", "in": "path", "required": True, "schema": {"type": "string"}}]
    assert probed["paths"] == {
        "/v1/app-installers": {"x-jamfpy-source": "options-probe", "get": {}},
        "/v1/app-installers/deployments/{id}": {
            "x-jamfpy-source": "options-probe", "parameters": id_param, "get": {}, "put": {}, "delete": {},
        },
        RETRY: {"x-jamfpy-source": "options-probe", "x-jamfpy-probe": "allow-header-missing", "parameters": id_param, "post": {}},
    }
    generated = probed["x-jamfpy-generated"]
    assert generated["generatedAt"] == "2026-10-15T12:00:00+00:00"
    assert "Allow header" in generated["method"]
    assert "verbs are always probed, never typed" in generated["note"]


def test_probe_sends_options_through_the_sdk_with_the_token(tenant, mocked_responses):
    register_probe_answers(mocked_responses)
    schemas.probe(PROBE_INPUT, tenant, now=NOW)
    sent = [call.request for call in mocked_responses.calls]
    assert [request.method for request in sent] == ["OPTIONS"] * 3
    assert all(request.headers["Authorization"] == f"Bearer {FAKE_TOKEN}" for request in sent)
    assert all(request.headers["User-Agent"].startswith("jamfpy/") for request in sent)


def test_probe_keeps_the_stamp_when_the_paths_are_unchanged(tenant, mocked_responses, tmp_path):
    register_probe_answers(mocked_responses)
    first = schemas.probe(PROBE_INPUT, tenant, now=NOW)
    register_probe_answers(mocked_responses)
    again = schemas.probe(first, tenant, now=NOW + dt.timedelta(hours=1))
    assert again["x-jamfpy-generated"]["generatedAt"] == "2026-10-15T12:00:00+00:00"
    assert again == first
    schemas.save(first, tmp_path / "first.json")
    schemas.save(again, tmp_path / "again.json")
    assert (tmp_path / "again.json").read_bytes() == (tmp_path / "first.json").read_bytes()


def test_probe_moves_the_stamp_when_a_verb_or_a_path_changes(tenant, mocked_responses):
    register_probe_answers(mocked_responses)
    first = schemas.probe(PROBE_INPUT, tenant, now=NOW)
    later = NOW + dt.timedelta(hours=1)
    # A new verb on one path.
    base = f"{FQDN}/api/v1/app-installers"
    mocked_responses.add(responses.OPTIONS, base, headers={"Allow": "GET,POST,HEAD,OPTIONS"})
    mocked_responses.add(responses.OPTIONS, f"{base}/deployments/0", headers={"Allow": "PUT, GET, HEAD, DELETE, OPTIONS"})
    mocked_responses.add(responses.OPTIONS, f"{base}/deployments/0/computers/installation-retry")
    assert schemas.probe(first, tenant, now=later)["x-jamfpy-generated"]["generatedAt"] == "2026-10-15T13:00:00+00:00"
    # A path the probe never saw before.
    register_probe_answers(mocked_responses)
    mocked_responses.add(responses.OPTIONS, f"{base}/titles", headers={"Allow": "GET,HEAD,OPTIONS"})
    grown = {"paths": {**first["paths"], "/v1/app-installers/titles": {}}, "x-jamfpy-generated": first["x-jamfpy-generated"]}
    assert schemas.probe(grown, tenant, now=later)["x-jamfpy-generated"]["generatedAt"] == "2026-10-15T13:00:00+00:00"


def test_probe_raises_on_an_error_status(tenant, mocked_responses):
    mocked_responses.add(responses.OPTIONS, f"{FQDN}/api/v1/app-installers", status=404)
    with pytest.raises(schemas.SchemaError, match=r"OPTIONS .*/api/v1/app-installers returned 404"):
        schemas.probe({"paths": {"/v1/app-installers": {}}}, tenant)


def test_probe_raises_when_no_verbs_are_known(tenant, mocked_responses):
    mocked_responses.add(responses.OPTIONS, f"{FQDN}/api/v1/app-installers")
    with pytest.raises(schemas.SchemaError, match="found no verbs for /v1/app-installers"):
        schemas.probe({"paths": {"/v1/app-installers": {}}}, tenant)


def test_probe_raises_for_a_path_without_a_version(tenant):
    with pytest.raises(schemas.SchemaError, match="has no /v<n> version prefix"):
        schemas.probe({"paths": {"/app-installers": {"get": {}}}}, tenant)


def test_tenant_from_env_names_the_missing_variables(no_schema_env):
    no_schema_env.setenv("JAMFPRO_INSTANCE_FQDN", "acme.jamfcloud.com")
    with pytest.raises(schemas.SchemaError, match=r"^the probe needs JAMFPRO_CLIENT_ID, JAMFPRO_CLIENT_SECRET set"):
        schemas.tenant_from_env()


# Drift


OLD = {"paths": {"/a": {"get": {}}, "/b": {"get": {}}, "/c": {"get": {"summary": "x"}}, "/d": {"get": {}, "post": {}}}}
NEW = {"paths": {"/a": {"get": {}}, "/c": {"get": {"summary": "y"}}, "/d": {"post": {}, "put": {}}, "/e": {"get": {}, "delete": {}}}}


def test_drift_finds_added_removed_and_changed_paths():
    added, removed, changed = schemas.drift("pro", NEW, OLD)
    assert added == ["/e"]
    assert removed == ["/b"]
    assert changed == ["/c", "/d"]


def test_drift_ignores_key_order():
    reordered = {"paths": {"/d": {"post": {}, "get": {}}, "/a": {"get": {}}, "/b": {"get": {}}, "/c": {"get": {"summary": "x"}}}}
    assert schemas.drift("pro", reordered, OLD) == schemas.Drift([], [], [])


def test_drift_treats_a_stray_classic_verb_as_its_proper_spelling():
    assert schemas.drift("classic", {"paths": {"/a": {"delete": {}}}}, {"paths": {"/a": {" delete": {}}}}).changed == []
    assert schemas.drift("pro", {"paths": {"/a": {"delete": {}}}}, {"paths": {"/a": {" delete": {}}}}).changed == ["/a"]


def test_drift_summary_text():
    assert schemas.drift_summary("pro", NEW, OLD) == "\n".join([
        "pro: 4 -> 4 paths (1 added, 1 removed, 2 changed)",
        "  + /e  [delete get]",
        "  - /b  [get]",
        "  ~ /c  (differs in get)",
        "  ~ /d  (verbs get post -> post put; differs in get, put)",
    ])


DEFS_OLD = {"paths": {}, "components": {"schemas": {"A": {"type": "string"}, "B": {"type": "object"}, "C": {"a": 1, "b": 2}}}}
DEFS_NEW = {"paths": {}, "components": {"schemas": {"A": {"type": "string"}, "C": {"b": 2, "a": 3}, "D": {"type": "integer"}}}}


def test_definitions_drift_finds_added_removed_and_changed_pro_schemas():
    assert schemas.definitions_drift("pro", DEFS_NEW, DEFS_OLD) == schemas.Drift(added=["D"], removed=["B"], changed=["C"])


def test_definitions_drift_reads_classic_definitions():
    old = {"paths": {}, "definitions": {"A": {"type": "string"}, "B": {}}}
    new = {"paths": {}, "definitions": {"A": {"type": "integer"}, "C": {}}}
    assert schemas.definitions_drift("classic", new, old) == schemas.Drift(added=["C"], removed=["B"], changed=["A"])
    # Pro's container is components.schemas; a Classic-shaped schema has none there.
    assert schemas.definitions_drift("pro", new, old) == schemas.Drift([], [], [])


def test_definitions_drift_ignores_key_order_and_treats_a_missing_container_as_empty():
    reordered = {"paths": {}, "components": {"schemas": {"A": {"type": "string"}, "B": {"type": "object"}, "C": {"b": 2, "a": 1}}}}
    assert schemas.definitions_drift("pro", reordered, DEFS_OLD) == schemas.Drift([], [], [])
    assert schemas.definitions_drift("pro", DEFS_OLD, {"paths": {}}) == schemas.Drift(["A", "B", "C"], [], [])


def test_drift_summary_counts_and_names_the_definitions():
    assert schemas.drift_summary("pro", DEFS_NEW, DEFS_OLD) == "\n".join([
        "pro: 0 -> 0 paths (0 added, 0 removed, 0 changed); 3 -> 3 schemas (1 added, 1 removed, 1 changed)",
        "  schemas + D",
        "  schemas - B",
        "  schemas ~ C",
    ])
    assert schemas.drift_summary("pro", OPENAPI, OPENAPI) == (
        "pro: 4 -> 4 paths (0 added, 0 removed, 0 changed); 4 -> 4 schemas (0 added, 0 removed, 0 changed)"
    )


def test_drift_summary_reports_definitions_when_only_one_side_has_them():
    old = {"paths": {}}
    assert schemas.drift_summary("pro", DEFS_NEW, old).splitlines()[0] == (
        "pro: 0 -> 0 paths (0 added, 0 removed, 0 changed); 0 -> 3 schemas (3 added, 0 removed, 0 changed)"
    )
    assert schemas.drift_summary("pro", old, DEFS_NEW).splitlines()[0].endswith("3 -> 0 schemas (0 added, 3 removed, 0 changed)")


def test_drift_summary_lists_at_most_twenty_names_per_kind():
    new = {"paths": {}, "definitions": {f"S{i:02d}": {} for i in range(23)}}
    lines = schemas.drift_summary("classic", new, {"paths": {}, "definitions": {}}).splitlines()
    assert lines[0] == "classic: 0 -> 0 paths (0 added, 0 removed, 0 changed); 0 -> 23 schemas (23 added, 0 removed, 0 changed)"
    assert lines[1] == "  schemas + " + ", ".join(f"S{i:02d}" for i in range(20)) + ", \u2026 and 3 more"
    assert len(lines) == 2


def test_drift_summary_without_definitions_on_either_side_has_no_schemas_clause():
    assert "schemas" not in schemas.drift_summary("pro", NEW, OLD)


def test_drift_summary_label_and_no_changes():
    assert schemas.drift_summary("pro", OLD, OLD, label="pro-supplement") == "pro-supplement: 4 -> 4 paths (0 added, 0 removed, 0 changed)"


# CLI


def run_cli(*args):
    return subprocess.run([sys.executable, "-m", "tools.schemas", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=False)


def test_cli_paths_smoke_on_the_committed_schemas():
    result = run_cli("paths", "--api", "pro", "--match", "scripts")
    assert result.returncode == 0, result.stderr
    rows = {}
    for line in result.stdout.splitlines():
        key, *rest = line.split()
        # A supplement path is followed by a [marker] list after its verbs.
        rows[key] = [word for word in rest if not word.startswith("[") and not word.endswith("]")]
    assert "/v1/scripts" in rows
    assert all(row and set(row) <= set(schemas.HTTP_VERBS) for row in rows.values())


@pytest.mark.parametrize(("api", "key", "needs_body"), [("pro", "/v1/scripts", True), ("classic", "/buildings/id/{id}", False)])
def test_cli_path_smoke_on_the_committed_schemas(api, key, needs_body):
    result = run_cli("path", "--api", api, key)
    assert result.returncode == 0, result.stderr
    described = json.loads(result.stdout)
    assert (described["api"], described["path"]) == (api, key)
    assert described["methods"]
    assert set(described["methods"]) <= set(schemas.HTTP_VERBS)
    bodies = [method["requestBody"] for method in described["methods"].values() if "requestBody" in method]
    assert bool(bodies) or not needs_body
    assert all(set(body) == {"required", "contentTypes", "schema"} for body in bodies)


@pytest.mark.usefixtures("no_schema_env")
def test_cli_pull_without_a_source_fails_with_one_line(schema_dir, capsys):
    assert schemas.main(["pull"]) == 1
    err = capsys.readouterr().err
    assert err == (
        "schemas: no source for the pro schema: set JAMFPRO_INSTANCE_FQDN (copy .env.example to .env) or JAMFPY_PRO_SCHEMA_SOURCE\n"
    )
    assert not list(schema_dir.iterdir())


def test_cli_pull_writes_both_schemas_and_prints_drift(no_schema_env, schema_dir, tmp_path_factory, capsys):
    sources = tmp_path_factory.mktemp("sources")
    no_schema_env.setenv("JAMFPY_PRO_SCHEMA_SOURCE", str(write_json(sources / "pro.json", OPENAPI)))
    (sources / "classic.yaml").write_text(CLASSIC_YAML, encoding="utf-8")
    no_schema_env.setenv("JAMFPY_CLASSIC_SCHEMA_SOURCE", str(sources / "classic.yaml"))
    write_json(schema_dir / "pro.json", {"paths": {"/v1/scripts": OPENAPI["paths"]["/v1/scripts"], "/v1/gone": {"get": {}}}})
    write_json(schema_dir / "pro-supplement.json", SUPPLEMENT)

    assert schemas.main(["pull"]) == 0
    out = capsys.readouterr().out
    assert "pro: 2 -> 4 paths (3 added, 1 removed, 0 changed); 0 -> 4 schemas (4 added, 0 removed, 0 changed)\n" in out
    assert "  schemas + Category, Child, Parent, Script" in out
    assert "  - /v1/gone  [get]" in out
    assert "classic: 0 -> 2 paths (2 added, 0 removed, 0 changed)" in out
    assert json.loads((schema_dir / "pro.json").read_text(encoding="utf-8")) == OPENAPI
    assert list(schemas.load_classic(schema_dir)["paths"]) == ["/patchexternalsources/id/{id}", "/computers"]
    # The supplement is the probe's file; pull leaves it alone.
    assert json.loads((schema_dir / "pro-supplement.json").read_text(encoding="utf-8")) == SUPPLEMENT


def digests(directory):
    return {file.name: hashlib.sha256(file.read_bytes()).hexdigest() for file in sorted(directory.iterdir())}


def test_cli_pull_with_api_pro_touches_only_the_pro_schema(no_schema_env, schema_dir, tmp_path_factory, capsys):
    # No classic source is set, so a pull that reached for the Classic schema would fail.
    no_schema_env.setenv("JAMFPY_PRO_SCHEMA_SOURCE", str(write_json(tmp_path_factory.mktemp("sources") / "pro.json", OPENAPI)))
    write_json(schema_dir / "classic.json", {"paths": {"/old": {"get": {}}}})
    classic_before = (schema_dir / "classic.json").read_bytes()

    assert schemas.main(["pull", "--api", "pro"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("pro: pulled from ")
    assert "classic" not in out
    assert json.loads((schema_dir / "pro.json").read_text(encoding="utf-8")) == OPENAPI
    assert (schema_dir / "classic.json").read_bytes() == classic_before


def test_cli_pull_writes_nothing_when_the_classic_fetch_fails(no_schema_env, schema_dir, tmp_path_factory, capsys):
    sources = tmp_path_factory.mktemp("sources")
    no_schema_env.setenv("JAMFPY_PRO_SCHEMA_SOURCE", str(write_json(sources / "pro.json", OPENAPI)))
    no_schema_env.setenv("JAMFPY_CLASSIC_SCHEMA_SOURCE", str(sources / "missing.yaml"))
    write_json(schema_dir / "pro.json", {"paths": {"/v1/gone": {"get": {}}}})
    before = digests(schema_dir)

    assert schemas.main(["pull"]) == 1
    assert capsys.readouterr().err.startswith("schemas: could not read ")
    assert digests(schema_dir) == before


@pytest.mark.usefixtures("no_schema_env")
def test_cli_drift_prints_without_writing(schema_dir, tmp_path_factory, capsys):
    source = write_json(tmp_path_factory.mktemp("sources") / "pro.json", OPENAPI)
    write_json(schema_dir / "pro.json", {"paths": {"/v1/scripts": OPENAPI["paths"]["/v1/scripts"]}})
    before = (schema_dir / "pro.json").read_text(encoding="utf-8")
    assert schemas.main(["drift", "--api", "pro", "--source", str(source)]) == 0
    assert capsys.readouterr().out.startswith("pro: 1 -> 4 paths (3 added, 0 removed, 0 changed); 0 -> 4 schemas (4 added, 0 removed, 0 changed)\n")
    assert (schema_dir / "pro.json").read_text(encoding="utf-8") == before


def test_cli_probe_rewrites_the_supplement_through_a_tenant_from_env(no_schema_env, schema_dir, mocked_responses, capsys):
    no_schema_env.setenv("JAMFPRO_INSTANCE_FQDN", "test.jamfcloud.com")
    no_schema_env.setenv("JAMFPRO_CLIENT_ID", "test-client-id")
    no_schema_env.setenv("JAMFPRO_CLIENT_SECRET", "test-client-secret")
    write_json(schema_dir / "pro-supplement.json", PROBE_INPUT)
    register_oauth_token(mocked_responses)
    register_probe_answers(mocked_responses)
    mocked_responses.post(f"{FQDN}/api/v1/auth/invalidate-token", status=204)

    assert schemas.main(["probe"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("pro-supplement: 3 -> 3 paths (0 added, 0 removed, 2 changed)\n")
    written = json.loads((schema_dir / "pro-supplement.json").read_text(encoding="utf-8"))
    assert written["paths"][RETRY]["x-jamfpy-probe"] == "allow-header-missing"
    assert list(written) == ["x-jamfpy-generated", "paths"]


def test_cli_probe_reports_an_auth_failure_in_one_line(no_schema_env, schema_dir, mocked_responses, capsys):
    no_schema_env.setenv("JAMFPRO_INSTANCE_FQDN", "test.jamfcloud.com")
    no_schema_env.setenv("JAMFPRO_CLIENT_ID", "test-client-id")
    no_schema_env.setenv("JAMFPRO_CLIENT_SECRET", "test-client-secret")
    write_json(schema_dir / "pro-supplement.json", PROBE_INPUT)
    mocked_responses.post(f"{FQDN}/api/oauth/token", status=401, json={"error": "invalid_client"})

    assert schemas.main(["probe"]) == 1
    err = capsys.readouterr().err
    assert err.startswith("schemas: probe failed: ")
    assert err.count("\n") == 1
    assert json.loads((schema_dir / "pro-supplement.json").read_text(encoding="utf-8")) == PROBE_INPUT


def test_cli_probe_reports_a_non_2xx_options_answer_and_writes_nothing(no_schema_env, schema_dir, mocked_responses, capsys):
    set_probe_credentials(no_schema_env)
    write_json(schema_dir / "pro-supplement.json", PROBE_INPUT)
    before = digests(schema_dir)
    register_oauth_token(mocked_responses)
    mocked_responses.add(responses.OPTIONS, f"{FQDN}/api/v1/app-installers", status=403)
    mocked_responses.post(f"{FQDN}/api/v1/auth/invalidate-token", status=204)

    assert schemas.main(["probe"]) == 1
    err = capsys.readouterr().err
    assert err.startswith("schemas: OPTIONS ")
    assert err.endswith("/api/v1/app-installers returned 403\n")
    assert err.count("\n") == 1
    assert digests(schema_dir) == before


def set_probe_credentials(monkeypatch):
    monkeypatch.setenv("JAMFPRO_INSTANCE_FQDN", "test.jamfcloud.com")
    monkeypatch.setenv("JAMFPRO_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("JAMFPRO_CLIENT_SECRET", "test-client-secret")


@pytest.fixture
def refresh_setup(no_schema_env, schema_dir, tmp_path_factory):
    """Local schema sources, a committed copy of all three files to compare against, and no credentials yet."""
    sources = tmp_path_factory.mktemp("sources")
    no_schema_env.setenv("JAMFPY_PRO_SCHEMA_SOURCE", str(write_json(sources / "pro.json", OPENAPI)))
    (sources / "classic.yaml").write_text(CLASSIC_YAML, encoding="utf-8")
    no_schema_env.setenv("JAMFPY_CLASSIC_SCHEMA_SOURCE", str(sources / "classic.yaml"))
    write_json(schema_dir / "pro.json", {"paths": {"/v1/gone": {"get": {}}}})
    write_json(schema_dir / "classic.json", {"paths": {"/old": {"get": {}}}})
    write_json(schema_dir / "pro-supplement.json", PROBE_INPUT)
    return sources


@pytest.mark.usefixtures("refresh_setup")
def test_cli_refresh_without_credentials_fails_before_writing_anything(schema_dir, mocked_responses, capsys):
    before = digests(schema_dir)

    assert schemas.main(["refresh"]) == 1
    assert capsys.readouterr().err == (
        "schemas: the probe needs JAMFPRO_INSTANCE_FQDN, JAMFPRO_CLIENT_ID, JAMFPRO_CLIENT_SECRET set (copy .env.example to .env)\n"
    )
    assert digests(schema_dir) == before
    assert not mocked_responses.calls


@pytest.mark.usefixtures("refresh_setup")
def test_cli_refresh_without_a_source_fails_before_writing_anything(schema_dir, no_schema_env, capsys):
    no_schema_env.delenv("JAMFPY_CLASSIC_SCHEMA_SOURCE")
    set_probe_credentials(no_schema_env)
    no_schema_env.delenv("JAMFPRO_INSTANCE_FQDN")
    before = digests(schema_dir)

    assert schemas.main(["refresh"]) == 1
    assert capsys.readouterr().err.startswith("schemas: no source for the classic schema")
    assert digests(schema_dir) == before


@pytest.mark.usefixtures("refresh_setup")
def test_cli_refresh_writes_all_three_files_and_prints_each_drift(schema_dir, no_schema_env, mocked_responses, capsys):
    set_probe_credentials(no_schema_env)
    register_oauth_token(mocked_responses)
    register_probe_answers(mocked_responses)
    mocked_responses.post(f"{FQDN}/api/v1/auth/invalidate-token", status=204)

    assert schemas.main(["refresh"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert [line.split(":")[0] for line in out if not line.startswith(" ")] == ["pro", "pro", "classic", "classic", "pro-supplement"]
    assert json.loads((schema_dir / "pro.json").read_text(encoding="utf-8")) == OPENAPI
    assert list(schemas.load_classic(schema_dir)["paths"]) == ["/patchexternalsources/id/{id}", "/computers"]
    assert json.loads((schema_dir / "pro-supplement.json").read_text(encoding="utf-8"))["paths"][RETRY]["post"] == {}


def test_cli_refresh_writes_nothing_when_a_fetch_fails(refresh_setup, schema_dir, no_schema_env, mocked_responses, capsys):
    set_probe_credentials(no_schema_env)
    no_schema_env.setenv("JAMFPY_CLASSIC_SCHEMA_SOURCE", str(refresh_setup / "missing.yaml"))
    before = digests(schema_dir)

    assert schemas.main(["refresh"]) == 1
    assert capsys.readouterr().err.startswith("schemas: could not read ")
    assert digests(schema_dir) == before
    assert not mocked_responses.calls


@pytest.mark.usefixtures("refresh_setup")
def test_cli_refresh_writes_nothing_when_the_probe_fails(schema_dir, no_schema_env, mocked_responses, capsys):
    set_probe_credentials(no_schema_env)
    before = digests(schema_dir)
    register_oauth_token(mocked_responses)
    mocked_responses.add(responses.OPTIONS, f"{FQDN}/api/v1/app-installers", status=500)
    mocked_responses.post(f"{FQDN}/api/v1/auth/invalidate-token", status=204)

    assert schemas.main(["refresh"]) == 1
    assert capsys.readouterr().err.endswith("/api/v1/app-installers returned 500\n")
    assert digests(schema_dir) == before


def test_cli_paths_marks_supplement_entries(schema_dir, capsys):
    write_json(schema_dir / "pro.json", OPENAPI)
    write_json(schema_dir / "pro-supplement.json", {"paths": {
        "/v1/app-installers": {"x-jamfpy-source": "options-probe", "get": {}},
        RETRY: {"x-jamfpy-source": "options-probe", "x-jamfpy-probe": "allow-header-missing", "post": {}},
    }})
    assert schemas.main(["paths", "--api", "pro", "--match", "app-installers"]) == 0
    assert capsys.readouterr().out.splitlines() == [
        f"{'/v1/app-installers':<{len(RETRY)}}  get  [options-probe]",
        f"{RETRY}  post  [options-probe, allow-header-missing]",
    ]


def test_cli_paths_without_a_match_fails(schema_dir, capsys):
    write_json(schema_dir / "pro.json", OPENAPI)
    assert schemas.main(["paths", "--api", "pro", "--match", "nothing"]) == 1
    assert capsys.readouterr().err == "schemas: no pro path contains 'nothing'\n"


def test_cli_path_prints_json(schema_dir, capsys):
    write_json(schema_dir / "classic.json", SWAGGER)
    assert schemas.main(["path", "--api", "classic", "/buildings"]) == 0
    assert json.loads(capsys.readouterr().out) == {"api": "classic", "path": "/buildings", "methods": {"get": {"parameters": []}}}
