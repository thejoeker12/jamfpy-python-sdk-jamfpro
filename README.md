# jamfpy

A Python SDK for the Jamf Pro server APIs.

## What it is

Jamf Pro has two HTTP APIs, and jamfpy wraps both:

| API | Base path | Payloads | In jamfpy |
|---|---|---|---|
| Classic (the JSS Resource API) | `/JSSResource` | XML for writes; JSON (the default) or XML for reads | `tenant.classic` |
| Pro (the Jamf Pro API) | `/api/v{n}`, versioned per endpoint | JSON | `tenant.pro` |

jamfpy is a thin, explicit wrapper. It authenticates and keeps the token fresh, builds each request's URL and
headers, retries what is safe to retry and logs what it does. Then it hands back the raw `requests.Response`:

- It never turns a response into a model. You read `response.json()`, `response.text` or `response.content`
  yourself.
- It never raises because of a status code. A 404 or a 500 comes back as a `Response` like any other, so check
  `response.ok` or `response.status_code`. Authentication failures and network errors do raise (see
  [Authentication](#authentication) and [Retries](#retries)).

It needs Python 3.13 or later, and its only runtime dependency is `requests`. The package is fully type-hinted and
ships a `py.typed` marker, so mypy and other type checkers use its hints.

## Install

```bash
pip install jamfpy
```

or, in a uv project:

```bash
uv add jamfpy
```

The features described here ship from the next major release. The latest PyPI release, 2.6.0 (v2.7.0 exists on GitHub
but was never published to PyPI), has no request hooks,
retries, `configure_logging`, `parallelism` or lazy authentication.

## Quickstart

Build a `Tenant` for your Jamf Pro instance, then call endpoints on `tenant.classic` and `tenant.pro`. The examples
read credentials from environment variables. The examples further down reuse this one's imports and a `tenant`
built the same way.

```python
import os
from xml.etree import ElementTree

import jamfpy

tenant = jamfpy.Tenant(
    fqdn="https://acme.jamfcloud.com",
    auth_method="oauth2",
    client_id=os.environ["JAMFPRO_CLIENT_ID"],
    client_secret=os.environ["JAMFPRO_CLIENT_SECRET"],
)

# Classic API: reads come back as JSON unless you ask for XML.
buildings = tenant.classic.buildings.get_all()
if buildings.ok:
    for building in buildings.json()["buildings"]:
        print(building["id"], building["name"])
else:
    print("Listing buildings failed:", buildings.status_code, buildings.text)

# Pro API: JSON both ways.
script = tenant.pro.scripts.get_by_id(1)
if script.ok:
    print(script.json()["name"])

# A Classic write takes an XML string. Jamf answers with the new id, as XML.
created = tenant.classic.buildings.create(
    "<building><name>London</name></building>"
)
if created.ok:
    new_id = ElementTree.fromstring(created.content).findtext("id")
    print("Created building", new_id)
else:
    print("Creating the building failed:", created.status_code, created.text)

# A Pro write takes a dict, sent as JSON.
new_script = tenant.pro.scripts.create(
    {"name": "Hello", "scriptContents": "#!/bin/sh\necho hello\n"}
)
if new_script.ok:
    print("Created script", new_script.json()["id"])
else:
    print(
        "Creating the script failed:",
        new_script.status_code,
        new_script.text,
    )

# Invalidate the token. Both APIs share it, so this covers tenant.pro too.
tenant.classic.close()
```

Either `tenant.classic.close()` or `tenant.pro.close()` will do: the two APIs share one token, and closing either
invalidates it on the server. Requests sent after that carry the invalidated token and get a 401, so build a new
`Tenant` to start again.

## Examples

The repository's [examples](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/blob/main/examples/README.md)
folder has a runnable script per topic: authentication, error handling, calling an endpoint jamfpy doesn't wrap,
logging, timeouts and retries, pagination, certificates, request hooks, concurrency, and a create, read, update and
delete cycle on each API. Each reads its credentials from the environment; the folder's README lists the variables
and says which two scripts write to the tenant.

## Authentication

`auth_method` picks how jamfpy gets its token. Either way, every API request carries `Authorization: Bearer <token>`,
and jamfpy fetches and refreshes the token for you.

### OAuth with an API client

`auth_method="oauth2"` with the API client's `client_id` and `client_secret`, as in the quickstart. jamfpy fetches an
access token with the client-credentials grant (`POST /api/oauth/token`), and fetches a new one when the current one
nears expiry.

### Username and password

`auth_method="basic"` with a Jamf Pro user's `username` and `password`:

```python
tenant = jamfpy.Tenant(
    fqdn="https://acme.jamfcloud.com",
    auth_method="basic",
    username=os.environ["JAMFPRO_USERNAME"],
    password=os.environ["JAMFPRO_PASSWORD"],
)
```

jamfpy exchanges the credentials for a bearer token (`POST /api/v1/auth/token`) and keeps that token alive
(`POST /api/v1/auth/keep-alive`) as it nears expiry. It uses the credentials again only to fetch a new token once the
current one has expired; API requests carry the bearer token, never the credentials.

An `auth_method` other than these two, or a missing credential, raises `JamfpyConfigError` when the `Tenant` is
built.

### When authentication happens

Building a `Tenant` makes no network call. The first request fetches the token, so that is where problems surface:

- Credentials the server refuses raise `JamfAuthError`.
- An unreachable host raises the `requests` exception, such as `requests.ConnectionError`.

To fail fast instead, call `authenticate()` straight after building the tenant. It fetches a token at once and
raises the same errors:

```python
from jamfpy.client.exceptions import JamfAuthError

try:
    tenant.authenticate()
except JamfAuthError as exc:
    raise SystemExit(f"Jamf Pro refused the credentials: {exc}") from exc
```

The exceptions live in `jamfpy.client.exceptions`. `str(exc)` and the message text of a `JamfAuthError` are redacted,
whatever `safe_mode` says, so they are safe to log. `exc.args` is not: a refused token request also carries the
`requests.Response` (OAuth: `exc.args[1]`, then the redacted body text; basic auth: the status code, then the
Response as `exc.args[2]`), and that Response's `request` holds the raw request body or headers, which include the
client secret or the `Authorization: Basic` credentials. Never serialise `exc.args` or the Response into a log or a
crash report. A keep-alive failure (basic auth) raises a `JamfAuthError` that carries no Response.

### Token refresh

Before every request jamfpy checks the token. With no token yet, or an expired one, it fetches a new one. Inside the
refresh buffer, OAuth fetches a new token and basic auth extends the current one with keep-alive.

The buffer is `token_exp_threshold_mins` (default 20 minutes), capped at half the token's lifetime, so a freshly
issued token always starts outside it. The cap matters for API clients that issue tokens shorter than the buffer: for
a 299-second token the buffer becomes about 150 seconds. When the configured buffer is at least the whole token
lifetime, jamfpy logs one WARNING per `Tenant` naming the buffer it uses instead (timestamp left off):

```text
[WARNING] (acme-auth): Configured token buffer of 20 min is not shorter than the token lifetime of 299 s; using a 150 s buffer instead
```

Refreshing is thread-safe. It runs under a lock, so when several threads find the token due at once, one of them
fetches it and the others use the result. A failed fetch is not shared: each waiting thread tries again in turn, so
N threads against an unreachable token endpoint can take up to N times the timeout. Token requests are never
retried.

## Tenant options

Every argument is keyword-only.

| Keyword | Default | What it does |
|---|---|---|
| `fqdn` | required | The instance's URL, with its scheme and without a trailing slash: `https://acme.jamfcloud.com`. Its first label (`acme`) names the loggers. |
| `auth_method` | required | `"oauth2"` or `"basic"` (see [Authentication](#authentication)). |
| `client_id`, `client_secret` | `None` | The API client's credentials, for `oauth2`. |
| `username`, `password` | `None` | A Jamf Pro user's credentials, for `basic`. |
| `http_config` | `HTTPConfig()` | The URL paths and header sets every request is built from (`jamfpy.client.http_config.HTTPConfig`), defaulting to `DEFAULT_HTTP_CONFIG_URLS` and `DEFAULT_HTTP_CONFIG_HEADERS` in `jamfpy.client.constants`. |
| `token_exp_threshold_mins` | `20` | The token refresh buffer in minutes, capped at half the token's lifetime (see [Token refresh](#token-refresh)). |
| `log_level` | `logging.INFO` | The level of the tenant's three loggers (see [Logging](#logging)). |
| `safe_mode` | `True` | Redact credentials in logged headers and bodies (see [Redaction and safe_mode](#redaction-and-safe_mode)). |
| `cert_path` | `None` | A client certificate file, for mutual TLS (see [Certificates](#certificates)). |
| `verify_path` | `None` | A CA bundle to verify the server's certificate against. |
| `timeout` | `30.0` | Seconds, or a `(connect, read)` tuple, for every API and auth call (see [Timeouts](#timeouts)). |
| `retries` | `RetryConfig()` | How API requests are retried; `None` turns retries off (see [Retries](#retries)). |
| `parallelism` | `5` | The most requests jamfpy runs at once for an operation it fans out itself, today a Pro `get_all` (see [Parallelism](#parallelism)). |

A tenant with most of them set:

```python
import logging

tenant = jamfpy.Tenant(
    fqdn="https://acme.jamfcloud.com",
    auth_method="oauth2",
    client_id=os.environ["JAMFPRO_CLIENT_ID"],
    client_secret=os.environ["JAMFPRO_CLIENT_SECRET"],
    token_exp_threshold_mins=20,
    log_level=logging.INFO,
    safe_mode=True,
    timeout=(5.0, 60.0),
    retries=jamfpy.RetryConfig(total=5),
    parallelism=5,
)
```

### Timeouts

`timeout` takes what `requests` takes: one number of seconds for both the connect and the read phase, or a
`(connect, read)` tuple. The type alias is `jamfpy.Timeout`. The default of 30 seconds applies to every API request
and to every auth call: token fetch, keep-alive and invalidation.

To override it for one request, send that request yourself through the API's `do()`. That is also how to call a
Jamf endpoint jamfpy doesn't wrap yet: `do()` adds the token, retries, logs and fires hooks exactly as it does for an
endpoint method.

```python
from requests import Request

request = Request(
    "GET",
    tenant.pro.url("1") + "/scripts?page=0&page-size=200",
    headers=tenant.pro.header("read")["json"],
)
# This request only: a token fetch it triggers uses Tenant(timeout=...).
response = tenant.pro.do(request, timeout=(5.0, 120.0))
```

`tenant.pro.url("1")` is the base URL for version 1 of the Pro API (`https://acme.jamfcloud.com/api/v1`), and
`tenant.classic.url()` the Classic one (`https://acme.jamfcloud.com/JSSResource`). `do()` prepares the request again
for each attempt, so give it a body that can be sent twice (a `data=` string, bytes or dict, or `json=`), never a
file or a generator.

### Retries

`retries` takes a `jamfpy.RetryConfig`, which decides how API requests are retried. Auth calls (token fetch,
keep-alive, invalidation) are never retried.

| Field | Default | Meaning |
|---|---|---|
| `total` | `3` | Retries after the first attempt, so at most four attempts. |
| `backoff_factor` | `0.5` | The base of the exponential backoff, in seconds. |
| `max_backoff` | `30.0` | The cap on the computed delay, and the longest `Retry-After` jamfpy will wait. |
| `jitter` | `True` | Apply full jitter to the computed delay. |
| `statuses` | `(429, 500, 502, 503, 504)` | The statuses that are retried. |
| `methods` | `("GET", "HEAD", "OPTIONS", "PUT", "DELETE")` | The methods retried after a status, a read timeout or a connection error, compared case-insensitively. |
| `retry_post` | `False` | Retry POST under the same rules. POST is not idempotent: a resend can create a second record. |

`RetryConfig` is a frozen dataclass, so one instance is safe to share. It is checked when it is built: a negative,
NaN or wrongly typed value raises `ValueError`, and so does a bare string for `methods` (write `methods=("GET",)`).
Lists and sets are accepted and stored as tuples.

What is retried:

- **A status in `statuses`**, for a method in `methods`, and for POST when `retry_post` is set. Any other status,
  and a listed status on any other method (PATCH, or POST without `retry_post`), is returned at once.
- **`requests.ConnectTimeout`**, for every method, POST included, whatever `retry_post` says: the connection never
  opened, so nothing reached the server.
- **`requests.ReadTimeout` and `requests.ConnectionError`** (`ProxyError` included), under the same method rule as a
  status, because the server may have processed the request.
- **Nothing else.** `requests.SSLError` is a `ConnectionError`, but it is raised at once: a TLS failure won't fix
  itself on a resend. So is every other exception.

The wait before the next attempt, after attempt n failed:

- **Computed:** `min(backoff_factor * 2 ** (n - 1), max_backoff)`, then, with `jitter`, multiplied by a random number
  in [0, 1). The cap comes before the jitter ("full jitter"), so late retries still spread across the whole window.
  Without jitter the defaults wait 0.5, 1 and 2 seconds.
- **`Retry-After`:** on a response that is retried, it replaces the computed delay, without jitter. Both of its forms
  work: a number of seconds, or an HTTP date (a date in the past means no wait). A value that is neither is ignored,
  and the computed delay applies.
  If it asks for more than `max_backoff`, jamfpy stops retrying and returns that response, since waiting less than the
  server asked would only earn another 429.

When the retries run out, a status retry returns the last response (a status never raises) and an exception retry
raises the last exception. Each attempt gets the current token, so a token that expires during a backoff is
refreshed before the resend.

Every retry logs one WARNING with the method, the URL, the attempt that failed, the reason and the delay, and giving
up on a request that was still retryable logs one ERROR. Each attempt also logs its own INFO line, so a retried
request reads as one trace (timestamps left off):

```text
[INFO] (acme-clc): GET https://acme.jamfcloud.com/JSSResource/departments -> 503 (41 ms)
[WARNING] (acme-clc): Retrying GET https://acme.jamfcloud.com/JSSResource/departments: attempt 1 failed with HTTP 503; next attempt in 0.31 s
[INFO] (acme-clc): GET https://acme.jamfcloud.com/JSSResource/departments -> 200 (38 ms, attempt 2)
```

`retries=None` turns retries off: one attempt per request, and the retry loop logs nothing.

### Parallelism

`parallelism` caps how many requests jamfpy runs at once for an operation it fans out on its own. Today that is one
operation: a Pro `get_all`, which fetches its pages in parallel. The Classic API has nothing to fan out.

- **It is not a rate limiter.** It never throttles, queues or serialises requests you make. Ten threads calling
  `get_by_id` on one tenant send ten requests at once, and ten threads each running a `get_all` can have ten times
  `parallelism` page requests in flight. If you need a global cap, bring your own.
- **It takes an `int` of at least 1.** `1` fetches every page on the calling thread, one at a time, in order. Anything
  else (0, a negative number, a bool, a non-int) raises `ValueError` when the tenant is built.
- **The default of 5** follows Jamf's scalability guidance, which says to limit a client to no more than five
  concurrent connections:
  https://developer.jamf.com/jamf-pro/docs/jamf-pro-api-scalability-best-practices

How a Pro `get_all(page_size=None, sort=None)` fetches (100 records a page unless you pass `page_size`):

1. Page 0 first, on the calling thread. If it isn't ok, it is returned as-is.
2. When page 0 reports a `totalCount`, the number of pages is known. jamfpy keeps up to `parallelism` of the rest in
   flight on worker threads, starting the next page as each one finishes (a sliding window), and reads them back in
   page order, so `results` keeps the server's order.
3. If a page comes back not ok, or raises, no further pages are started. The pages already in flight finish, and the
   lowest-numbered failed page is returned as-is: its own status, headers, body and URL. A page whose request raised
   (after its retries) raises from `get_all`.
4. A page that repeats page 0's (non-empty) results means the server is ignoring `page`: jamfpy logs a WARNING and
   returns only the results of the pages before it.
5. Otherwise you get one `Response` whose body is `{"totalCount": N, "results": [...]}`, N being the number of results
   collected.

Without a `totalCount` on page 0 the number of pages is unknown, so jamfpy walks them one at a time on the calling
thread until a short or empty page, and stops after page 3 as a guard against a server that ignores `page`.

Each page is its own request: it is retried, logged and hooked on its own, and its hooks fire on the thread that
fetched it.

```python
scripts = tenant.pro.scripts.get_all(page_size=200, sort="name:asc")
if scripts.ok:
    body = scripts.json()
    print(body["totalCount"], "scripts")
    for script in body["results"]:
        print(script["id"], script["name"])
else:
    print("A page failed:", scripts.url, scripts.status_code)
```

### Logging

By default jamfpy prints nothing. It logs through the standard `logging` module, and its top logger, `jamfpy`, has
only a `NullHandler` until you ask for output, so an application that configures nothing sees nothing (not even
Python's last-resort output for warnings). To see the logs:

```python
import logging

import jamfpy

jamfpy.configure_logging(level=logging.INFO, fmt="text")
```

`configure_logging(level=logging.INFO, fmt="text", stream=None)` attaches one handler to the `jamfpy` logger, writing
to `stream` (`sys.stdout` when it is `None`), sets the handler's and the logger's level to `level`, and returns the
handler. Calling it again replaces the handler it installed before and leaves any handler you added yourself alone.
If your application already configures logging, you don't need it: the tenant's loggers propagate, so their records
also reach the root logger's handlers.

Each tenant logs through three loggers named after the first label of `fqdn` (`acme` for
`https://acme.jamfcloud.com`): `jamfpy.acme-auth` (token fetch, keep-alive, invalidation), `jamfpy.acme-pro` and
`jamfpy.acme-clc`. `Tenant(log_level=...)` sets the level of all three. Loggers are process-wide by name, so two
tenants for the same instance share them, and the last `log_level` set wins.

The two formats:

- `fmt="text"`: `%(asctime)s [%(levelname)s] (%(name)s): %(message)s`, with `jamfpy.` dropped from the name:

  ```text
  2026-10-15 20:15:04,134 [INFO] (acme-pro): GET https://acme.jamfcloud.com/api/v1/scripts?page=0&page-size=2 -> 200 (820 ms)
  ```

- `fmt="json"`: one object per line, with `ts`, `level`, `sender` and `message`, plus `method`, `url`, `status`,
  `duration_ms` and `attempt` when the record has them. A traceback is folded into `message`, so the keys never
  change:

  ```json
  {"ts": "2026-10-15T19:14:01.751Z", "level": "INFO", "sender": "acme-pro", "message": "GET https://acme.jamfcloud.com/api/v1/scripts?page=0&page-size=2 -> 200 (832 ms)", "method": "GET", "url": "https://acme.jamfcloud.com/api/v1/scripts?page=0&page-size=2", "status": 200, "duration_ms": 832, "attempt": 1}
  ```

Any other `fmt` raises `ValueError`.

| Level | What is logged |
|---|---|
| DEBUG | Each API attempt's request and response headers and bodies, redacted under `safe_mode` and then cut to 1024 characters; each auth call; routine token housekeeping. |
| INFO | One line per API attempt: the method, the URL, the status (or, when the send raised, the exception's class) and the duration in milliseconds, with the attempt number from the first retry on. Also `close()`. |
| WARNING | Each retry, a request hook that raised, a failed token invalidation in `close()`, the one-time token buffer warning, and a `get_all` page that repeats page 0. |
| ERROR | Giving up on a request that was still retryable. |

A clean request logs nothing above INFO, and auth calls never log at INFO. The one exception is the first token
fetch for an API client whose tokens last no longer than the refresh buffer: it logs the one-time buffer WARNING (see
[Token refresh](#token-refresh)).

The lines for each request attempt (the DEBUG request and response lines, the INFO line, and any retry WARNING or
give-up ERROR) also carry their fields as attributes on the `LogRecord`: `method`, `url` and `attempt`, then
`duration_ms` from the INFO line on, and `status` when a response arrived. The JSON format reads them from there, and
so can your own filters and formatters.

To see DEBUG output, lower both thresholds: `configure_logging` sets what is written, and `log_level` what the
tenant emits.

```python
jamfpy.configure_logging(level=logging.DEBUG, fmt="json")
tenant = jamfpy.Tenant(
    fqdn="https://acme.jamfcloud.com",
    auth_method="oauth2",
    client_id=os.environ["JAMFPRO_CLIENT_ID"],
    client_secret=os.environ["JAMFPRO_CLIENT_SECRET"],
    log_level=logging.DEBUG,
)
```

#### Redaction and safe_mode

With `safe_mode=True`, the default, every header set and body jamfpy logs is redacted first:

- The value of the `Authorization` header, keeping its `Bearer` or `Basic` scheme (`Bearer [redacted]`).
- The whole value of the `Proxy-Authorization`, `X-Auth-Token`, `Cookie` and `Set-Cookie` headers, so session
  cookies such as `JSESSIONID` show as `[redacted]`.
- The value of the keys `password`, `client_secret`, `client_id`, `access_token` and `token`, in JSON, form bodies,
  XML elements (`<password>[redacted]</password>`) and raw text. `client_id` is on the list because it is half of the
  OAuth credential pair.

Names match case-insensitively but exactly: `newPassword` and `pin` are not redacted. URLs and their query strings
are never redacted either. No URL jamfpy builds carries a credential, but one you add yourself is logged as written.
Redaction happens before the cut to 1024 characters, so a secret can't straddle it.

`safe_mode=False` logs headers and bodies raw, including the bearer token, the basic credentials, the client ID and
secret, and the tokens Jamf issues. Use it against a development tenant only. The `str()` of a `JamfAuthError` is
redacted whatever `safe_mode` says, but its `args` can hold the raw `Response` (see
[When authentication happens](#when-authentication-happens)).

### Certificates

Requests are TLS-verified by default and never sent unverified.

- `verify_path` is a CA bundle to verify the server's certificate against. When it is set, it wins over the
  `REQUESTS_CA_BUNDLE` and `CURL_CA_BUNDLE` environment variables, which are honoured otherwise.
- `cert_path` is a single PEM file holding both the client certificate and its private key, sent for mutual TLS (it
  is passed to requests as `cert`, in its string form).

Both must be existing files: a missing path or a directory raises `JamfpyConfigError` when the tenant is built. Proxy
settings from the environment (`HTTP_PROXY`, `HTTPS_PROXY`, `NO_PROXY`) are honoured too, for API and auth calls
alike.

```python
tenant = jamfpy.Tenant(
    fqdn="https://jamf.example.com:8443",
    auth_method="oauth2",
    client_id=os.environ["JAMFPRO_CLIENT_ID"],
    client_secret=os.environ["JAMFPRO_CLIENT_SECRET"],
    verify_path="certs/corp-ca.pem",
    cert_path="certs/jamf-client.pem",
)
```

## Raw responses

Every endpoint method that sends a request returns a `requests.Response`, whatever its status. jamfpy stays a thin,
explicit wrapper: it doesn't parse the body into a model and doesn't raise on a 4xx or 5xx, so you decide what a
failure means for your code.

```python
response = tenant.classic.buildings.get_by_id(1)
if response.status_code == 404:
    print("No such building")
elif not response.ok:
    response.raise_for_status()  # opt in to an exception, the requests way
else:
    print(response.json()["building"]["name"])
```

Classic reads ask for JSON by default. Pass `xml_response=True` to a Classic `get_all` or `get_by_id` to get XML
instead:

```python
from xml.etree import ElementTree

response = tenant.classic.buildings.get_by_id(1, xml_response=True)
if response.ok:
    building = ElementTree.fromstring(response.content)
    print(building.findtext("name"))
else:
    print("Fetching the building failed:", response.status_code)
```

Classic writes take an XML string, and Pro writes a dict, which is sent as JSON.

Two kinds of method build a `Response` of their own instead of passing Jamf's straight back. Both build it only from
successful responses: a response that isn't ok is returned as-is, so you check `.ok` as for any other call.

- A Pro `get_all` aggregates every page into one `Response` with the body `{"totalCount": N, "results": [...]}` and
  the last page's status, headers and URL (see [Parallelism](#parallelism)).
- `tenant.classic.accounts.users.get_all()` and `tenant.classic.accounts.groups.get_all()` slice the shared
  `/accounts` payload down to `{"users": [...]}` or `{"groups": [...]}`. `tenant.classic.accounts.get_all()` returns
  the whole payload.

## Request hooks

Hooks let you observe every API request jamfpy sends, for metrics, tracing or auditing, without wrapping the SDK.
`tenant.hooks` holds them, and both APIs share it.

```python
import logging
import threading
import time

audit = logging.getLogger("audit")
slow_urls = []
slow_urls_lock = threading.Lock()


@tenant.hooks.after_response
def record_response(prepared, response, ctx):
    elapsed_ms = (time.monotonic() - ctx.started) * 1000
    audit.info("%s %s %s -> %d (%.0f ms, attempt %d)", ctx.api,
               prepared.method, prepared.url, response.status_code,
               elapsed_ms, ctx.attempt)
    if elapsed_ms > 2000:
        # Hooks can run on several threads at once, so guard shared state.
        with slow_urls_lock:
            slow_urls.append(prepared.url)


@tenant.hooks.on_retry
def record_retry(prepared, ctx, reason, delay):
    audit.warning("retrying %s %s after attempt %d in %.1f s: %r",
                  prepared.method, prepared.url, ctx.attempt, delay, reason)


tenant.classic.departments.get_all()  # fires the hooks once per attempt

tenant.hooks.remove(record_response)
tenant.hooks.remove(record_retry)
```

`before_request(fn)`, `after_response(fn)` and `on_retry(fn)` each register `fn` and return it, so each also works as
a decorator. `remove(fn)` takes `fn` out of every list it is in, however many times it was registered; removing a
function that isn't registered does nothing. Registering and removing are safe from any thread and from inside a
hook, and a change takes effect the next time hooks of that kind fire.

The signatures:

- `before_request(prepared: PreparedRequest, ctx: RequestContext) -> None`
- `after_response(prepared: PreparedRequest, response: Response, ctx: RequestContext) -> None`
- `on_retry(prepared: PreparedRequest, ctx: RequestContext, reason: Response | Exception, delay: float) -> None`

`jamfpy.RequestContext` is a frozen dataclass:

- `tenant`: the tenant's FQDN, as a plain string, so a hook never receives the object that holds the credentials.
- `api`: `"pro"` or `"classic"`.
- `attempt`: 1 for the first attempt, then one more per retry.
- `started`: `time.monotonic()` when the attempt started, after the request was prepared, so a token fetch isn't
  counted.

The contract:

- Hooks fire per HTTP attempt, not per SDK operation, and for API requests only: never for auth calls (token fetch,
  keep-alive, invalidation).
- For each attempt: `before_request`, then the send, then exactly one of `after_response`, for any response whatever
  its status (including one that is about to be retried), or nothing, when the send raised.
- If a retry follows, `on_retry` fires after that and before the sleep, with the response or the exception as
  `reason` and the delay about to be slept as `delay`.
- A Pro `get_all` runs this sequence once per page. Its pages may be fetched on worker threads, so their hook calls
  can interleave in any order. `ctx.attempt` counts the attempts of one page's request, so it tells a retry from a
  new page.
- Return values are ignored. Mutating the arguments is unsupported.
- A hook that raises is logged at WARNING with its `__qualname__` and the traceback, and the request carries on. The
  remaining hooks still run.
- Hooks may run on worker threads, not only the caller's, and on several threads at once (concurrent callers of one
  tenant, or a `get_all`'s page fetchers), so they must be thread-safe.
- The prepared request carries the real `Authorization` header. If you persist requests, redact it yourself.

## Thread safety

One `Tenant` can be shared across threads:

```python
from concurrent.futures import ThreadPoolExecutor

with ThreadPoolExecutor(max_workers=4) as pool:
    computers = list(
        pool.map(tenant.classic.computers.get_by_id, [1, 2, 3, 4])
    )
print([response.status_code for response in computers])
```

What jamfpy guarantees:

- The `Authorization` header goes on each request, never on the shared session, so concurrent callers never see each
  other's headers.
- Each API's session holds only the connection pool (which urllib3 guards), the cookie jar, the redirect cache and
  headers set once at construction (requests' defaults and `User-Agent: jamfpy/<version>`). jamfpy changes none of
  it per request.
- The token is the only shared state that changes as requests run, and it is refreshed under a lock: N threads that
  find it due make one token request and all use the result. A failed fetch is retried by each waiting thread in
  turn (see [Token refresh](#token-refresh)).
- The hook registry has its own lock. The hooks themselves must be thread-safe (see [Request hooks](#request-hooks)).
- `parallelism` bounds only jamfpy's own fan-out, never your concurrency (see [Parallelism](#parallelism)).

## Endpoints

Endpoints hang off the two APIs as `tenant.classic.<resource>` and `tenant.pro.<resource>`: `tenant.classic.computers`,
`tenant.classic.accounts.users`, `tenant.pro.scripts` and so on.
[COVERAGE.md](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/blob/main/COVERAGE.md)
lists every endpoint wrapped today with the paths and verbs it sends, and the Jamf resources that aren't wrapped yet.

CRUD endpoints share one set of methods:

| Method | Classic | Pro |
|---|---|---|
| `get_all()` | One GET for the whole collection; `xml_response=True` for XML. | Every page, aggregated into one `Response`; optional `page_size` and `sort` (such as `"name:asc"`). |
| `get_by_id(id)` | GET `/<resource>/id/<id>`; `xml_response=True` for XML. | GET `/<resource>/<id>`. |
| `create(body)` | An XML string, POSTed to `/<resource>/id/0`. | A dict, POSTed as JSON to `/<resource>`. |
| `update_by_id(id, body)` | An XML string, sent with PUT. | A dict, sent as JSON with PUT. |
| `delete_by_id(id)` | DELETE. | DELETE. |
| `name()` | The endpoint's short name, such as `"buildings"`. | The same, such as `"scripts"`. |

`tenant.classic.accounts.users` and `.groups` use Jamf's `/accounts/userid/<id>` and `/accounts/groupid/<id>` paths,
and their `get_all` and `get_by_id` take no `xml_response`.

A Pro endpoint has only the methods its resource supports in Jamf's schema. `/v1/dock-items` has no collection GET,
for example, so `tenant.pro.dock_items` has no `get_all`.

`tenant.pro.app_installers` is the exception: Jamf's published schema leaves out `/v1/app-installers`, so its verbs
and body shapes come from a probe of a live tenant (the repository's `pro-supplement.json`), not from Jamf's schema.
Its pagination and a full create, read, update and delete are tested against a live tenant, but Jamf documents
neither, so they can change without notice.

Action endpoints send commands rather than manage records. `tenant.pro.mdm` sends MDM commands: it has wrappers for
common commands, which map Python arguments to Jamf's field names, and `send_command` for any command type:

```python
response = tenant.pro.mdm.lock_device(
    ["<management-id>"], message="Contact IT", pin="123456"
)
response = tenant.pro.mdm.send_command("SHUT_DOWN_DEVICE", ["<management-id>"])
```

For a Jamf endpoint jamfpy doesn't wrap yet, send a request through `do()` (see [Timeouts](#timeouts)).

## Contributing

The developer documentation is [AGENTS.md](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/blob/main/AGENTS.md),
which covers how the SDK is built, its conventions and its quality gates, and
[EXPANDING.md](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/blob/main/EXPANDING.md),
a worked guide to adding an endpoint. Every task runs through make:
`make setup` installs the locked environment with uv, `make help` lists the targets, and `make check` runs every gate
CI runs (lint, type check, the unit tests with coverage, and the COVERAGE.md drift check). The live integration suite,
`make test-integration`, needs a development Jamf Pro tenant: copy `.env.example` to `.env` and fill in the three
`JAMFPRO_` variables it lists. Commits follow Conventional Commits, which drive the releases.
