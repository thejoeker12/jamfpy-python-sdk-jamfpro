# AGENTS.md

Entrypoint for AI agents and junior devs working on **jamfpy** — a hand-authored Python SDK for the Jamf Pro server APIs. `README.md` is intentionally empty; this file is the source of truth for how the codebase is put together and how to change it safely.

**Route by task:**

- **Adding an endpoint** (the most common job) → jump to **How to add an endpoint**.
- **Touching auth, tokens, or request plumbing** → read **Architecture & request lifecycle** first.
- **Touching retries or request hooks** → **Retries** and **Request hooks** (the hook contract is public; change it deliberately).
- **Anything else** → skim **Conventions** and **Quality gates**, and read **Known rough edges** before "fixing" anything you didn't come here to change.

---

## What this SDK is

Jamf Pro exposes **two** HTTP APIs and this SDK wraps both:

| API | Jamf name | Base path | Payloads | This SDK |
|-----|-----------|-----------|----------|----------|
| **Classic** | JSS Resource API | `/JSSResource` | **XML** for writes, JSON readable | `tenant.classic.*` |
| **Pro** | Modern Jamf Pro API | `/api/v{n}` (versioned per-endpoint) | **JSON** | `tenant.pro.*` |

The SDK is a thin, explicit wrapper: auth/token lifecycle, URL/header assembly, logging — then it hands back the **raw `requests.Response`**. It does *not* deserialize into models (two documented exceptions, see Conventions). Only runtime dependency is `requests`. Python **>= 3.13**; CI tests the three newest stable CPython lines (3.15, 3.14, 3.13).

---

## Repo layout

```
jamfpy/
  __init__.py               # public surface (`__all__`): Tenant, OAuth, BasicAuth, API, ProAPI, ClassicAPI, new_logger, Timeout,
                            #   RetryConfig, Hooks, RequestContext
  py.typed                  # PEP 561 marker: tells downstream type checkers the package ships inline hints.
  client/
    tenant.py               # Tenant — the main entrypoint. Validates config, builds Auth + both APIs.
    auth.py                 # Auth base + OAuth + BasicAuth. Token acquisition, refresh, keep-alive, invalidate.
    api.py                  # API base class. do() is the central request executor and runs the retry loop.
    client.py               # ProAPI / ClassicAPI. Wire endpoint objects onto each API.
    http_config.py          # HTTPConfig wrapper around the URL/header dicts.
    retry.py                # RetryConfig (public) + RetryPolicy (internal): what do() retries and how long it waits.
    hooks.py                # Hooks + RequestContext: request hooks do() fires per attempt.
    constants.py            # Default URLs, header sets, DEFAULT_TIMEOUT + the Timeout alias, VALID_AUTH_METHODS. Edit URLs/headers HERE.
    exceptions.py           # JamfAPIError, JamfpyConfigError, JamfpyInitError, JamfAuthError.
    logger.py               # new_logger() — per-tenant stdout logger; names are {tenant}-pro, {tenant}-clc and {tenant}-auth.
    utility.py              # URL parsing, Jamf datetime parsing, XML helpers, the jamfpy User-Agent string.
  endpoints/
    models.py               # Endpoint / ClassicEndpoint / ProEndpoint base classes.
    clc_endpoints.py        # Classic endpoints (one small class each).
    clc_endpoints_accounts.py  # Accounts (composite: .users / .groups).
    pro_scripts.py          # Pro Scripts endpoint.
    pro_mdm_commands.py     # Pro MDM commands (send_command + ~30 convenience wrappers).
    pro_app_installers.py   # Pro App Installers endpoint.
    pro_dock_items.py       # Pro Dock Items endpoint.
api_schemas/
  classic.json, pro.json    # Jamf's own API schemas — query, never read whole (see below).
  api-reference-url.txt     # Pointer to Jamf's human-readable docs: https://developer.jamf.com/jamf-pro/reference
tests/
  conftest.py               # `responses` harness: mocked_responses, tenant / pro_api / classic_api fixtures, header and concurrency helpers.
  <module>_test.py          # One offline pytest file per source module (mocks the network).
  integration/              # Live min/max lifecycle tests against a real tenant — spec-driven (one spec per resource), opt-in via `make test-integration`, never run by default.
COVERAGE.md                 # Which API resources the SDK wraps vs. doesn't — update when adding an endpoint.
Makefile                    # The single dev entrypoint (`make help` lists targets). Docs only ever point at make targets.
uv.lock                     # Locked runtime + dev dependency set; `make setup` installs exactly this.
.env.example                # Template for the live-tenant vars; copy to `.env` (gitignored) for `make test-integration`.
```

---

## The two helpers every endpoint uses

Endpoints never hardcode URLs or headers. They ask the API object:

