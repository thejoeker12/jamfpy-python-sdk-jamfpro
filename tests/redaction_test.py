"""Unit tests for jamfpy.client.redaction.redact()."""
# pylint: disable=missing-function-docstring
import copy
import json

import pytest
from requests.structures import CaseInsensitiveDict

from jamfpy.client.redaction import REDACTED, REDACTED_HEADERS, SECRET_KEYS, redact

SECRET = "s3cr3t-VALUE"
# Every spelling a key may arrive in: lower, upper and mixed case.
SECRET_KEY_SPELLINGS = sorted({spelling for key in SECRET_KEYS for spelling in (key, key.upper(), key.title())})
# The same for headers: lower case, upper case and the canonical Set-Cookie / X-Auth-Token form.
REDACTED_HEADER_SPELLINGS = sorted({spelling for name in REDACTED_HEADERS for spelling in (name, name.upper(), name.title())})


# --- mappings --------------------------------------------------------------

@pytest.mark.parametrize("key", SECRET_KEY_SPELLINGS)
def test_secret_key_in_a_mapping_is_redacted(key):
    assert redact({key: SECRET, "accept": "application/json"}) == {key: REDACTED, "accept": "application/json"}


@pytest.mark.parametrize("value, expected", [
    ("Bearer eyJhbGciOi.payload.sig", "Bearer [redacted]"),
    ("Basic dXNlcjpwYXNz", "Basic [redacted]"),
    ("bearer lower-case-scheme", "bearer [redacted]"),
    ("rawtokenwithoutascheme", REDACTED),
    ("Digest username=x", REDACTED),
])
@pytest.mark.parametrize("name", ["Authorization", "authorization", "AUTHORIZATION"])
def test_authorization_header_keeps_only_a_bearer_or_basic_scheme(name, value, expected):
    assert redact({name: value}) == {name: expected}


@pytest.mark.parametrize("name", REDACTED_HEADER_SPELLINGS)
def test_credential_and_session_headers_are_redacted_whole(name):
    value = "JSESSIONID=abc123; Path=/; Secure; HttpOnly, jpro-ingress=def456"
    assert redact({name: value, "Content-Type": "application/json"}) == {name: REDACTED, "Content-Type": "application/json"}


def test_redacted_headers_are_exactly_the_documented_ones():
    assert REDACTED_HEADERS == {"proxy-authorization", "x-auth-token", "cookie", "set-cookie"}


def test_case_insensitive_dict_headers_come_back_as_a_new_plain_dict():
    headers = CaseInsensitiveDict({"Authorization": "Bearer tok", "User-Agent": "jamfpy/1.0"})

    redacted = redact(headers)

    assert type(redacted) is dict  # pylint: disable=unidiomatic-typecheck
    assert redacted == {"Authorization": "Bearer [redacted]", "User-Agent": "jamfpy/1.0"}
    assert headers["Authorization"] == "Bearer tok"


def test_nested_mapping_and_lists_are_redacted_throughout():
    body = {
        "name": "svc",
        "credentials": {"password": SECRET, "hint": "none"},
        "tokens": [{"token": SECRET}, {"note": "keep"}, ["deeper", {"Access_Token": SECRET}]],
        "client_secret": {"structured": SECRET},
    }

    assert redact(body) == {
        "name": "svc",
        "credentials": {"password": REDACTED, "hint": "none"},
        "tokens": [{"token": REDACTED}, {"note": "keep"}, ["deeper", {"Access_Token": REDACTED}]],
        "client_secret": REDACTED,
    }


def test_mapping_input_is_not_mutated():
    body = {"password": SECRET, "nested": {"token": SECRET, "items": [{"client_secret": SECRET}]}}
    original = copy.deepcopy(body)

    redact(body)

    assert body == original


def test_non_string_keys_are_kept():
    assert redact({1: "one", "token": SECRET}) == {1: "one", "token": REDACTED}


@pytest.mark.parametrize("value", [None, b"Bearer abc", 12345])
def test_a_non_string_authorization_value_is_redacted_whole(value):
    assert redact({"Authorization": value}) == {"Authorization": REDACTED}


@pytest.mark.parametrize("key", ["name", "my_token", "token_type", "passwords", "secret", "expires_in", "grant_type"])
def test_non_secret_keys_are_untouched(key):
    assert redact({key: "visible"}) == {key: "visible"}


# --- JSON text -------------------------------------------------------------

