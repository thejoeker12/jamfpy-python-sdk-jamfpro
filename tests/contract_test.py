"""Contract tests: every public endpoint method sends a request whose path and verb are in the API schema.

A test of the whole endpoint surface wired in ``jamfpy/client/client.py``, not of one source module. Nothing is
listed by hand: the endpoints are every ``Endpoint`` instance attribute of ``tenant.classic`` and ``tenant.pro``,
recursing into endpoints that hold endpoints (``classic.accounts.users``), and the methods are every public method
of each bar ``name()``. A newly wired endpoint or method is therefore tested without touching this file, and each
test id names the method (``classic.buildings.get_by_id``, ``pro.mdm.lock_device``).

Each method is called with dummy arguments built from its signature, under a catch-all ``responses`` registration.
Every request it sends is normalised (API base and query string stripped; integer, UUID and ``CONTRACT_ARG``
segments to ``{id}``) and its ``(path, verb)`` must be in the schema (``load_classic()``, or ``load_pro()`` with the
supplement), whose ``{param}`` segments are normalised to ``{id}`` too. The check is that the pair exists, so a valid
verb that is wrong for the method on a path with several verbs is for the per-endpoint unit tests to catch. There is
no allowlist: a method the schema does not back is a bug in the endpoint, and the fix is to correct or remove the
method, never to exempt it here.
"""
# pylint: disable=missing-function-docstring,redefined-outer-name,protected-access
import functools
import inspect
import logging
import re
import typing
from collections.abc import Callable
from types import SimpleNamespace
from urllib.parse import unquote, urlsplit

import pytest
from conftest import FAKE_TOKEN

import jamfpy
from jamfpy.endpoints.models import ClassicEndpoint, Endpoint, ProBase, ProDeleteById, ProGetById, ProUpdateById
from tools.schemas import HTTP_VERBS, load_classic, load_pro, paths

# Bump when wiring an endpoint in client.py; the methods of a new one are tested automatically.
EXPECTED_ENDPOINT_COUNT = 22
KNOWN_ACCESSORS = {
    "classic.buildings", "classic.computers", "classic.policies", "classic.accounts",
    "classic.accounts.users", "classic.accounts.groups",
    "pro.scripts", "pro.mdm", "pro.app_installers", "pro.dock_items",
}

API_BASES = {"classic": "/JSSResource", "pro": "/api"}
WRITE_VERBS = frozenset({"post", "put", "patch"})
# The dummy for every ``str`` parameter. Distinctive so a name-based lookup that puts it in the URL
# (``/accounts/username/<this>``) normalises to ``{id}`` instead of failing the schema check; it is as good a body value.
CONTRACT_ARG = "jamfpy-contract-arg"
# Page 0 of an empty collection, so a paginating get_all stops after one request; every other method ignores it.
EMPTY_PAGE = {"totalCount": 0, "results": []}

_ID_SEGMENT = re.compile(r"\d+|[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}|\{[^/}]+\}")


def discover_endpoints(tenant: jamfpy.Tenant) -> dict[str, Endpoint]:
    """Every endpoint reachable from ``tenant.classic`` and ``tenant.pro``, keyed by dotted accessor."""
    found: dict[str, Endpoint] = {}
    for api in ("classic", "pro"):
        _collect(getattr(tenant, api), api, found)
    return found


def _collect(owner: object, prefix: str, found: dict[str, Endpoint]) -> None:
    for attr, value in vars(owner).items():
        if attr.startswith("_") or not isinstance(value, Endpoint):
            continue
        accessor = f"{prefix}.{attr}"
        found[accessor] = value
        _collect(value, accessor, found)


def public_methods(endpoint: Endpoint) -> list[str]:
    """The endpoint's public callables; ``name()`` is left out because it sends nothing.

    Not only bound methods: a public ``@staticmethod`` or a callable assigned in ``__init__`` can send a request too.
    Nested endpoints are skipped here because ``_collect`` visits them as endpoints in their own right.
    """
    methods = []
    for attr in dir(endpoint):
        if attr.startswith("_") or attr == "name":
            continue
        value = getattr(endpoint, attr)
        if callable(value) and not isinstance(value, Endpoint):
            methods.append(attr)
    return methods


def resolve(tenant: jamfpy.Tenant, accessor: str) -> Endpoint:
    """The endpoint at a dotted accessor such as ``classic.accounts.users``."""
    endpoint: Endpoint = functools.reduce(getattr, accessor.split("."), tenant)
    return endpoint


