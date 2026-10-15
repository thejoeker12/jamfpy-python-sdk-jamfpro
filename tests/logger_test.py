"""Unit tests for jamfpy.client.logger: the jamfpy logger, configure_logging(), the text and JSON formats and the
DEBUG rendering helpers.

``configure_logging()`` changes the process-wide ``jamfpy`` logger; the autouse ``restore_jamfpy_logging`` fixture
in ``conftest.py`` puts it back after each test. Tests write to an ``io.StringIO`` so each line can be read back.
"""
# pylint: disable=missing-function-docstring,redefined-outer-name
import io
import json
import logging
import re
import subprocess
import sys
from datetime import datetime, timezone

import pytest
from requests.exceptions import ConnectTimeout
from conftest import FQDN

import jamfpy
from jamfpy.client.logger import (
    MAX_LOGGED_CHARS, JsonFormatter, TextFormatter, configure_logging, render_body, render_headers, truncate,
)
from jamfpy.client.retry import RetryConfig

ACME = "https://acme.jamfcloud.com"
COMPUTERS_URL = f"{FQDN}/JSSResource/computers"
BASE_KEYS = {"ts", "level", "sender", "message"}
FIELDS = {"method": "GET", "url": f"{ACME}/api/v1/scripts/1", "status": 200, "duration_ms": 84, "attempt": 2}
# What new_logger's handler printed, minus the name padding: the text format must reproduce it byte for byte.
OLD_FORMAT = "%(asctime)s [%(levelname)s] (%(name)s): %(message)s"


def _record(name="jamfpy.acme-pro", level=logging.INFO, msg="GET %s -> %d (%d ms)", args=(f"{ACME}/x", 200, 84),
            exc_info=None, **extra):
    record = logging.LogRecord(name, level, __file__, 1, msg, args, exc_info)
    record.__dict__.update(extra)
    return record


def _jamfpy_handlers():
    return logging.getLogger("jamfpy").handlers


def _lines(stream):
    return stream.getvalue().splitlines()


@pytest.fixture
def acme_pro():
    """The ``jamfpy.acme-pro`` child at DEBUG, as a Tenant for https://acme.jamfcloud.com would set it up."""
    logger = logging.getLogger("jamfpy.acme-pro")
    logger.setLevel(logging.DEBUG)
    return logger


# --- the jamfpy logger -----------------------------------------------------

def test_jamfpy_logger_has_only_a_null_handler_before_configure_logging():
    handlers = _jamfpy_handlers()
    assert len(handlers) == 1
    assert type(handlers[0]) is logging.NullHandler  # pylint: disable=unidiomatic-typecheck


def test_unconfigured_jamfpy_output_goes_nowhere(acme_pro, capsys):
    # The NullHandler stops Python's last-resort handler printing WARNINGs to stderr for an app that set up nothing.
    acme_pro.warning("nobody asked for this")
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


# --- configure_logging -----------------------------------------------------

def test_configure_logging_returns_the_handler_it_installs():
    stream = io.StringIO()
    handler = configure_logging(stream=stream)

    assert handler in _jamfpy_handlers()
    assert isinstance(handler, logging.StreamHandler)
    assert handler.stream is stream


def test_configure_logging_defaults_to_text_at_info_on_stdout(acme_pro, capsys):
    handler = configure_logging()

    # sys.stdout as it is at the call, here capsys's, not as it was when jamfpy was imported.
    assert handler.stream is sys.stdout
    assert handler.level == logging.INFO
    assert logging.getLogger("jamfpy").level == logging.INFO
    assert isinstance(handler.formatter, TextFormatter)
    acme_pro.debug("hidden")
    acme_pro.info("shown")
    assert re.fullmatch(r"\S+ \S+ \[INFO\] \(acme-pro\): shown\n", capsys.readouterr().out)