def test_json_body_text_is_redacted_key_by_key():
    body = json.dumps({"access_token": SECRET, "token_type": "Bearer", "expires_in": 299, "scope": "api-role:1"})

    assert json.loads(redact(body)) == {"access_token": REDACTED, "token_type": "Bearer", "expires_in": 299, "scope": "api-role:1"}


def test_json_body_redaction_reads_as_access_token_redacted():
    assert redact('{"access_token":"abc","expires_in":299}') == '{"access_token": "[redacted]", "expires_in": 299}'


def test_json_array_body_with_nested_secrets():
    body = json.dumps([{"user": {"Password": SECRET}}, {"list": [{"TOKEN": 12345}]}])

    assert json.loads(redact(body)) == [{"user": {"Password": REDACTED}}, {"list": [{"TOKEN": REDACTED}]}]


def test_json_that_does_not_parse_falls_back_to_the_patterns():
    # Cut off mid-body, as a truncated or streamed response would be: it opens like JSON but won't parse.
    text = '{"access_token": "abc", "expires_in": 299, "scope": "api-ro'
    assert redact(text) == '{"access_token": "[redacted]", "expires_in": 299, "scope": "api-ro'


def test_json_body_keeps_non_ascii_text():
    assert json.loads(redact('{"name": "Café", "password": "x"}')) == {"name": "Café", "password": REDACTED}


# --- form bodies and raw text ----------------------------------------------

def test_form_body_redacts_secret_values_only():
    body = f"grant_type=client_credentials&client_id=my-client&client_secret={SECRET}"
    assert redact(body) == "grant_type=client_credentials&client_id=[redacted]&client_secret=[redacted]"


@pytest.mark.parametrize("key", SECRET_KEY_SPELLINGS)
def test_form_pair_for_each_secret_key(key):
    assert redact(f"a=1&{key}={SECRET}&b=2") == f"a=1&{key}=[redacted]&b=2"


def test_form_pair_needs_the_whole_key():
    assert redact("my_token=keep&x-token=keep&token.v=keep") == "my_token=keep&x-token=keep&token.v=keep"


@pytest.mark.parametrize("text, expected", [
    ("Authorization: Bearer abc.def.ghi", "Authorization: Bearer [redacted]"),
    ("authorization: basic dXNlcjpwYXNz trailing", "authorization: basic [redacted] trailing"),
    ("headers {'Authorization': 'Bearer abc'}", "headers {'Authorization': 'Bearer [redacted]'}"),
    ('sent "Authorization": "Bearer abc", then', 'sent "Authorization": "Bearer [redacted]", then'),
])
def test_authorization_in_raw_text(text, expected):
    assert redact(text) == expected


def test_json_pair_in_raw_text_that_is_not_whole_json():
    # A truncated or embedded fragment does not parse, so the "key": "value" pattern catches it.
    text = 'Error: {"error": "invalid_client", "Password" : "with \\"escaped\\" quote", "client_secret": "x"'
    assert redact(text) == 'Error: {"error": "invalid_client", "Password" : "[redacted]", "client_secret": "[redacted]"'


def test_plain_text_without_secrets_is_unchanged():
    text = "GET https://acme.jamfcloud.com/api/v1/scripts?page=0&page-size=100&sort=id%3Aasc -> 200 (84 ms)"
    assert redact(text) == text


@pytest.mark.parametrize("text, expected", [
    ("Cookie: JSESSIONID=abc; jpro-ingress=def", "Cookie: [redacted]"),
    ("cookie: a=b", "cookie: [redacted]"),
    ("Set-Cookie: JSESSIONID=abc123; Path=/; Secure; HttpOnly", "Set-Cookie: [redacted]"),
    ("SET-COOKIE:jpro-ingress=def; Max-Age=60", "SET-COOKIE:[redacted]"),
    ("Proxy-Authorization: Basic dXNlcjpwYXNz", "Proxy-Authorization: [redacted]"),
    ("Proxy-Authorization: Negotiate YII", "Proxy-Authorization: [redacted]"),
    ("X-Auth-Token: abc.def", "X-Auth-Token: [redacted]"),
    ("{'Cookie': 'a=b; c=d', 'Accept': 'x'}", "{'Cookie': '[redacted]', 'Accept': 'x'}"),
    ('{"Set-Cookie": "JSESSIONID=abc; Path=/", "Accept": "x"', '{"Set-Cookie": "[redacted]", "Accept": "x"'),
    ("Set-Cookie: JSESSIONID=abc\nAccept: text/plain\nCookie: a=b\n", "Set-Cookie: [redacted]\nAccept: text/plain\nCookie: [redacted]\n"),
])
def test_credential_and_session_headers_in_raw_text(text, expected):
    assert redact(text) == expected


