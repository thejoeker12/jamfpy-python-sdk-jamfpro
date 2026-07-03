# AGENTS.md

Entrypoint for AI agents and junior devs working on **jamfpy** — a hand-authored Python SDK for the Jamf Pro server APIs. `README.md` is intentionally empty; this file is the source of truth for how the codebase is put together and how to change it safely.

**Route by task:**

- **Adding an endpoint** (the most common job) → jump to **How to add an endpoint**.
- **Touching auth, tokens, or request plumbing** → read **Architecture & request lifecycle** first.
- **Anything else** → skim **Conventions** and **Quality gates**, and read **Known rough edges** before "fixing" anything you didn't come here to change.

---

## What this SDK is

Jamf Pro exposes **two** HTTP APIs and this SDK wraps both:

| API | Jamf name | Base path | Payloads | This SDK |
|-----|-----------|-----------|----------|----------|
| **Classic** | JSS Resource API | `/JSSResource` | **XML** for writes, JSON readable | `tenant.classic.*` |
| **Pro** | Modern Jamf Pro API | `/api/v{n}` (versioned per-endpoint) | **JSON** | `tenant.pro.*` |

The SDK is a thin, explicit wrapper: auth/token lifecycle, URL/header assembly, logging — then it hands back the **raw `requests.Response`**. It does *not* deserialize into models (two documented exceptions, see Conventions). Only runtime dependency is `requests`. Python **>= 3.10** (`match`, `X | Y` unions).

---

## Repo layout

```
jamfpy/
  __init__.py               # public surface: Tenant, OAuth, BasicAuth, API, ProAPI, ClassicAPI, new_logger
  client/
    tenant.py               # Tenant — the main entrypoint. Validates config, builds Auth + both APIs.
    auth.py                 # Auth base + OAuth + BasicAuth. Token acquisition, refresh, keep-alive, invalidate.
    api.py                  # API base class. do() is the central request executor.
    client.py               # ProAPI / ClassicAPI. Wire endpoint objects onto each API.
    http_config.py          # HTTPConfig wrapper around the URL/header dicts.
    constants.py            # Default URLs, header sets, timeouts, VALID_AUTH_METHODS. Edit URLs/headers HERE.
    exceptions.py           # JamfAPIError, JamfpyConfigError, JamfpyInitError, JamfAuthError.
    logger.py               # new_logger() — per-tenant stdout logger.
    utility.py              # URL parsing, Jamf time->ISO fixups, XML helpers.
  endpoints/
    models.py               # Endpoint / ClassicEndpoint / ProEndpoint base classes.
    clc_endpoints.py        # Classic endpoints (one small class each).
    clc_endpoints_accounts.py  # Accounts (composite: .users / .groups).
    pro_scripts.py          # Pro Scripts endpoint.
    pro_mdm_commands.py     # Pro MDM commands (send_command + ~30 convenience wrappers).
    pro_app_installers.py   # Pro App Installers endpoint.
api_schemas/
  classic.json, pro.json    # Jamf's own API schemas — query, never read whole (see below).
  api-reference-url.txt     # Pointer to Jamf's human-readable docs: https://developer.jamf.com/jamf-pro/reference
tests/
  conftest.py               # FakeAPI double + make_response helper + shared fixtures.
  <module>_test.py          # One offline pytest file per source module (mocks the network).
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

1. **Endpoints return the raw `requests.Response`.** Don't `.json()` inside an endpoint or invent return models. Exceptions that *do* transform, and why: `pro_scripts.Scripts.get_all` (paginates and aggregates), `clc_endpoints_accounts` `.users`/`.groups` (repackage the shared `/accounts` payload). Match the surrounding file, not these outliers, unless you have the same reason.
2. **Classic write bodies are XML strings** passed as `data=`. Pro bodies are dicts passed as `json=`.
3. **One endpoint = one class.** Classic endpoints subclass `ClassicEndpoint` and usually only set `_uri` and `_name` — they inherit full CRUD. Pro endpoints subclass `ProEndpoint` (which is empty) and implement each method by hand.
4. **`_uri`** is the path segment appended to the base URL (leading slash, e.g. `/computers`). **`_name`** is the snake_case key used for response browsing / `.name()`; keep it aligned with Jamf's JSON top-level key where one exists.
5. **Docstrings on every public class/method.** `.pylintrc` exempts `_private` names (`no-docstring-rgx=^_`) but everything public needs one. Comments explain **why**, never what.
6. **`snake_case`** functions/vars/args, **`PascalCase`** classes, **`UPPER_CASE`** constants (all enforced by pylint). Max line length **150**.
7. **Log through the injected logger** (`self._logger` / `self._api._logger`), not `print`. `safe_mode=True` (default) redacts headers from debug logs — don't log secrets around it.

---

## How to add an endpoint

> For a fuller, worked walkthrough of each endpoint variant (simple/composite Classic, hand-rolled/action Pro), including test templates and schema-query recipes, see [`EXPANDING.md`](EXPANDING.md). This section is the quick version.

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

### Pro endpoint (implement methods by hand)

1. Create/extend a module (e.g. `jamfpy/endpoints/pro_<thing>.py`), subclass `ProEndpoint`, and build each `requests.Request` explicitly:
   ```python
   from requests import Request, Response
   from .models import ProEndpoint

   class Things(ProEndpoint):
       """Endpoint for managing things in the modern Jamf Pro API."""
       _uri = "/things"
       _name = "things"

       def get_by_id(self, target_id: int) -> Response:
           """Get a thing by its ID."""
           return self._api.do(Request(
               "GET",
               url=self._api.url("1") + f"{self._uri}/{target_id}",
               headers=self._api.header("read")["json"],
           ))
   ```
2. Import it in `client.py` and attach it in `ProAPI.__init__` (e.g. `self.things = Things(self)`).

### Querying the API schemas (never read them whole)

`api_schemas/pro.json` is **~1.9 MB** and `classic.json` is **~320 KB** — reading either in full wastes your context. Query them instead:

```bash
# Pro: find the path. The /v1, /v2... prefix IS the version string url() needs.
.venv/bin/python -c "import json; print([p for p in json.load(open('api_schemas/pro.json'))['paths'] if 'script' in p])"

