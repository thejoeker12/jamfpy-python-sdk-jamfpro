"""Shared machinery for the live integration suite.

Each resource is described by a small spec dict (see the *_live_test.py files);
the two runners below walk the full create → read → update → read → delete → 404
cycle for any spec. Not a test module (``*_test.py`` naming), so pytest never
collects it directly.
"""
import functools
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

from requests import Response


def resolve_accessor(api, dotted: str):
    """Resolve a dotted accessor like ``accounts.users`` on a ProAPI/ClassicAPI."""
    return functools.reduce(getattr, dotted.split("."), api)


def id_from_xml(resp: Response) -> int:
    """Extract the integer id from a Classic create/read XML body."""
    return int(ET.fromstring(resp.text).findtext("id"))


def xml_from_dict(tag: str, value) -> str:
    """Render a (possibly nested) dict as Classic API XML.

    Booleans become ``true``/``false``; text is XML-escaped (config-profile
    payload plists embed raw XML that must survive the trip).
    """
    if isinstance(value, dict):
        inner = "".join(xml_from_dict(k, v) for k, v in value.items())
        return f"<{tag}>{inner}</{tag}>"
    if isinstance(value, bool):
        return f"<{tag}>{str(value).lower()}</{tag}>"
    return f"<{tag}>{escape(str(value))}</{tag}>"


def strip_keys(value, keys):
    """Deep-copy a nested dict, dropping any key named in ``keys`` at any depth."""
    if not isinstance(value, dict):
        return value
    return {k: strip_keys(v, keys) for k, v in value.items() if k not in keys}


def assert_subset(expected: dict, actual: dict, path: str = ""):
    """Assert every expected key round-tripped; the server may add extra keys."""
    for key, value in expected.items():
        assert key in actual, f"{path}{key}: missing from response ({sorted(actual)})"
        if isinstance(value, dict):
            assert_subset(value, actual[key], f"{path}{key}.")
        else:
            assert actual[key] == value, f"{path}{key}: sent {value!r}, got {actual[key]!r}"


def run_classic_lifecycle(api, spec: dict, build, name: str, janitor: list):
    """Full lifecycle for one Classic resource: XML writes, JSON reads.

    ``build`` is the spec's min or max payload builder; the update phase re-runs
    it with a mutated name, so name-derived fields change too (a real update,
    not just a rename). Classic status codes: create/update 201, delete 200.
    """
    endpoint = resolve_accessor(api, spec["accessor"])
    root = spec["root"]
    read_key = spec.get("read_key", root)
    drop = spec.get("unassertable", ())

    payload = build(name)
    create = endpoint.create(xml_from_dict(root, payload))
    assert create.status_code == 201, f"create: {create.status_code} {create.text}"
    rid = id_from_xml(create)
    janitor.append((endpoint, rid, (200, 404)))

    read = endpoint.get_by_id(rid)
    assert read.status_code == 200, f"read: {read.status_code} {read.text}"
    assert_subset(strip_keys(payload, drop), read.json()[read_key])

    updated = build(name + "-upd")
    update = endpoint.update_by_id(rid, xml_from_dict(root, updated))
    assert update.status_code == 201, f"update: {update.status_code} {update.text}"

    reread = endpoint.get_by_id(rid)
    assert reread.status_code == 200, f"re-read: {reread.status_code} {reread.text}"
    assert_subset(strip_keys(updated, drop), reread.json()[read_key])

    delete = endpoint.delete_by_id(rid)
    assert delete.status_code == 200, f"delete: {delete.status_code} {delete.text}"
    assert endpoint.get_by_id(rid).status_code == 404, "resource still readable after delete"


def run_pro_lifecycle(api, spec: dict, build, name: str, janitor: list):
    """Full lifecycle for one Pro resource: JSON both ways.

    Pro returns ``id`` as a JSON string — it is passed back verbatim and
    compared as returned. Status codes: create 201, update 200, delete 204.
    """
    endpoint = resolve_accessor(api, spec["accessor"])
    drop = spec.get("unassertable", ())

    payload = build(name)
    create = endpoint.create(payload)
    assert create.status_code == 201, f"create: {create.status_code} {create.text}"
    created = create.json()
    assert "id" in created and "href" in created
    rid = created["id"]
    janitor.append((endpoint, rid, (204, 404)))

    read = endpoint.get_by_id(rid)
    assert read.status_code == 200, f"read: {read.status_code} {read.text}"
    body = read.json()
    assert body["id"] == rid
    assert_subset(strip_keys(payload, drop), body)

    updated = build(name + "-upd")
    update = endpoint.update_by_id(rid, updated)
    assert update.status_code == 200, f"update: {update.status_code} {update.text}"

    reread = endpoint.get_by_id(rid)
    assert reread.status_code == 200, f"re-read: {reread.status_code} {reread.text}"
    assert_subset(strip_keys(updated, drop), reread.json())

    delete = endpoint.delete_by_id(rid)
    assert delete.status_code == 204, f"delete: {delete.status_code} {delete.text}"
    assert endpoint.get_by_id(rid).status_code == 404, "resource still readable after delete"