- **`self._api.url(target=None)`** — base URL for this API version.
  - Classic ignores `target`: `https://<fqdn>/JSSResource`.
  - Pro **requires** `target` = the API version as a string: `self._api.url("2")` → `.../api/v2`. Versions differ per endpoint (scripts=v1, mdm/commands=v2, app-installers=v1) — the version prefix on the path in `pro.json` is the value to pass.
- **`self._api.header(key)`** — header set from `constants.py`. Shape: `header("read")["json"]`, `header("create-update")["xml"]`, `header("delete")["json"]`, `header("image")`. Classic writes use `["xml"]`; Pro uses `["json"]`.

---

## Conventions (follow these — the codebase is consistent)

1. **Endpoints return a `requests.Response`.** Don't `.json()` inside an endpoint or invent return models. Two places synthesize a Response instead of passing the raw one straight back, and both still hand back a `Response`: `ProEndpoint.get_all` (paginates every page and aggregates them into one Response whose body is `{"totalCount": N, "results": [...]}`), and `clc_endpoints_accounts` `.users`/`.groups` (repackage the shared `/accounts` payload). Both use the shared `Endpoint._repackage_response` helper; don't add another copy. Match the surrounding file unless you have the same reason.
2. **Classic write bodies are XML strings** passed as `data=`. Pro bodies are dicts passed as `json=`.
3. **One endpoint = one class.** Classic endpoints subclass `ClassicEndpoint` and usually only set `_uri` and `_name` — they inherit full CRUD. Pro endpoints subclass `ProEndpoint` and usually only set `_uri`, `_name`, and `_version` — they inherit the same full CRUD (with a paginating `get_all`), the Pro mirror of `ClassicEndpoint`. Hand-roll a method only when a resource deviates. **Action/verb endpoints** (send-command style, e.g. `pro_mdm_commands`) subclass the bare `Endpoint` so they don't inherit CRUD.
4. **`_uri`** is the path segment appended to the base URL (leading slash, e.g. `/computers`). **`_name`** is the snake_case key used for response browsing / `.name()`; keep it aligned with Jamf's JSON top-level key where one exists.
5. **Docstrings on every public class/method.** `.pylintrc` exempts `_private` names (`no-docstring-rgx=^_`) but everything public needs one. Comments explain **why**, never what.
6. **`snake_case`** functions/vars/args, **`PascalCase`** classes, **`UPPER_CASE`** constants (all enforced by pylint). Max line length **150**.
7. **Log through the injected logger** (`self._logger` / `self._api._logger`), not `print`. `safe_mode=True` (default) redacts headers from debug logs — don't log secrets around it.
8. **Style reference is [PEP 8](https://peps.python.org/pep-0008/); docstrings follow [PEP 257](https://peps.python.org/pep-0257/).** pylint (`make lint`) is the only lint gate. There is no auto-formatter — don't add one.

---

## How to add an endpoint

> For a fuller, worked walkthrough of each endpoint variant (simple/composite Classic, simple/action Pro), including test templates and schema-query recipes, see [`EXPANDING.md`](EXPANDING.md). This section is the quick version.

### Classic endpoint (inherits CRUD for free)

1. Add the class in `jamfpy/endpoints/clc_endpoints.py`:
   ```python
   class Buildings(ClassicEndpoint):
       """Endpoint for managing building locations in Jamf Pro."""
       _uri = "/buildings"
       _name = "buildings"
   ```
   You now have `get_all`, `get_by_id`, `update_by_id`, `create`, `delete_by_id`, `name` from `ClassicEndpoint`.
2. Import it in `jamfpy/client/client.py` (the `from ..endpoints.clc_endpoints import (...)` block).
3. Attach it in `ClassicAPI.__init__`: `self.buildings = Buildings(self)`.

### Pro endpoint (inherits CRUD for free)

1. Add the class in a `jamfpy/endpoints/pro_<thing>.py` module, subclass `ProEndpoint`, and set `_uri`, `_name`, and `_version` (the `/v{n}` prefix on the path in `pro.json`):
   ```python
   from .models import ProEndpoint

   class Things(ProEndpoint):
       """Endpoint for managing things in the modern Jamf Pro API."""
       _uri = "/things"
       _name = "things"
       _version = "1"
   ```
   You now have `get_all`, `get_by_id`, `create`, `update_by_id`, `delete_by_id`, `name` from `ProEndpoint` — the Pro mirror of `ClassicEndpoint`, but with versioned URLs (`url(self._version)`), `/{id}` id paths (**no** `/id/`), JSON bodies (`json=`), and a `get_all` that transparently paginates the `page`/`page-size` cursor and aggregates every page into **one** Response (`{"totalCount": N, "results": [...]}`). Hand-roll a method only when a resource deviates. **Verbs-not-CRUD** endpoints (send-command style) subclass the bare `Endpoint` instead — see `pro_mdm_commands.py`.
2. Import it in `jamfpy/client/client.py` and attach it in `ProAPI.__init__` (e.g. `self.things = Things(self)`).

### Querying the API schemas (never read them whole)

`api_schemas/pro.json` is **~1.9 MB** and `classic.json` is **~320 KB** — reading either in full wastes your context. Query them instead:

```bash
# Pro: find the path. The /v1, /v2... prefix IS the version string url() needs.
uv run python -c "import json; print([p for p in json.load(open('api_schemas/pro.json'))['paths'] if 'script' in p])"

# Pro: full spec for one path (methods, params, request body shape)
uv run python -c "import json; print(json.dumps(json.load(open('api_schemas/pro.json'))['paths']['/v1/scripts'], indent=2))"

# Classic: NOT valid JSON (trailing commas — json.load raises). grep it instead:
grep -o '"/[^"]*buildings[^"]*"' api_schemas/classic.json | sort -u
```

Human-readable docs, if the schema isn't enough: https://developer.jamf.com/jamf-pro/reference (also in `api_schemas/api-reference-url.txt`).

### If you need a new URL, header set, or auth route

Edit the dicts in `jamfpy/client/constants.py` (`DEFAULT_HTTP_CONFIG_URLS` / `DEFAULT_HTTP_CONFIG_HEADERS`). Everything else reads from there via `HTTPConfig`.

### Definition of done

- [ ] Class added, with docstrings on every public class/method.
- [ ] Imported in `jamfpy/client/client.py` and attached in `ProAPI.__init__` / `ClassicAPI.__init__`.
- [ ] Path, version, and body shape verified against the schema (queries above, not a full read).
- [ ] Smoke test passes: `uv run python -c "import jamfpy; print(jamfpy.Tenant)"`
- [ ] Tests pass: `make test` — and a new endpoint gets a `tests/<module>_test.py` covering the request it sends (mocked with `responses`; see Quality gates).
- [ ] Lint passes: `make lint`
- [ ] Type check passes: `make typecheck`
- [ ] Coverage gate passes: `make coverage` (or run all three gates CI runs with `make check`).
- [ ] No live-request testing outside `tests/integration/` (the unit suite mocks the network — see Quality gates), no edits to version/CHANGELOG.
- [ ] [`COVERAGE.md`](COVERAGE.md) updated: move the resource from *Not yet covered* into the covered table and bump the summary counts — and add a row to the *Live integration test coverage* table (with a min/max spec in `tests/integration/` if the resource supports CRUD, or an N/A row with the reason if it doesn't).
- [ ] If asked to commit: Conventional Commit message (`feat:` for a new endpoint).

---

## Architecture & request lifecycle

```
Tenant(fqdn, auth_method, creds..., timeout=30.0, retries=RetryConfig())
  ├─ builds ONE Auth object (OAuth or BasicAuth)   ← no network call: auth is lazy
  ├─ tenant.hooks   = Hooks()          ← one hook registry, shared by both APIs
  ├─ tenant.pro     = ProAPI(...)      ┐ both APIs share the SAME auth object and hooks; each has its own Session
  └─ tenant.classic = ClassicAPI(...)  ┘ (requests' default headers + User-Agent: jamfpy/<version>) and RetryPolicy

tenant.authenticate()                  ← optional: fetch a token now, to fail fast

tenant.classic.computers.get_all()
  → ClassicEndpoint builds a requests.Request (url via api.url(), headers via api.header())
  → api.do(request, timeout=None)
       loop: attempt = 1, 2, ... (at most 1 + RetryConfig.total attempts)
       → auth.token() → check_token()  ← first fetch, or refresh if expired / within buffer, under the Auth lock (never retried, no hooks)
       → request.headers = {**endpoint headers, "Authorization": "Bearer <token>"}   ← per attempt, never on the session
       → session.prepare_request()
       → hooks: before_request(prepared, ctx)
       → merge_environment_settings() + session.send(prepped, timeout=<configured or override>, **settings)
            got a response → hooks: after_response(prepared, response, ctx)   (any status)
            send raised    → no after_response
       → RetryPolicy.delay(): retryable, not exhausted, Retry-After within max_backoff?
            no  → return the raw requests.Response, or raise the exception (ERROR log if it gave up on a retryable one)
            yes → WARNING log → hooks: on_retry(prepared, ctx, reason, delay) → sleep(delay) → next attempt
```

- **`API.do()` (`client/api.py`) is the one place every request goes through.** It puts `Authorization: Bearer <token>` from `auth.token()` on each `Request`'s own headers before `prepare_request` — endpoints never touch auth. It builds a new dict over the endpoint's headers rather than updating them in place, because endpoints pass the shared header sets from `constants.py`, which must never carry a token. requests merges request headers over session headers case-insensitively, so the per-request `Authorization` (and an endpoint's `accept`/`content-type`) win over any session default.
- **Auth is lazy.** `Tenant()` makes no network call. `Auth` starts with no token (`_token_str = None`) and `token_expiry = 0.0`, which reads as expired, and `token()` fetches one on demand, so the first request does it. Bad credentials (`JamfAuthError`) or an unreachable FQDN (the requests exception) therefore raise on the first request, not at construction. `Tenant.authenticate()` fetches a token immediately for callers who want to fail fast; the live `tenant` fixture calls it. A `ProAPI`/`ClassicAPI` built directly from an `Auth` needs no setup either. `invalidate()` before any token exists returns `True` without a request.
- **Thread safety.** One `Tenant` can serve concurrent callers. `do()` never mutates the `Session`: its headers (requests' defaults plus `User-Agent`), `verify` and `cert` are set once at construction, and per-request state (the `Authorization` header, the timeout) travels with each request. What concurrent callers share is the `Session`, which holds the connection pool, the cookie jar and the redirect cache. The SDK mutates none of them per request, and the pool is the part urllib3 guards, so one session per API is fine. The token is the only shared state that changes as requests run, and `Auth` guards it with a `threading.RLock`. (The hook registry is shared too, but changes only when a caller registers or removes a hook; `Hooks` guards its lists with its own lock, see Request hooks. Everything else `do()` touches per attempt, the retry counter and the `RequestContext`, is local to the call.) `token()` does a double-checked refresh: a lock-free check, then, if a fetch or refresh is due, the lock and a re-check, because another thread may have refreshed while this one waited. So N threads that hit an expired token make one token request and all use its result. `set_new_token()`, `_keep_alive_token()` and `invalidate()` take the same lock, so no thread swaps the token out from under another. The lock is re-entrant because `token()` holds it while `check_token()` calls `set_new_token()` / `_keep_alive_token()`. A failing fetch is not shared: the lock is held across the fetch and every waiting thread re-checks and re-tries it in turn, so N concurrent first requests against a dead token endpoint take up to N times the timeout. That is by design (simple and correct); the API retry loop never retries auth calls.
- **Timeout.** `Tenant(timeout=30.0)` takes seconds or a `(connect, read)` tuple, as requests does (type alias `jamfpy.Timeout`; default `DEFAULT_TIMEOUT` in `constants.py`). It applies to every API call and every auth call (token, keep-alive, invalidate). `OAuth`, `BasicAuth`, `ProAPI` and `ClassicAPI` take the same `timeout=` keyword. `api.do(request, timeout=...)` overrides it for that API request only; the default `None` means the configured value. A token fetch the call triggers uses the configured `Tenant(timeout=...)`, not the override.
- **User-Agent.** Each API's session sends `User-Agent: jamfpy/<version>`, with the version from `importlib.metadata` (`jamfpy/unknown` when jamfpy isn't installed as a distribution). It is set at construction, including on a `session=` you pass in, and the auth calls send the same header. requests' other defaults (`Accept-Encoding`, `Accept: */*`, `Connection: keep-alive`) go out too; an endpoint's `accept` replaces `Accept` per request.
- **API requests are TLS-verified by default and honour the environment like the auth calls.** `API.__init__` sets `session.verify` (`True`, or `verify_path` as a CA-bundle path) and `session.cert` (`cert_path`, or `None`) once, including on a `session=` you pass in. `do()` resolves `verify`/`cert`/`proxies` through `Session.merge_environment_settings` and passes them to `session.send`, because `send` skips the env merge that `Session.request` does. So API requests pick up `REQUESTS_CA_BUNDLE`/`CURL_CA_BUNDLE` and `HTTP_PROXY`/`HTTPS_PROXY`/`NO_PROXY` exactly as the auth calls (which go through `requests.request()`) do; an explicit `verify_path` wins over the env bundle, and a request is never sent unverified. `Tenant` checks both paths exist and stores them as `str`.
- **`auth.token()` → `check_token()`** checks for a token, its expiry, and a refresh buffer. No token yet or expired ⇒ new token (the first fetch logs at DEBUG, not as an expired token). Within buffer ⇒ OAuth re-fetches, Basic/Bearer calls keep-alive. The buffer is `token_exp_threshold_mins` (default 20), capped at half the current token's lifetime (0 s if the lifetime is 0 or negative), which `Auth` records whenever a token is set (OAuth: `expires_in`; Bearer: `expires` minus now, at issue and on keep-alive). The cap exists because API clients can issue tokens shorter than the buffer (the dev tenant's are 299 s). The clamp is silent unless the configured buffer is at least the whole token lifetime (the case that used to raise); then `Auth` logs one WARNING per instance naming the buffer it uses instead. A freshly issued token is always used, never rejected.
- **`close()` → `auth.invalidate()`** POSTs `{fqdn}/api/v1/auth/invalidate-token`. Pro and Classic share one `Auth`, so closing either invalidates the token for both. If invalidation fails, `close()` logs a WARNING and still marks the API closed.

---

## Retries

`API.do()` retries a failed attempt itself, in a loop. It does not use urllib3's `Retry`, which cannot fire the `on_retry` hook, log per attempt or re-apply a refreshed token. Configure it with `Tenant(retries=RetryConfig(...))`; the default is `RetryConfig()`, and `retries=None` turns retries off (one attempt, and the loop logs nothing). `API`, `ProAPI` and `ClassicAPI` take the same `retries=` keyword. Auth calls (token fetch, keep-alive, invalidate) are never retried: a token fetch that fails inside `do()` raises out of it on that attempt.

`RetryConfig` (`jamfpy/client/retry.py`, exported as `jamfpy.RetryConfig`) is a frozen dataclass, so one instance is safe to share:

| Field | Default | Meaning |
|---|---|---|
| `total` | `3` | Retries after the first attempt, so at most four attempts. Attempts are numbered from 1 in logs and hooks. |
| `backoff_factor` | `0.5` | Base of the exponential backoff. |
| `max_backoff` | `30.0` | Cap on the computed delay, and the most `Retry-After` the loop will honour. |
| `jitter` | `True` | Full jitter on the computed delay. |
| `statuses` | `(429, 500, 502, 503, 504)` | Statuses that are retried. |
| `methods` | `("GET", "HEAD", "OPTIONS", "PUT", "DELETE")` | Methods retried after a status, read timeout or connection error (compared case-insensitively). |
| `retry_post` | `False` | Also retry POST under those rules. POST is not idempotent: a resend can create a second record. |

The fields are validated when the config is built, so a typo fails at construction rather than mid-outage: `total` must be an `int` and `backoff_factor` and `max_backoff` numbers, none of them negative or NaN, and `statuses` (ints) and `methods` (strings) must be collections, not a bare string (`methods="GET"` raises `ValueError` and shows the one-item tuple form, `methods=("GET",)`). Any bad value raises `ValueError`. Lists and sets are accepted and stored as tuples, which keeps the frozen config hashable.

What is retried:

- **A status in `statuses`**: for a method in `methods`, plus POST when `retry_post`. Any other status, or a listed status on any other method (PATCH, a POST without `retry_post`), is returned at once.
- **`requests.ConnectTimeout`**: every method, POST included, whatever `retry_post` says. The connection never opened, so nothing reached the server.
- **`requests.ReadTimeout` and `requests.ConnectionError`**: the same method rule as a status, because the server may have processed the request. `ProxyError` subclasses `ConnectionError` and is treated as one.
- **Nothing else.** `SSLError` also subclasses `ConnectionError`, so the policy checks it first and lets it propagate at once (a TLS failure won't fix itself on a resend). `ConnectTimeout` is checked before the `ConnectionError` rule too, since it subclasses both `ConnectionError` and `Timeout`. `InvalidURL`, `MissingSchema`, `ChunkedEncodingError` and every other exception propagate at once.

Delay before the next attempt, when attempt `n` failed:

- **Computed:** `min(backoff_factor * 2**(n-1), max_backoff)`, then, with `jitter`, multiplied by a uniform draw in [0, 1) ("full jitter": capped first, so late retries still spread over the whole window). Without jitter the defaults give 0.5 s, 1 s, 2 s.
- **`Retry-After`:** on a retryable response it replaces the computed delay, unjittered. It may be integer seconds or an HTTP-date (RFC 9110), which is parsed with `email.utils.parsedate_to_datetime` and measured from the current UTC time (a naive `-0000` date is read as UTC; a date in the past means no wait). A value that parses as neither is ignored and the computed delay applies. If the value is more than `max_backoff`, the loop stops and returns that response, because sleeping less than the server asked would only earn another 429. A `Retry-After` on a status that isn't retried changes nothing.

Each attempt re-prepares the `Request` and re-applies `Authorization` from `auth.token()`, so a token that expires during a backoff is refreshed before the resend. The body must therefore be replayable: a `str`/`bytes`/dict `data=` or `json=`, as every endpoint passes. A file-like or generator body would be used up by the first attempt.

When retries run out, a status retry returns the last response (`do()` never raises on a status) and a timeout or connection retry raises the last exception.

Logging goes through the API's logger. Each retry logs one WARNING with the method, URL, the number of the attempt that failed, the reason (`HTTP 503`, or the exception's class and message) and the delay. Giving up on an outcome that was still retryable (retries exhausted, or a `Retry-After` beyond `max_backoff`) logs one ERROR. A clean first attempt, a status that isn't retried and an exception that isn't retried add nothing at WARNING or above. At DEBUG each attempt logs three lines, `prepping` and `sending` (method, URL, headers redacted under `safe_mode`) and `Response: <method> <url> -> <status>`, each ending `(attempt n)`, so a retried request reads as one trace; the response line is neutral because it runs for every status, including one about to be retried.

For tests, `API.__init__` (and `ProAPI`/`ClassicAPI`) take keyword-only `sleep: Callable[[float], None] = time.sleep` and `random_source: Callable[[], float] = random.random`. They are deliberately not on `Tenant`. The decisions live in `RetryPolicy` (`retry.py`, internal), which the API keeps as `_retry` (`None` when retries are off). The unit suite injects a recording sleep and a fixed random source, so no test ever waits (see Quality gates).

---

## Request hooks

`tenant.hooks` is a `Hooks` object (`jamfpy/client/hooks.py`; `Hooks` and `RequestContext` are exported from `jamfpy`). `Tenant` creates one and both APIs share it. `API`, `ProAPI` and `ClassicAPI` take `hooks: Hooks | None = None`; `None` gives that API a private, empty `Hooks`, so nothing fires.

Registering: `before_request(fn)`, `after_response(fn)` and `on_retry(fn)` each register `fn` and return it, so each also works as a decorator (`@tenant.hooks.after_response`). `remove(fn)` removes `fn` from every list it is in, every time it was registered; removing a function that isn't registered does nothing. The lists are guarded by a lock and copied before each dispatch, so registering or removing is safe from any thread and from inside a hook; a change applies from the next dispatch.

Signatures:

- `before_request(prepared: PreparedRequest, ctx: RequestContext) -> None`
- `after_response(prepared: PreparedRequest, response: Response, ctx: RequestContext) -> None`
- `on_retry(prepared: PreparedRequest, ctx: RequestContext, reason: Response | Exception, delay: float) -> None`

`RequestContext` is a frozen dataclass:

- `tenant: str`: the tenant's FQDN. It is a plain string so hooks also work for an API built without a `Tenant`, and so a hook never receives the object that holds the credentials.
- `api: str`: `"pro"` or `"classic"`.
- `attempt: int`: 1 for the first attempt, then one more per retry.
- `started: float`: `time.monotonic()` at the start of the attempt, taken after the request is prepared, so a token fetch isn't counted.

The contract:

- Hooks fire per HTTP attempt, not per SDK operation. They fire for API requests only, never for auth calls (token fetch, keep-alive, invalidate).
- For each attempt: `before_request`, then the send, then exactly one of `after_response` (for any response received, whatever its status, including one that is about to be retried) or nothing, when the send raised.
- If a retry follows, `on_retry` fires after that and before the sleep, with the response or the exception as `reason` and the delay about to be slept as `delay`.
- `ProEndpoint.get_all` runs this sequence once per page. `ctx.attempt` lets a consumer tell retries apart.
- Return values are ignored. Mutating the arguments is unsupported.
- A hook that raises is logged at WARNING, with the hook's `__qualname__` (its `repr` for a callable without one) and the traceback, and the request carries on. The remaining hooks still run.
- Hooks may run on worker threads, not only the caller's, and from several threads at once (concurrent callers of one `Tenant`, or SDK worker threads such as page fetchers), so they must be thread-safe.
- The prepared request carries the real `Authorization` header. A consumer that persists requests redacts it itself.

---

## Auth: user-facing vs internal names (footgun)

The string you pass to `Tenant(auth_method=...)` is **not** the same as the internal method name:

| You pass (`VALID_AUTH_METHODS`) | Class | Internal `_method` (URL/header lookup) |
|---|---|---|
| `"oauth2"` | `OAuth` (client_id + client_secret) | `"oauth"` |
| `"basic"` | `BasicAuth` (username + password, or `basic_auth_token`) | `"bearer"` |

Use `"oauth2"` / `"basic"` at the `Tenant` layer. The `"oauth"` / `"bearer"` strings are internal only.

---

## Quality gates & workflow

- **Setup:** install [uv](https://docs.astral.sh/uv/), then `make setup` (`uv sync`). It creates the project virtualenv from `uv.lock` with the runtime dependency plus the `dev` dependency group in `pyproject.toml` (`pytest`, `pytest-cov`, `responses`, `pylint`, `mypy`). Run everything through `make` (`make help` lists the targets); each target calls `uv run`, which keeps the virtualenv in step with the lock. To change a dependency, edit `pyproject.toml`, run `uv lock`, and commit `uv.lock` with it.
- **CI.** `.github/workflows/ci.yml` runs on every pull request (no base-branch filter, so stacked PRs are checked too) and every push to `main`. Three jobs: `lint` (Python 3.13, `make lint`), `typecheck` (3.13, `make typecheck`) and `test` (matrix 3.15 / 3.14 / 3.13, `make coverage`). Each job uses `astral-sh/setup-uv` pinned to `v10.3.0`, `uv python install <version>`, `uv sync --frozen`, then the make target, with `UV_PYTHON` and `UV_FROZEN=1` in the job env so `uv run` inside make neither picks another interpreter nor rewrites the lock. No `actions/setup-python`. Locally, `make check` runs the same three gates; `make check-matrix` repeats `make check` once per interpreter in `PYTHON_VERSIONS` (default `3.15 3.14 3.13`), each in its own per-version virtualenv (via `UV_PROJECT_ENVIRONMENT`).
- **Lint — a CI gate.** `make lint` runs pylint over every tracked `.py` file and **fails under 9.0**. Baseline is ~9.9/10. Config is `.pylintrc` (`py-version=3.13`; max line 150; `missing-module-docstring`, `too-many-arguments`, `duplicate-code` disabled). Keep the score ≥ 9.0 — don't blanket-disable checks to get there.
- **Types — a CI gate.** `jamfpy/` is fully type-hinted, and `make typecheck` runs mypy in strict mode (config in `pyproject.toml` `[tool.mypy]`) over it; the package ships `jamfpy/py.typed` so downstream type checkers use the hints. New code must be hinted too: no bare `def f(x):`, every parameter and return annotated (strict mypy rejects anything less). Endpoints reference `API` through the `typing.TYPE_CHECKING` import at the top of `jamfpy/endpoints/models.py` (reuse it in any endpoint module that needs the name): the client layer imports the endpoints at runtime, so endpoints import `API` for hints only and the import graph cannot become a cycle. `# type: ignore` needs an error code and a one-line reason; prefer `cast()` when the narrowing is genuinely known. `tests/` is not type-checked.
- **Tests — a CI gate.** `make test` runs the unit suite; `make coverage` (what CI runs, on all three interpreters) adds branch coverage of `jamfpy/` and **fails under 90%** (baseline 97%).
  The unit suite lives in `tests/`, one `<module>_test.py` per source module (config in `pyproject.toml` `[tool.pytest.ini_options]` — note the non-default `*_test.py` naming). It is **fully offline and deterministic**: tests drive the real SDK stack and mock only the network edge, with [`responses`](https://github.com/getsentry/responses). `responses` replaces `HTTPAdapter.send`, so the auth calls (`requests.request()`) and every endpoint call (`API.do()` → `Session.send`) both land in one `RequestsMock`; an unregistered URL raises `ConnectionError`, so nothing can leak to a live tenant. `tests/conftest.py` provides `mocked_responses` (an active `RequestsMock` that fails the test if a registration goes unused), `response_registry` (the registry class behind it; `tests/models_test.py` overrides it with `OrderedRegistry` so a paginated `get_all` that repeats a URL fails the test instead of looping), `tenant` (a real OAuth `Tenant`, authenticated with `authenticate()` against the token endpoint `mocked_responses` answers; the call log is reset after that, so `mocked_responses.calls` holds only the test's own requests; its APIs keep the default `RetryConfig` but append each backoff delay to the `sleeps` list instead of sleeping, so a retried status costs no time; at teardown it fails the test if any call other than a token request went out without the `Authorization: Bearer` header), `pro_api` / `classic_api` (its two APIs), `make_classic_api` (builds a `ClassicAPI` on the tenant's `Auth` with whatever `retries`, `hooks`, `logger` or `sleep` a test passes, defaulting to a recording `sleep` and a `random_source` fixed at 0.5), `warning_logger` (a propagating WARNING-level logger for `caplog` tests), the helpers `register_oauth_token`, `with_bearer` and `sent_headers`, and for the concurrency tests `run_together` (calls a function from `THREADS` = 20 threads released together by a `threading.Barrier`, with timeouts so a deadlock fails instead of hanging) and `register_slow_oauth_token` (a token endpoint slow enough that, without the `Auth` lock, every thread would reach it). A lazy-auth test builds its own `Tenant` inside `mocked_responses` and registers the token endpoint only if it authenticates or sends a request. An endpoint test registers the URL it expects, calls the endpoint through `pro_api` / `classic_api`, and asserts on `mocked_responses.calls[-1].request`: method, full URL (with the `/JSSResource` or `/api/v{n}` prefix), headers (`sent_headers(req) == with_bearer(<config header set>)`: requests' session defaults with the jamfpy `User-Agent`, the config header set over them, and the `Authorization: Bearer` header the real `Auth` injects; names lower-cased) and body (`request.body`: the XML string for Classic, JSON for Pro). Auth tests register the four auth URLs (`/api/oauth/token`, `/api/v1/auth/token`, `/api/v1/auth/keep-alive`, `/api/v1/auth/invalidate-token`) the same way. The one exception is the TLS tests in `api_test.py`: they patch `HTTPAdapter.send` directly, with a stub Auth and no `responses` mock, because they assert the exact keyword arguments the adapter receives (`verify`, `cert`, `proxies`, `timeout`), the point where `verify=None` used to become an unverified connection. Other timeout tests read the value `responses` records on `mocked_responses.calls[i].request.req_kwargs["timeout"]`. `tests/retry_test.py` scripts each attempt with `OrderedRegistry` (one registration per attempt, in order) and raises network failures by registering an exception as the `body` (`body=requests.exceptions.ConnectTimeout(...)`), which `responses` raises from the send; `tests/hooks_test.py` records hook calls in lists, tests that a hook registered (or re-registered by itself) from inside a dispatch only runs from the next one, and includes a 20-thread test where workers register and remove hooks while others dispatch. **Never exercise a live tenant from unit tests** — add tests by registering responses, following the existing files. The one sanctioned exception is `tests/integration/`: marker-gated live min/max lifecycle tests, deselected by default (`addopts = "-m 'not integration'"`), run only by `.github/workflows/integration-test.yml` (workflow_dispatch + PRs to main, also on uv: setup-uv, `uv sync --frozen`, `make test-integration`; needs the repo var/secrets below and skips on forks/unconfigured repos) or locally via `make test-integration` with `JAMFPRO_INSTANCE_FQDN` / `JAMFPRO_CLIENT_ID` / `JAMFPRO_CLIENT_SECRET` set (repo Actions variable + secrets in CI). Locally the target loads `.env` when it exists (copy `.env.example`); if any of the three vars is unset or empty it exits non-zero with a one-line reason before pytest starts, and the live `tenant` fixture in `tests/integration/conftest.py` also fails (never skips) as a backstop. That live `tenant` (a real tenant, built from the environment) and the unit `tenant` in `tests/conftest.py` (a fake token served by `responses`) are different fixtures that share a name; each applies only to the tests under its own directory. The suite is spec-driven: each resource is a small dict (min/max payload builders) in `tests/integration/clc_resources_live_test.py` / `pro_resources_live_test.py`, run through the shared runners in `tests/integration/lifecycle.py`; per-resource status is tracked in `COVERAGE.md` → *Live integration test coverage*. Some tests deliberately **characterize known quirks** (e.g. `new_logger` stacking a fresh handler per call, `ClassicEndpoint.delete_by_id` sending no headers of its own); the tests that pin current behaviour carry a `# Characterises current behaviour` comment, so `grep -rn "Characterises current behaviour" tests` finds them (the `new_logger` test says `KNOWN QUIRK` instead); if you intentionally fix one of those, update its test in the same change. Test files carry a small `# pylint: disable=...` header for test idioms (fixtures, `_private` access) — keep new ones lint-clean too.
- **Commits drive releases — use Conventional Commits.** `release-please` runs on `main` (`feat:` → minor, `fix:` → patch, `chore:`/`docs:` → no release) and opens the release PR + updates `CHANGELOG.md` and the version in `pyproject.toml`. PyPI publish (`pypi-publish.yml`) is **manual** (`workflow_dispatch`). Don't hand-edit the version.
- **Branch/PR:** work on a branch, open a PR to `main`. Don't commit or push unless asked.

---

## Known rough edges (don't "fix" without asking)

- **`logger.new_logger`** adds a fresh `StreamHandler` each call for a given name — repeated construction of the same-named logger can duplicate log lines.
- **`ProEndpoint` provides shared CRUD + pagination** (mirroring `ClassicEndpoint`). `ProEndpoint.get_all` paginates and aggregates into one Response; its `update_by_id` uses PUT and is a best-effort default (some resources are read-only or need PATCH — override or don't use it). `pro_app_installers` inherits `get_all`/`update_by_id` even though those aren't in `pro.json` for that resource — treat them as best-effort there.
- **`api_schemas/classic.json` is not strictly valid JSON** (trailing commas) — `json.load` raises. Query it with grep, not a JSON parser.

---

## Quick reference

```python
import logging

import jamfpy

tenant = jamfpy.Tenant(
    fqdn="https://your-instance.jamfcloud.com",
    auth_method="oauth2",              # or "basic"
    client_id="...", client_secret="...",   # or username=..., password=...
    timeout=30.0,                      # the default; or (connect, read). API and auth calls alike.
    retries=jamfpy.RetryConfig(),      # the default; e.g. RetryConfig(total=5, retry_post=True). retries=None turns retries off.
)
tenant.authenticate()                  # optional: fetch the token now (fail fast) instead of on the first request

# Hooks fire per HTTP attempt (API requests only) and must be thread-safe.
@tenant.hooks.after_response
def log_status(prepared, response, ctx):
    logging.getLogger("audit").info("%s %s -> %s (attempt %d)", prepared.method, prepared.url, response.status_code, ctx.attempt)

tenant.hooks.remove(log_status)

# Classic (raw requests.Response back)
resp = tenant.classic.computers.get_all()
one  = tenant.classic.computers.get_by_id(123)
tenant.classic.buildings.create("<building>...</building>")   # XML body

# Pro
scripts = tenant.pro.scripts.get_all()
tenant.pro.mdm.lock_device(["<managementId>"], message="...", pin="123456")

tenant.classic.close()   # invalidates the token
```
