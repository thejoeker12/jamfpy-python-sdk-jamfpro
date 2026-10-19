"""Redaction of credentials in headers and bodies, before they reach a log line or an exception message.

``redact()`` replaces the value of an ``Authorization`` header (keeping a ``Bearer`` or ``Basic`` scheme), the whole
value of the headers in ``REDACTED_HEADERS``, and the values of the keys in ``SECRET_KEYS``, all matched
case-insensitively. Keys are found in header mappings, JSON bodies (nested, lists included), form-encoded bodies, XML
elements and raw text. Everything else is left as it was.
"""

import json
import re
from collections.abc import Mapping
from typing import Any, overload

REDACTED = "[redacted]"

# client_id is not a secret on its own, but it is half of the OAuth credential pair and the token request body
# carries it, so it is kept out of logs with the secrets.
SECRET_KEYS = frozenset({"access_token", "token", "client_id", "client_secret", "password"})

# Headers whose whole value is a credential or a session handle. Authorization is not here: its scheme is kept.
REDACTED_HEADERS = frozenset({"proxy-authorization", "x-auth-token", "cookie", "set-cookie"})

_AUTH_SCHEMES = frozenset({"bearer", "basic"})
_KEY_PATTERN = "|".join(sorted(SECRET_KEYS, key=len, reverse=True))
_HEADER_PATTERN = "|".join(sorted(REDACTED_HEADERS, key=len, reverse=True))

_TEXT_PATTERNS = (
    # Cookie: a=b; c=d, also inside quotes ("Set-Cookie": "...") or in a dict repr ({'Cookie': '...'}). Cookie values
    # hold spaces and semicolons, so the value runs to the closing quote, or to the end of the line when unquoted.
    # Groups 2 and 3 hold whichever quote opened the value (the other is empty), so it comes back wrapped as it was.
    # Tried before the Authorization pattern so Proxy-Authorization loses its scheme as well, as it does in a mapping.
    (
        re.compile(
            rf"""(?<![\w-])((?:{_HEADER_PATTERN})["']?[ \t]*:[ \t]*)(?:(")(?:[^"\\]|\\.)*"|(')(?:[^'\\]|\\.)*'|[^\r\n]+)""",
            re.IGNORECASE,
        ),
        rf"\1\2\3{REDACTED}\2\3",
    ),
    # Authorization: Bearer xxx, also inside quotes ("Authorization": "Basic xxx") or as authorization=Bearer xxx.
    (re.compile(r"""(authorization["']?\s*[:=]\s*["']?(?:bearer|basic)\s+)[^\s"',;&]+""", re.IGNORECASE), rf"\1{REDACTED}"),
    # "key": "value", for JSON that did not parse as a whole (a fragment, or JSON embedded in other text).
    (re.compile(rf'("(?:{_KEY_PATTERN})"\s*:\s*)"(?:[^"\\]|\\.)*"', re.IGNORECASE), rf'\1"{REDACTED}"'),
    # key=value, as in a form body or a query string. The lookbehind stops my_token=... matching as token=....
    (re.compile(rf"(?<![\w.-])((?:{_KEY_PATTERN})=)[^&\s]*", re.IGNORECASE), rf"\1{REDACTED}"),
    # <password>value</password>, as in a Classic body. The content is text or a CDATA section, so one linear pass
    # covers it; an empty or self-closing element holds no secret and is left alone, and the backreference keeps
    # <password>x</token> from pairing. Possessive quantifiers keep a large body from building a backtrack stack.
    (
        re.compile(
            rf"(<(?P<tag>{_KEY_PATTERN})(?:\s[^<>]*)?(?<!/)>)(?:[^<]++|<!\[CDATA\[.*?\]\]>)++(</(?P=tag)\s*>)",
            re.IGNORECASE | re.DOTALL,
        ),
        rf"\1{REDACTED}\3",
    ),
)


@overload
def redact(value: None) -> None: ...
@overload
def redact(value: str | bytes) -> str: ...
@overload
def redact(value: Mapping[str, Any]) -> dict[str, Any]: ...


def redact(value: Mapping[str, Any] | str | bytes | None) -> dict[str, Any] | str | None:
    """Return a copy of ``value`` with credentials replaced by ``[redacted]``; the input is never mutated.

    A mapping (headers, or a parsed JSON object) comes back as a new dict. Text comes back as text: a JSON object or
    array is redacted key by key and re-serialised, anything else is matched against the ``"key": "value"``,
    ``key=value``, ``<key>value</key>``, ``Authorization: Bearer xxx`` and ``Cookie: xxx`` patterns. Bytes are
    decoded as UTF-8 (undecodable bytes become U+FFFD) and handled as text. ``None`` stays ``None``.
    """
    if value is None:
        return None
    if isinstance(value, Mapping):
        return _redact_mapping(value)
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    return _redact_text(value)


def _redact_mapping(mapping: Mapping[str, Any]) -> dict[str, Any]:
    return {key: _redact_entry(key, item) for key, item in mapping.items()}


def _redact_entry(key: object, item: object) -> object:
    if isinstance(key, str):
        lowered = key.lower()
        if lowered == "authorization":
            return _redact_authorization(item)
        if lowered in SECRET_KEYS or lowered in REDACTED_HEADERS:
            return REDACTED
    return _redact_structure(item)


def _redact_structure(value: object) -> object:
    if isinstance(value, Mapping):
        return _redact_mapping(value)
    if isinstance(value, list):
        return [_redact_structure(item) for item in value]
    return value


def _redact_authorization(value: object) -> str:
    """``Bearer xxx`` -> ``Bearer [redacted]``; the scheme is kept because it tells a reader which auth was used."""
    if isinstance(value, str):
        scheme, separator, _ = value.partition(" ")
        if separator and scheme.lower() in _AUTH_SCHEMES:
            return f"{scheme} {REDACTED}"
    return REDACTED


def _redact_text(text: str) -> str:
    # Only an object or array can hold a key; text opening with either parses to a dict or a list, or not at all.
    if text.lstrip()[:1] in ("{", "["):
        try:
            parsed = json.loads(text)
        # RecursionError: pathologically deep nesting. Either way the patterns below still apply.
        except (ValueError, RecursionError):
            pass
        else:
            # Parsed rather than pattern-matched, so a secret held as a number, object or list is caught too.
            return json.dumps(_redact_structure(parsed), ensure_ascii=False)

    for pattern, replacement in _TEXT_PATTERNS:
        text = pattern.sub(replacement, text)
    return text