def dummy_value(param: inspect.Parameter) -> object:
    """A value of the parameter's type that is enough to build the request; a default always wins."""
    if param.default is not inspect.Parameter.empty:
        return param.default
    annotation = param.annotation
    if annotation is bool:
        # No default to take, and False is the value that sends the least.
        return False
    if annotation is int:
        return 1
    if annotation is str:
        return CONTRACT_ARG
    if typing.get_origin(annotation) is list and typing.get_args(annotation) == (str,):
        return [CONTRACT_ARG]
    if typing.get_origin(annotation) is dict:
        return {}
    raise TypeError(f"no dummy value for parameter {param.name!r} annotated {annotation!r}: add one to dummy_value")


def dummy_arguments(method: Callable[..., object]) -> tuple[list[object], dict[str, object]]:
    """Positional and keyword arguments for every parameter of ``method``; ``*args`` and ``**kwargs`` get nothing."""
    args: list[object] = []
    kwargs: dict[str, object] = {}
    for param in inspect.signature(method, eval_str=True).parameters.values():
        if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            continue
        if param.kind is inspect.Parameter.KEYWORD_ONLY:
            kwargs[param.name] = dummy_value(param)
        else:
            args.append(dummy_value(param))
    return args, kwargs


def _is_id_segment(segment: str) -> bool:
    return bool(_ID_SEGMENT.fullmatch(segment)) or unquote(segment) == CONTRACT_ARG


def normalise(path: str) -> str:
    """Every integer, UUID, ``{param}`` or ``CONTRACT_ARG`` segment as ``{id}``, so a sent path and a schema template compare."""
    return "/".join("{id}" if _is_id_segment(segment) else segment for segment in path.split("/"))


def sent_path(url: str, api: str) -> str:
    """A sent URL's path with the API base and query string stripped, normalised."""
    path = urlsplit(url).path
    base = API_BASES[api]
    assert path.startswith(base + "/"), f"{url} is not under the {api} base {base}"
    return normalise(path.removeprefix(base))


def schema_pairs(api: str, schema: dict[str, typing.Any]) -> set[tuple[str, str]]:
    """Every ``(normalised path, verb)`` pair in a schema."""
    return {(normalise(key), verb) for key, verbs in paths(api, schema=schema) for verb in verbs}


# Discovered at collection, on a throwaway Tenant (construction sends nothing), so each method gets its own test id.
_DISCOVERY_TENANT = jamfpy.Tenant(
    fqdn="https://contract.jamfcloud.com",
    auth_method="oauth2",
    client_id="contract-client-id",
    client_secret="contract-client-secret",
    log_level=logging.CRITICAL,
)
DISCOVERED = discover_endpoints(_DISCOVERY_TENANT)
CASES = [(accessor, method) for accessor, endpoint in DISCOVERED.items() for method in public_methods(endpoint)]


@pytest.fixture(scope="module")
def schema():
    """Both schemas' ``(path, verb)`` pairs, read once for the module (pro.json is ~2 MB)."""
    return {"classic": schema_pairs("classic", load_classic()), "pro": schema_pairs("pro", load_pro())}


@pytest.fixture
def traffic(tenant, mocked_responses, monkeypatch):
    """Answer any URL with any verb (a 200 with an empty first page) and record what the endpoints send.

    ``traffic.requests`` holds every ``requests.Request`` handed to ``do()``, so a test can tell ``data=`` from
    ``json=``; ``traffic.calls`` is the ``responses`` call log of what went over the wire.
    """
    # One registration per verb, and a method uses only one or two of them.
    mocked_responses.assert_all_requests_are_fired = False
    for verb in HTTP_VERBS:
        mocked_responses.add(verb.upper(), re.compile(r".*"), json=EMPTY_PAGE)
    recorded = []
    for api in (tenant.classic, tenant.pro):
        def recording_do(request, timeout=None, _do=api.do):
            recorded.append(request)
            return _do(request, timeout=timeout)
        monkeypatch.setattr(api, "do", recording_do)
    return SimpleNamespace(requests=recorded, calls=mocked_responses.calls)


def test_discovery_finds_every_endpoint_client_py_wires(tenant):
    found = discover_endpoints(tenant)
    assert len(found) == EXPECTED_ENDPOINT_COUNT, sorted(found)
    assert KNOWN_ACCESSORS <= set(found), sorted(KNOWN_ACCESSORS - set(found))
    assert set(found) == set(DISCOVERED)


def test_every_discovered_endpoint_has_a_method_to_test():
    assert {accessor for accessor, _ in CASES} == set(DISCOVERED)