def test_configure_logging_twice_keeps_one_handler_and_the_second_call_wins(acme_pro):
    first, second = io.StringIO(), io.StringIO()
    configure_logging(level=logging.INFO, fmt="text", stream=first)
    handler = configure_logging(level=logging.DEBUG, fmt="json", stream=second)

    installed = [h for h in _jamfpy_handlers() if not isinstance(h, logging.NullHandler)]
    assert installed == [handler]
    assert handler.level == logging.DEBUG
    assert logging.getLogger("jamfpy").level == logging.DEBUG
    assert isinstance(handler.formatter, JsonFormatter)

    acme_pro.debug("after")
    assert first.getvalue() == ""
    assert [json.loads(line)["message"] for line in _lines(second)] == ["after"]


def test_configure_logging_leaves_a_users_handler_alone(acme_pro):
    users = io.StringIO()
    user_handler = logging.StreamHandler(users)
    logging.getLogger("jamfpy").addHandler(user_handler)

    configure_logging(stream=io.StringIO())
    configure_logging(stream=io.StringIO())
    acme_pro.info("both see this")

    assert user_handler in _jamfpy_handlers()
    assert any(isinstance(h, logging.NullHandler) for h in _jamfpy_handlers())
    assert len(_jamfpy_handlers()) == 3
    assert users.getvalue() == "both see this\n"


def test_configure_logging_level_filters_what_reaches_the_stream(acme_pro):
    stream = io.StringIO()
    configure_logging(level=logging.WARNING, stream=stream)

    acme_pro.info("quiet")
    acme_pro.warning("loud")

    assert [line.rsplit(": ", 1)[1] for line in _lines(stream)] == ["loud"]


@pytest.mark.parametrize("fmt", ["xml", "JSON", ""])
def test_configure_logging_rejects_an_unknown_format(fmt):
    with pytest.raises(ValueError, match="fmt must be one of 'text', 'json'"):
        configure_logging(fmt=fmt)
    assert len(_jamfpy_handlers()) == 1


# --- text format -----------------------------------------------------------

def test_text_format_is_the_old_new_logger_line_without_the_jamfpy_prefix():
    record = _record()
    old_style = logging.makeLogRecord({**record.__dict__, "name": "acme-pro"})

    assert TextFormatter().format(record) == logging.Formatter(OLD_FORMAT).format(old_style)
    # The record itself keeps its real name for every other handler it reaches.
    assert record.name == "jamfpy.acme-pro"


def test_text_format_leaves_a_foreign_logger_name_alone():
    line = TextFormatter().format(_record(name="myapp.sync", msg="hello", args=()))
    assert line.endswith(" [INFO] (myapp.sync): hello")


def test_text_line_for_a_real_request(mocked_responses):
    mocked_responses.post(f"{ACME}/api/oauth/token", json={"access_token": "t", "expires_in": 1800})
    mocked_responses.get(f"{ACME}/api/v1/scripts/1", json={"id": "1"})
    stream = io.StringIO()
    configure_logging(stream=stream)
    tenant = jamfpy.Tenant(fqdn=ACME, auth_method="oauth2", client_id="c", client_secret="s")

    tenant.pro.scripts.get_by_id(1)

    # The token fetch logs at DEBUG only, so at INFO the request is the single line.
    [line] = _lines(stream)
    assert re.fullmatch(
        r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3} \[INFO\] \(acme-pro\): "
        rf"GET {re.escape(ACME)}/api/v1/scripts/1 -> 200 \(\d+ ms\)",
        line,
    )


# --- JSON format -----------------------------------------------------------

def test_json_line_without_fields_has_exactly_the_base_keys():
    payload = json.loads(JsonFormatter().format(_record()))

    assert set(payload) == BASE_KEYS
    assert payload["level"] == "INFO"
    assert payload["sender"] == "acme-pro"
    assert payload["message"] == f"GET {ACME}/x -> 200 (84 ms)"