# Pro: full spec for one path (methods, params, request body shape)
.venv/bin/python -c "import json; print(json.dumps(json.load(open('api_schemas/pro.json'))['paths']['/v1/scripts'], indent=2))"

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
- [ ] Smoke test passes: `.venv/bin/python -c "import jamfpy; print(jamfpy.Tenant)"`
- [ ] Tests pass: `.venv/bin/python -m pytest -q` — and a new endpoint gets a `tests/<module>_test.py` covering the Request it builds (mock only; see Quality gates).
- [ ] Lint passes: `.venv/bin/pylint $(git ls-files '*.py') --fail-under=9.0`
- [ ] No live-request "testing" attempted (the suite mocks the network — see Quality gates), no edits to version/CHANGELOG.
- [ ] If asked to commit: Conventional Commit message (`feat:` for a new endpoint).

---

## Architecture & request lifecycle

```
Tenant(fqdn, auth_method, creds...)
  ├─ builds ONE Auth object (OAuth or BasicAuth) and eagerly calls set_new_token()  ← network call at construction
  ├─ tenant.pro     = ProAPI(...)      ┐ both APIs share the SAME auth object
  └─ tenant.classic = ClassicAPI(...)  ┘

tenant.classic.computers.get_all()
  → ClassicEndpoint builds a requests.Request (url via api.url(), headers via api.header())
  → api.do(request)
       → _refresh_session_headers()  → auth.token() → check_token()  ← refreshes token if expired / within buffer
       → session.prepare_request() + session.send()
       → returns raw requests.Response
```

- **`API.do()` (`client/api.py`) is the one place every request goes through.** It re-applies the `Authorization` header from `auth.token()` before *every* send — endpoints never touch auth.
- **`auth.token()` → `check_token()`** checks expiry and a configurable buffer (`token_exp_threshold_mins`, default 20). Expired ⇒ new token. Within buffer ⇒ OAuth re-fetches, Basic/Bearer calls keep-alive.
- **`Tenant.__init__` makes a live auth request** (`set_new_token()`). Bad creds or an unreachable FQDN raise at construction, not on first API call.
- If you build a `ProAPI`/`ClassicAPI` directly (bypassing `Tenant`), call `auth.set_new_token()` yourself first — `token_expiry` is unset until then.

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