@pytest.mark.parametrize(("accessor", "method_name"), CASES, ids=[f"{accessor}.{method}" for accessor, method in CASES])
def test_method_sends_a_path_and_verb_the_schema_has(tenant, traffic, schema, accessor, method_name):
    api = accessor.split(".", 1)[0]
    method = getattr(resolve(tenant, accessor), method_name)
    args, kwargs = dummy_arguments(method)

    method(*args, **kwargs)

    assert traffic.calls, f"{accessor}.{method_name} sent no request"
    assert len(traffic.requests) == len(traffic.calls)
    for request, call in zip(traffic.requests, traffic.calls):
        path, verb = sent_path(call.request.url, api), call.request.method.lower()
        known_verbs = sorted(v for p, v in schema[api] if p == path)
        assert (path, verb) in schema[api], (
            f"{accessor}.{method_name} sent {verb.upper()} {path}, which the {api} schema "
            + (f"has only for {known_verbs}" if known_verbs else "has no path for")
        )
        assert call.request.headers["Authorization"] == f"Bearer {FAKE_TOKEN}"
        if verb in WRITE_VERBS and api == "classic":
            assert isinstance(request.data, str) and request.json is None, "a Classic write sends an XML string as data="
            assert call.request.headers["Content-Type"] == "text/xml"
        elif verb in WRITE_VERBS:
            assert request.json is not None and not request.data, "a Pro write sends its body as json="
            assert call.request.headers["Content-Type"] == "application/json"


def expected_schema_paths(endpoint: Endpoint) -> list[str]:
    """The schema paths an endpoint's ``_uri`` says it targets: the collection, and the by-id path where it has one."""
    if isinstance(endpoint, ProBase):
        collection = f"/v{endpoint._version}{endpoint._uri}"
        by_id = isinstance(endpoint, (ProGetById, ProUpdateById, ProDeleteById))
        return [collection, f"{collection}/{{id}}"] if by_id else [collection]
    by_id_uri = getattr(endpoint, "_by_id_uri", None)
    if by_id_uri is not None:
        return [endpoint._uri, f"{by_id_uri}/{{id}}"]
    if isinstance(endpoint, ClassicEndpoint):
        return [endpoint._uri, f"{endpoint._uri}/id/{{id}}"]
    return [endpoint._uri]


@pytest.mark.parametrize("accessor", sorted(DISCOVERED))
def test_endpoint_uri_targets_paths_in_the_schema(schema, accessor):
    api = accessor.split(".", 1)[0]
    endpoint = DISCOVERED[accessor]
    known = {path for path, _ in schema[api]}
    if api == "pro" and not isinstance(endpoint, ProBase):
        # An action endpoint (pro.mdm) names its version in each method, so any version of its path will do.
        assert any(re.fullmatch(rf"/v\d+{re.escape(endpoint._uri)}", path) for path in known), endpoint._uri
        return
    missing = [path for path in expected_schema_paths(endpoint) if normalise(path) not in known]
    assert not missing, f"{accessor}: not in the {api} schema: {missing}"


@pytest.mark.parametrize(("url", "api", "expected"), [
    (f"https://t.jamfcloud.com/JSSResource/accounts/username/{CONTRACT_ARG}", "classic", "/accounts/username/{id}"),
    # Percent-encoded, as an endpoint that quotes its path argument would send it.
    ("https://t.jamfcloud.com/JSSResource/accounts/username/jamfpy%2Dcontract%2Darg", "classic", "/accounts/username/{id}"),
    (f"https://t.jamfcloud.com/JSSResource/accounts/username/{CONTRACT_ARG}?x=1", "classic", "/accounts/username/{id}"),
    ("https://t.jamfcloud.com/JSSResource/buildings/id/1", "classic", "/buildings/id/{id}"),
    ("https://t.jamfcloud.com/JSSResource/accounts/userid/0", "classic", "/accounts/userid/{id}"),
    ("https://t.jamfcloud.com/api/v1/things/123e4567-e89b-12d3-a456-426614174000", "pro", "/v1/things/{id}"),
    # Only the sentinel is exempt: any other string segment is part of the path and must match the schema.
    ("https://t.jamfcloud.com/JSSResource/buildings/frob", "classic", "/buildings/frob"),
    ("https://t.jamfcloud.com/JSSResource/accounts/username/x", "classic", "/accounts/username/x"),
])
def test_sent_path_normalises_ids_and_the_contract_sentinel(url, api, expected):
    assert sent_path(url, api) == expected


def test_normalise_maps_schema_params_to_id():
    assert normalise("/v1/things/{thingId}/children/{childId}") == "/v1/things/{id}/children/{id}"