def test_json_line_carries_every_field_the_record_has():
    payload = json.loads(JsonFormatter().format(_record(**FIELDS)))

    assert set(payload) == BASE_KEYS | set(FIELDS)
    assert {key: payload[key] for key in FIELDS} == FIELDS


def test_json_line_omits_the_fields_a_record_lacks():
    payload = json.loads(JsonFormatter().format(_record(method="POST", url=f"{ACME}/api/oauth/token", unrelated="x")))
    assert set(payload) == BASE_KEYS | {"method", "url"}


def test_json_ts_is_iso_8601_utc_with_milliseconds():
    record = _record()
    ts = json.loads(JsonFormatter().format(record))["ts"]

    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z", ts)
    parsed = datetime.fromisoformat(ts)
    assert parsed.utcoffset().total_seconds() == 0
    expected = datetime.fromtimestamp(record.created, timezone.utc).replace(microsecond=int(record.msecs) * 1000)
    assert parsed == expected


def _raised_exc_info():
    try:
        raise ValueError("boom")
    except ValueError:
        return sys.exc_info()


def test_json_folds_a_traceback_into_the_message():
    line = JsonFormatter().format(_record(msg="hook raised", args=(), exc_info=_raised_exc_info()))

    assert "\n" not in line
    payload = json.loads(line)
    assert set(payload) == BASE_KEYS
    assert payload["message"].startswith("hook raised\nTraceback (most recent call last):")
    assert "ValueError: boom" in payload["message"]


def test_every_json_line_of_a_retried_and_exhausted_request_is_valid(make_classic_api, mocked_responses):
    mocked_responses.get(COMPUTERS_URL, status=503)
    # logger=None: the API logs through its jamfpy.test-clc child rather than the fixture's silent logger.
    api = make_classic_api(logger=None, log_level=logging.DEBUG, retries=RetryConfig(total=2, jitter=False))
    # Configured after construction, so the stream holds only the request's lines.
    stream = io.StringIO()
    configure_logging(level=logging.DEBUG, fmt="json", stream=stream)

    api.computers.get_all()

    payloads = [json.loads(line) for line in _lines(stream)]
    assert [p["level"] for p in payloads] == ["DEBUG", "INFO", "DEBUG", "WARNING"] * 2 + ["DEBUG", "INFO", "DEBUG", "ERROR"]
    for payload in payloads:
        assert BASE_KEYS <= set(payload) <= BASE_KEYS | set(FIELDS)
        assert payload["sender"] == "test-clc"
        assert payload["method"] == "GET"
        assert payload["url"] == COMPUTERS_URL
    assert [p["attempt"] for p in payloads if p["level"] in ("WARNING", "ERROR")] == [1, 2, 3]
    # The request line is written before the send, so it has no status or duration yet.
    assert all(set(p) == BASE_KEYS | {"method", "url", "attempt"} for p in payloads if p["message"].startswith("Request "))
    assert all(p["status"] == 503 and isinstance(p["duration_ms"], int) for p in payloads if p["level"] != "DEBUG")


def test_json_info_line_for_a_failed_send_has_no_status(make_classic_api, mocked_responses):
    mocked_responses.get(COMPUTERS_URL, body=ConnectTimeout("connect timed out"))
    stream = io.StringIO()
    configure_logging(fmt="json", stream=stream)
    api = make_classic_api(logger=None, log_level=logging.INFO, retries=None)

    with pytest.raises(ConnectTimeout):
        api.computers.get_all()

    [payload] = [json.loads(line) for line in _lines(stream)]
    assert set(payload) == BASE_KEYS | {"method", "url", "duration_ms", "attempt"}
    assert re.fullmatch(rf"GET {re.escape(COMPUTERS_URL)} -> ConnectTimeout \(\d+ ms\)", payload["message"])


# --- DEBUG rendering helpers -----------------------------------------------

def test_truncate_keeps_text_up_to_the_limit():
    text = "x" * MAX_LOGGED_CHARS
    assert truncate(text) == text