- **Setup:** a `.venv` already exists with `requests`, `pylint` + `pytest`. Use it (`.venv/bin/python`, `.venv/bin/pylint`, `.venv/bin/pytest`). If recreating: `python -m venv .venv && .venv/bin/pip install requests pylint pytest`.
- **Lint — a CI gate.** `.github/workflows/pylint.yml` runs on every push against Python 3.13 and **fails under 9.0**. Match it locally before you push:
  ```bash
  .venv/bin/pylint $(git ls-files '*.py') --fail-under=9.0
  ```
  Baseline is ~9.8/10. Config is `.pylintrc` (max line 150; `missing-module-docstring`, `too-many-arguments`, `duplicate-code` disabled). Keep the score ≥ 9.0 — don't blanket-disable checks to get there.
- **Tests — a CI gate.** `.github/workflows/pytest.yml` runs `pytest` on every pull request to `main` (Python 3.13). Run locally before you push:
  ```bash
  .venv/bin/python -m pytest -q
  ```
  The suite lives in `tests/`, one `<module>_test.py` per source module (config in `pyproject.toml` `[tool.pytest.ini_options]` — note the non-default `*_test.py` naming). It is **fully offline and deterministic**: the SDK's two network boundaries are mocked — patch `jamfpy.client.auth.request` for auth, and endpoints run against the `FakeAPI` double in `tests/conftest.py` that records the `requests.Request` they build. **Still never exercise a live tenant** — add tests by mocking, following the existing files. Some tests deliberately **characterize known quirks** (e.g. `pro_scripts.Scripts.get_all`'s inconsistent return, the no-op `time.replace` in `fix_jamf_time_to_iso`); if you intentionally fix one of those, update its test in the same change. Test files carry a small `# pylint: disable=...` header for test idioms (fixtures, `_private` access) — keep new ones lint-clean too.
- **Commits drive releases — use Conventional Commits.** `release-please` runs on `main` (`feat:` → minor, `fix:` → patch, `chore:`/`docs:` → no release) and opens the release PR + updates `CHANGELOG.md` and the version in `pyproject.toml`. PyPI publish (`pypi-publish.yml`) is **manual** (`workflow_dispatch`). Don't hand-edit the version.
- **Branch/PR:** work on a branch, open a PR to `main`. Don't commit or push unless asked.

---

## Known rough edges (don't "fix" without asking)

- **`/json`** at the repo root is a stray file (accidental capture of git output). It is not used by anything — ignore it.
- **`pyproject.toml`** contains leftover template cruft: `[project.scripts] my-script = ...` and the `pdf`/`rest` optional-dependencies are placeholders, not real. Don't rely on them.
- **`client.py`** sets `self.policies = Policies(self)` twice in `ClassicAPI.__init__` — harmless duplicate.
- **`pro_scripts.Scripts.get_all`** has an inconsistent return signature (returns `(resp, list)` on one path, `resp` on another) and hand-rolled pagination. Treat it as legacy; don't copy its shape into new endpoints.
- **`logger.new_logger`** adds a fresh `StreamHandler` each call for a given name — repeated construction of the same-named logger can duplicate log lines.
- **`ProEndpoint` is deliberately empty** — Pro endpoints share no base CRUD (the two APIs differ too much). That's by design, not an omission to fill in.
- **`api_schemas/classic.json` is not strictly valid JSON** (trailing commas) — `json.load` raises. Query it with grep, not a JSON parser.

---

## Quick reference

```python
import jamfpy

tenant = jamfpy.Tenant(
    fqdn="https://your-instance.jamfcloud.com",
    auth_method="oauth2",              # or "basic"
    client_id="...", client_secret="...",   # or username=..., password=...
)

# Classic (raw requests.Response back)
resp = tenant.classic.computers.get_all()
one  = tenant.classic.computers.get_by_id(123)
tenant.classic.buildings.create("<building>...</building>")   # XML body

# Pro
scripts = tenant.pro.scripts.get_all()
tenant.pro.mdm.lock_device(["<managementId>"], message="...", pin="123456")

tenant.classic.close()   # invalidates the token
```
