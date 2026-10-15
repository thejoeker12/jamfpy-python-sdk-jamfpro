"""Introspection of the wired endpoints, shared by ``tests/contract_test.py`` and ``tools/coverage_doc.py``.

Both call every public endpoint method with dummy arguments built from its signature and look at the request it sends:
the contract test checks each against the API schema, the COVERAGE.md generator records them. The rules for what a
method is, what its dummy arguments are and how a sent path is normalised live here once, so the two cannot drift.

Nothing here talks to a tenant. ``record_requests`` swaps ``do`` on the API instance for a stub that answers every
request itself.
"""
import inspect
import io
import json
import re
import typing
from collections.abc import Callable
from typing import NamedTuple
from urllib.parse import unquote, urlsplit

from requests import Request, Response

from jamfpy import API
from jamfpy.endpoints.models import Endpoint

API_BASES = {"classic": "/JSSResource", "pro": "/api"}
# The dummy for every ``str`` parameter. Distinctive so a name-based lookup that puts it in the URL
# (``/accounts/username/<this>``) normalises to ``{id}`` instead of failing the schema check; it is as good a body value.
CONTRACT_ARG = "jamfpy-contract-arg"
# Page 0 of an empty collection, so a paginating get_all stops after one request; every other method ignores it.
EMPTY_PAGE = {"totalCount": 0, "results": []}

_ID_SEGMENT = re.compile(r"\d+|[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}|\{[^/}]+\}")


class DummyValueError(TypeError):
    """A parameter has a type ``dummy_value`` cannot build a value for."""


class Sent(NamedTuple):
    """One request an endpoint method sent: its lower-case verb and its normalised path (see ``sent_path``)."""

    verb: str
    path: str


def public_methods(endpoint: Endpoint) -> tuple[str, ...]:
    """The endpoint's public callables, sorted; ``name()`` is left out because it sends nothing.

    Not only bound methods: a public ``@staticmethod`` or a callable assigned in ``__init__`` can send a request too.
    Nested endpoints are skipped here because discovery visits them as endpoints in their own right.
    """
    methods = []
    for attr in sorted(dir(endpoint)):
        if attr.startswith("_") or attr == "name":
            continue
        value = getattr(endpoint, attr)
        if callable(value) and not isinstance(value, Endpoint):
            methods.append(attr)
    return tuple(methods)


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
    raise DummyValueError(
        f"no dummy value for parameter {param.name!r} annotated {annotation!r}: add one to dummy_value in tools/introspect.py"
    )


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
    if not path.startswith(base + "/"):
        raise ValueError(f"{url} is not under the {api} base {base}")
    return normalise(path.removeprefix(base))


class _Recorder:
    """Stands in for ``API.do``: notes each request and answers it with ``EMPTY_PAGE``."""

    def __init__(self, api: str) -> None:
        self.api = api
        self.sent: list[Sent] = []

    def do(self, request: Request, timeout: object = None) -> Response:
        """Record ``request`` and return a 200 whose JSON body is an empty first page."""
        del timeout
        url = request.url
        if not isinstance(url, str):
            raise ValueError("a request with no URL reached do()")
        self.sent.append(Sent(str(request.method).lower(), sent_path(url, self.api)))
        response = Response()
        response.status_code = 200
        response.url = url
        response.headers["Content-Type"] = "application/json"
        # Read back through .content, so no private attribute of Response is touched.
        response.raw = io.BytesIO(json.dumps(EMPTY_PAGE).encode("utf-8"))
        return response


def record_requests(endpoint: Endpoint, api: str, owner: API) -> dict[str, tuple[Sent, ...]]:
    """Each public method's requests, by method name in ``public_methods`` order: what it sends when called with dummy arguments.

    ``owner`` is the API object the endpoint holds (``api`` names its kind, ``classic`` or ``pro``). Its ``do`` is
    replaced by a stub for each call and put back after, so nothing leaves the process. A method's requests are
    distinct, in the order sent; one that sends nothing maps to ``()``.

    Raises ``DummyValueError`` for a parameter ``dummy_value`` cannot build a value for.
    """
    recorded: dict[str, tuple[Sent, ...]] = {}
    for name in public_methods(endpoint):
        method = getattr(endpoint, name)
        args, kwargs = dummy_arguments(method)
        recorder = _Recorder(api)
        # setattr, not assignment: a method is not assignable as far as the type checker goes, and an instance attribute
        # is what endpoints' ``self._api.do`` finds first.
        setattr(owner, "do", recorder.do)
        try:
            method(*args, **kwargs)
        finally:
            delattr(owner, "do")
        recorded[name] = tuple(dict.fromkeys(recorder.sent))
    return recorded