def test_truncate_cuts_longer_text_and_says_how_long_it_was():
    text = "x" * MAX_LOGGED_CHARS + "tail"
    assert truncate(text) == "x" * MAX_LOGGED_CHARS + f"… (truncated, {MAX_LOGGED_CHARS + 4} chars)"


@pytest.mark.parametrize("body", [None, "", b""])
def test_render_body_marks_an_empty_body(body):
    assert render_body(body, safe_mode=True) == "<none>"


def test_render_body_does_not_read_a_streamed_body():
    stream = io.BytesIO(b"client_secret=s")
    assert render_body(stream, safe_mode=True) == "<streamed BytesIO body, not logged>"
    assert stream.tell() == 0


def test_render_body_redacts_before_truncating():
    # Redacted first, so a secret straddling the cut can't leave its first 1024 characters behind.
    body = "a" * 1000 + "&password=" + "p" * 100
    assert render_body(body, safe_mode=True) == "a" * 1000 + "&password=[redacted]"
    assert render_body(body.encode(), safe_mode=False) == truncate(body)


def test_render_headers_redacts_only_under_safe_mode():
    headers = {"Authorization": "Bearer tok", "accept": "application/json"}

    assert json.loads(render_headers(headers, safe_mode=True)) == {"Authorization": "Bearer [redacted]", "accept": "application/json"}
    assert json.loads(render_headers(headers, safe_mode=False)) == headers


def test_render_headers_truncates_a_long_header_set():
    headers = {"Authorization": "Bearer tok", "X-Padding": "p" * 2 * MAX_LOGGED_CHARS}
    full = json.dumps({"Authorization": "Bearer [redacted]", "X-Padding": "p" * 2 * MAX_LOGGED_CHARS})

    rendered = render_headers(headers, safe_mode=True)

    assert len(full) > MAX_LOGGED_CHARS
    assert rendered == full[:MAX_LOGGED_CHARS] + f"… (truncated, {len(full)} chars)"


def test_render_headers_leaves_a_header_set_at_the_limit_whole():
    overhead = len(json.dumps({"X": ""}))
    headers = {"X": "p" * (MAX_LOGGED_CHARS - overhead)}

    assert len(json.dumps(headers)) == MAX_LOGGED_CHARS
    assert render_headers(headers, safe_mode=True) == json.dumps(headers)


def test_render_headers_redacts_cookies_under_safe_mode_only():
    headers = {"Cookie": "JSESSIONID=abc", "Set-Cookie": "jpro-ingress=def; Path=/", "Content-Type": "application/json"}

    assert json.loads(render_headers(headers, safe_mode=True)) == {
        "Cookie": "[redacted]", "Set-Cookie": "[redacted]", "Content-Type": "application/json",
    }
    assert json.loads(render_headers(headers, safe_mode=False)) == headers


def test_render_body_redacts_an_xml_password():
    body = "<account><name>svc</name><password>hunter2</password></account>"
    assert render_body(body, safe_mode=True) == "<account><name>svc</name><password>[redacted]</password></account>"


def test_render_body_raises_no_bytes_warning_on_empty_or_non_empty_bodies():
    # BytesWarning is only issued when the interpreter runs with -b, which pytest does not, so the check runs in a
    # child process under -bb where a bytes/str comparison anywhere in render_body would raise.
    script = (
        "import warnings\n"
        "warnings.simplefilter('error', BytesWarning)\n"
        "from jamfpy.client.logger import render_body\n"
        "for body in (b'', '', b'x', 'x'):\n"
        "    for safe_mode in (True, False):\n"
        "        render_body(body, safe_mode)\n"
        "print(render_body(b'', True), render_body('', False))\n"
    )

    done = subprocess.run([sys.executable, "-bb", "-c", script], capture_output=True, text=True, check=False, timeout=60)

    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "<none> <none>"