@pytest.mark.parametrize("text", [
    "Content-Type: application/json",
    "Cookie-Policy: strict",
    "My-Cookie: keep",
    "Cookie:",
    "X-Auth-Token-Id: keep",
])
def test_other_header_lines_in_raw_text_are_untouched(text):
    assert redact(text) == text


def test_content_type_header_is_untouched_in_a_mapping():
    assert redact({"Content-Type": "application/xml", "Accept": "*/*"}) == {"Content-Type": "application/xml", "Accept": "*/*"}


# --- XML bodies ------------------------------------------------------------

@pytest.mark.parametrize("key", SECRET_KEY_SPELLINGS)
def test_xml_element_for_each_secret_key(key):
    assert redact(f"<{key}>{SECRET}</{key}>") == f"<{key}>[redacted]</{key}>"


def test_xml_element_with_attributes_is_redacted():
    # An attribute value may hold a slash; it must not be mistaken for a self-closing tag.
    assert redact('<password type="plain" href="a/b">hunter2</password>') == '<password type="plain" href="a/b">[redacted]</password>'


def test_xml_element_name_and_closing_tag_match_case_insensitively():
    assert redact("<Client_Secret>x</CLIENT_SECRET >") == "<Client_Secret>[redacted]</CLIENT_SECRET >"


def test_xml_secret_nested_inside_a_classic_account_body():
    body = "<account><name>svc</name><directory_user>false</directory_user><password>hunter2</password><access_level>Full</access_level></account>"
    assert redact(body) == (
        "<account><name>svc</name><directory_user>false</directory_user><password>[redacted]</password><access_level>Full</access_level></account>"
    )


def test_xml_declaration_multiline_body_and_bytes():
    body = b'<?xml version="1.0" encoding="UTF-8"?>\n<account>\n  <password>\n    hunter2\n  </password>\n</account>\n'
    assert redact(body) == '<?xml version="1.0" encoding="UTF-8"?>\n<account>\n  <password>[redacted]</password>\n</account>\n'


def test_xml_cdata_content_is_redacted():
    assert redact("<token><![CDATA[a<b&c]]></token>") == "<token>[redacted]</token>"


def test_xml_secret_elements_side_by_side_are_each_redacted():
    assert redact("<a><token>one</token><token>two</token></a>") == "<a><token>[redacted]</token><token>[redacted]</token></a>"


@pytest.mark.parametrize("xml", [
    "<name>svc</name>",
    "<passwords>keep</passwords>",
    "<my_token>keep</my_token>",
    "<password_hint>keep</password_hint>",
    "<scope>password</scope>",
    "<password/>",
    "<password />",
    '<password required="true"/>',
    "<password></password>",
    "<password>keep</token>",
])
def test_xml_that_holds_no_secret_is_untouched(xml):
    assert redact(xml) == xml


def test_an_empty_element_beside_a_filled_one_leaves_only_the_filled_one_redacted():
    assert redact("<password/><client_id>abc</client_id>") == "<password/><client_id>[redacted]</client_id>"


def test_unclosed_secret_elements_are_handled_in_linear_time():
    # Possessive quantifiers: no backtracking over the (large) remainder of the body for each unclosed tag.
    text = "<token>" * 100_000
    assert redact(text) == text


# --- other input types -----------------------------------------------------

def test_bytes_are_decoded_and_redacted_to_text():
    assert redact(b"client_secret=abc&grant_type=client_credentials") == "client_secret=[redacted]&grant_type=client_credentials"


def test_undecodable_bytes_are_replaced_not_raised():
    assert redact(b"\xff\xfepassword=abc") == "��password=[redacted]"


def test_json_bytes_are_redacted():
    assert json.loads(redact(b'{"token": "abc", "expires": "2026-10-15T14:34:41.571Z"}')) == {
        "token": REDACTED, "expires": "2026-10-15T14:34:41.571Z",
    }


def test_none_stays_none():
    assert redact(None) is None


def test_empty_text_stays_empty():
    assert redact("") == ""
