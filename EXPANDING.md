# EXPANDING.md

A worked, copy-pasteable guide to adding an endpoint to **jamfpy**. `AGENTS.md` is the
source of truth for architecture, auth, and the quality gates — read its
**Architecture & request lifecycle** section if you're unsure how a request flows. This file
zooms in on one job: **adding an endpoint of each of the four shapes the SDK actually uses.**

Everything below is verified against the current code. Match the surrounding file, not your
instincts about "how a client should look" — this SDK is a thin, explicit wrapper that hands
back the raw `requests.Response`.

---

## Pick your variant

The SDK has two APIs (Classic = XML writes under `/JSSResource`; Pro = JSON under
`/api/v{n}`) and four concrete endpoint shapes across them. Find your row, then jump to that
section.

| Your target | Standard CRUD? | Variant | Base class | Reference file |
|---|---|---|---|---|
| Classic resource, normal `/id/{id}` CRUD | yes | **A. Classic simple** | `ClassicEndpoint` | `clc_endpoints.py` |
| Classic resource with sub-resources / non-`/id/` paths | no | **B. Classic composite** | `Endpoint` + `ClassicEndpoint` children | `clc_endpoints_accounts.py` |
| Pro resource, CRUD | n/a | **C. Pro hand-rolled CRUD** | `ProEndpoint` | `pro_app_installers.py`, `pro_scripts.py` |
| Pro action / command endpoint (verbs, not CRUD) | n/a | **D. Pro action + wrappers** | `ProEndpoint` | `pro_mdm_commands.py` |

**By far the most common job is Variant A** — a Classic resource that gets full CRUD for free.
Start there unless your target clearly doesn't fit.

Whichever variant you pick, wiring is the same three steps (detailed per-variant below):

1. Define the class in the right `jamfpy/endpoints/` module.
2. Import it in `jamfpy/client/client.py`.
3. Attach it as `self.<attr> = MyEndpoint(self)` in `ClassicAPI.__init__` or `ProAPI.__init__`.

You never touch `jamfpy/__init__.py` — endpoints are reached through a client
(`tenant.classic.buildings`), not exported at the top level.

---

## The three helpers every endpoint uses

Endpoints never hardcode URLs, headers, or auth. They call three methods on `self._api`
(the API client instance passed into the constructor). Source: `jamfpy/client/api.py`.

### `self._api.url(target=None) -> str`

- **Classic** ignores `target` and returns the base, e.g. `https://<fqdn>/JSSResource`.
- **Pro** *requires* `target` = the API version string and interpolates it:
  `self._api.url("2")` → `https://<fqdn>/api/v2`. The version differs per endpoint
  (scripts = v1, mdm/commands = v2, app-installers = v1). **The version string is literally
  the `/v{n}` prefix on the path in `pro.json`** (see [Querying the schemas](#querying-the-api-schemas)).
  Calling a Pro `url()` with no target yields the literal string `.../api/vNone` — always pass one.

### `self._api.header(key: str)`

Indexes the `crud` header block from `jamfpy/client/constants.py`. The valid keys and their
exact shapes:

| Call | Returns |
|---|---|
| `header("read")["json"]` | `{"accept": "application/json"}` |
| `header("read")["xml"]` | `{"accept": "text/xml"}` |
| `header("create-update")["json"]` | `{"accept": "application/json", "content-type": "application/json"}` |
| `header("create-update")["xml"]` | `{"accept": "text/xml", "content-type": "text/xml"}` |
| `header("delete")["json"]` | `{"accept": "application/json"}` |
| `header("delete")["xml"]` | `{"accept": "text/xml"}` |
| `header("image")` | `{"accept": "image/*"}` — **flat, no `["json"]`/`["xml"]` sub-key** |

`read` and `delete` carry no `content-type` (those requests have no body). Classic writes use
`["xml"]`; Pro uses `["json"]`. An unknown key raises `KeyError("Invalid header key provided")`.

### `self._api.do(request: Request, timeout: int = 10) -> Response`

The single choke point every request goes through. It refreshes the session's
`Authorization` header from `auth.token()`, preps the `requests.Request`, sends it, and
returns the **raw** `requests.Response`. Endpoints never touch auth — they just build a
`Request` and hand it to `do()`.

### Base classes (`jamfpy/endpoints/models.py`)

```python
class Endpoint:                 # stores self._api; class attrs _uri, _name (default None)
class ClassicEndpoint(Endpoint) # full CRUD: get_all, get_by_id, update_by_id, create, delete_by_id, name
class ProEndpoint(Endpoint)     # EMPTY marker — implement every method by hand
```

Classic vs Pro idioms at a glance:

| Aspect | Classic (`ClassicEndpoint`) | Pro (`ProEndpoint`) |
|---|---|---|
| URL base | `self._api.url()` (no arg) | `self._api.url("1")` / `url("2")` |
| ID path | `self._uri + f"/id/{target_id}"` | `self._uri + f"/{target_id}"` (**no `/id/`**) |
| Create path | `self._uri + "/id/0"` | endpoint-specific (e.g. `/deployments`) |
| Write body | XML string via `data=` | dict via `json=` |
| Write headers | `header("create-update")["xml"]` | `header("create-update")["json"]` |

---

## Querying the API schemas

`api_schemas/pro.json` is **~1.9 MB** and `classic.json` is **~330 KB** — never read either
whole; it wastes context. Query them. Use the project venv (`.venv/bin/python`) from the repo
root. Human-readable docs, if the schema isn't enough:
<https://developer.jamf.com/jamf-pro/reference> (also in `api_schemas/api-reference-url.txt`).

### Pro (`pro.json` — OpenAPI 3, 525 paths, versions v1–v4)

```bash
# 1. Find the path(s) for your resource. The /v1, /v2... prefix IS the string url() needs.
.venv/bin/python -c "import json; print([p for p in json.load(open('api_schemas/pro.json'))['paths'] if 'script' in p])"
# -> ['/v1/scripts', '/v1/scripts/{id}', '/v1/scripts/{id}/download', ...]

# 2. Read one path's methods / params / request body reference.
.venv/bin/python -c "import json; print(json.dumps(json.load(open('api_schemas/pro.json'))['paths']['/v1/scripts'], indent=2))"

# 3. A POST/PUT body is usually a $ref into components.schemas. Resolve it for the field names.
.venv/bin/python -c "import json; d=json.load(open('api_schemas/pro.json')); s=d['components']['schemas']['Script']; print('props:', list(s['properties'])); print('required:', s.get('required'))"
# -> props: ['id', 'name', 'info', 'notes', 'priority', ...]
# -> required: ['name']
```

`/v1/scripts` → pass `"1"` to `url()`. `/v2/mdm/commands` → pass `"2"`. Simple.

### Classic (`classic.json` — Swagger 2.0, basePath `/JSSResource/`)

**`classic.json` has trailing commas and is NOT valid JSON — `json.load` raises.** Two ways
to query it:

```bash
# Option 1 — grep for the paths of a resource (fast, no parsing).
grep -o '"/[^"]*buildings[^"]*"' api_schemas/classic.json | sort -u
# -> "/buildings"  "/buildings/id/{id}"  "/buildings/name/{name}"

# Option 2 — strip the trailing commas, then parse to inspect methods per path.
.venv/bin/python -c "import re,json; t=re.sub(r',(\s*[}\]])', r'\1', open('api_schemas/classic.json').read()); d=json.loads(t); print('/buildings:', list(d['paths']['/buildings'])); print('/buildings/id/{id}:', list(d['paths']['/buildings/id/{id}']))"
# -> /buildings: ['get']
# -> /buildings/id/{id}: ['delete', 'get', 'post', 'put']
```

The `/id/{id}` and `/name/{name}` path shapes confirm a resource fits **Variant A**. If a
resource's sub-paths look like `/accounts/userid/{id}` instead, it's **Variant B**.

---

## Variant A — Classic simple (inherits CRUD for free)

The canonical, most-common case. Subclass `ClassicEndpoint`, set `_uri` and `_name`, and you
inherit `get_all`, `get_by_id`, `update_by_id`, `create`, `delete_by_id`, `name` — no methods
of your own.

**1. Add the class** in `jamfpy/endpoints/clc_endpoints.py`:

```python
class Buildings(ClassicEndpoint):
    """Endpoint for managing building locations in Jamf Pro."""
    _uri = "/buildings"
    _name = "buildings"
```

Conventions:
- `_uri` — leading slash, **no** trailing slash (`/buildings`, not `buildings/`).
- `_name` — snake_case; keep it aligned with Jamf's JSON top-level key where one exists.
- One-line docstring: *"Endpoint for managing X in Jamf Pro."*

**2. Import it** in `jamfpy/client/client.py` (add to the existing
`from ..endpoints.clc_endpoints import (...)` block).

**3. Attach it** in `ClassicAPI.__init__`:

```python
self.buildings = Buildings(self)
```

(The instance attribute name doesn't have to match the class name — e.g. the codebase has
`self.computer_extension_attributes = ExtensionAttributes(self)`.)

That's it. Usage:

```python
tenant.classic.buildings.get_all()
tenant.classic.buildings.get_by_id(123)
tenant.classic.buildings.create("<building>...</building>")   # XML string body
tenant.classic.buildings.update_by_id(123, "<building>...</building>")
tenant.classic.buildings.delete_by_id(123)
```

For reference, here is exactly what you inherit (from `ClassicEndpoint`, `models.py`):

```python
def get_all(self, suffix=None, xml_response=False) -> Response:   # GET  url()+_uri
def get_by_id(self, target_id, xml_response=False) -> Response:   # GET  url()+_uri+/id/{id}
def update_by_id(self, target_id, updated_configuration) -> Response:  # PUT  ...+/id/{id}, data=<xml>
def create(self, config_profile) -> Response:                    # POST url()+_uri+/id/0, data=<xml>
def delete_by_id(self, target_id) -> Response:                   # DELETE ...+/id/{id}, no headers
```

Note: Classic **create posts to `/id/0`**, and **delete sends no headers**. `get_by_id`/
`get_all` accept `xml_response=True` to switch `read` headers from json to xml.

---

## Variant B — Classic composite (sub-resources, accounts pattern)

Use this when a single Classic resource exposes **child sub-endpoints whose IDs don't follow
the `/id/{id}` convention** — e.g. `/accounts` splits into users
(`/accounts/userid/{id}`, `/accounts/username/{name}`) and groups
(`/accounts/groupid/{id}`, `/accounts/groupname/{name}`), and one GET on `/accounts` returns
both. Reference: `jamfpy/endpoints/clc_endpoints_accounts.py`. Three pieces.

**1. A child base that overrides CRUD to use custom URIs.** It adds `_by_id_uri` /
`_by_name_uri` and rebuilds each method's suffix from `_by_id_uri` instead of `/id/{id}`:

```python
class AccountChild(ClassicEndpoint):
    """Shared CRUD for account sub-resources that use non-standard id/name URIs."""
    _by_id_uri: str = None
    _by_name_uri: str = None

    def get_by_id(self, target_id: int) -> Response:
        """Get a single record by ID."""
        suffix = self._by_id_uri + f"/{target_id}"
        return self._api.do(Request(
            method="GET",
            url=self._api.url() + suffix,
            headers=self._api.header("read")["json"],
        ))

    def create(self, config_profile: str) -> Response:
        """Create a new record."""
        suffix = f"{self._by_id_uri}/0"
        return self._api.do(Request(
            method="POST",
            url=self._api.url() + suffix,
            headers=self._api.header("create-update")["xml"],
            data=config_profile,
        ))
    # update_by_id (PUT) and delete_by_id (DELETE) follow the same shape off _by_id_uri.
```

It also provides a helper to repackage a filtered JSON payload into a fresh `Response`
(so a transforming `get_all` still returns a real `requests.Response`):

```python
def pass_response(self, original_response: Response, new_data) -> Response:
    """Repackage new_data as a Response, preserving status/headers/encoding/url of the original."""
    new_response = Response()
    new_response.status_code = original_response.status_code
    new_response.headers = original_response.headers.copy()
    new_response.encoding = original_response.encoding
    new_response.url = original_response.url
    new_response.request = original_response.request
    body = json.dumps(new_data)
    encoding = new_response.encoding or "utf-8"
    new_response._content = body.encode(encoding)  # pylint: disable=protected-access
    new_response.headers["Content-Length"] = str(len(new_response._content))  # pylint: disable=protected-access
    return new_response
```

**2. The concrete children**, composing their URIs off a shared `_uri`, each overriding
`get_all` to slice the shared payload down to its part:

```python
class AccountUsers(AccountChild):
    """Endpoint for managing account users in Jamf Pro."""
    _name = "users"
    _uri = "/accounts"
    _by_id_uri = _uri + "/userid"       # "/accounts/userid"
    _by_name_uri = _uri + "/username"   # "/accounts/username"

    def get_all(self, suffix=None) -> Response:
        """Get all users, sliced out of the shared /accounts payload."""
        original = super().get_all(suffix=None)      # hits /accounts
        original.raise_for_status()
        users = {self._name: original.json().get("accounts", {}).get("users", [])}
        return self.pass_response(original, users)

class AccountGroups(AccountChild):
    """Endpoint for managing account groups in Jamf Pro."""
    _name = "groups"
    _uri = "/accounts"
    _by_id_uri = _uri + "/groupid"      # "/accounts/groupid"
    _by_name_uri = _uri + "/groupname"  # "/accounts/groupname"
    # get_all mirrors AccountUsers, slicing accounts.groups
```

**3. The composite parent — subclasses bare `Endpoint`, NOT `ClassicEndpoint`** — and wires
the children in its `__init__`:

```python
class Accounts(Endpoint):
    """Composite endpoint for Jamf Pro accounts, exposing .users and .groups."""
    _uri = "/accounts"
    _name = "accounts"

    def __init__(self, api_client):
        """Wire the user and group sub-endpoints onto the shared API client."""
        super().__init__(api_client)
        self._api = api_client
        self.users = AccountUsers(self._api)
        self.groups = AccountGroups(self._api)

    def get_all(self):
        """Get the raw, unfiltered /accounts payload (both users and groups)."""
        return ClassicEndpoint(self._api).get_all(self._uri)
```

Wire it like any Classic endpoint: import `Accounts` in `client.py`, then
`self.accounts = Accounts(self)` in `ClassicAPI.__init__`. Usage:

```python
tenant.classic.accounts.get_all()            # raw combined payload
tenant.classic.accounts.users.get_by_id(5)   # -> /accounts/userid/5
tenant.classic.accounts.groups.get_all()     # payload sliced to just groups
```

---

## Variant C — Pro hand-rolled CRUD

`ProEndpoint` is deliberately empty — the two APIs differ too much to share CRUD, so you
implement each method by hand, building the `requests.Request` explicitly. Reference:
`jamfpy/endpoints/pro_app_installers.py` (minimal) and `pro_scripts.py`.

Create/extend a `jamfpy/endpoints/pro_<thing>.py` module:

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
            url=self._api.url("1") + f"{self._uri}/{target_id}",   # Pro ID path: no /id/
            headers=self._api.header("read")["json"],
        ))

    def create(self, payload: dict) -> Response:
        """Create a thing."""
        return self._api.do(Request(
            "POST",
            url=self._api.url("1") + self._uri,
            headers=self._api.header("create-update")["json"],
            json=payload,                                          # dict body via json=
        ))

    def delete_by_id(self, target_id: int) -> Response:
        """Delete a thing by its ID."""
        return self._api.do(Request(
            "DELETE",
            url=self._api.url("1") + f"{self._uri}/{target_id}",
            headers=self._api.header("delete")["json"],
        ))
```

Key points vs Classic:
- **Version is explicit**: `self._api.url("1")` — swap `"1"`/`"2"` to match the `/v{n}` prefix
  from the schema for *your* path.
- **ID path is `{_uri}/{id}`**, no `/id/` segment.
- **Bodies are dicts passed with `json=`**, headers use `["json"]`.
- Real Pro paths can nest below `_uri` — e.g. app-installers builds
  `url("1") + self._uri + f"/deployments/{id}"`. Verify the exact path against the schema.

Wire it: import in `client.py` (alias if the name clashes with a Classic class —
`from ..endpoints.pro_scripts import Scripts as ProScripts`), then
`self.things = Things(self)` in `ProAPI.__init__`.

---

## Variant D — Pro action + convenience wrappers

For endpoints that are **verbs, not CRUD** — sending commands to devices, etc. Reference:
`jamfpy/endpoints/pro_mdm_commands.py`. Pattern: **one core worker method** that builds the
JSON payload and POSTs, plus **many thin named wrappers** that fix the command string and map
snake_case Python args to Jamf's camelCase payload keys.

```python
from requests import Request, Response
from .models import ProEndpoint


class MDMCommands(ProEndpoint):
    """Endpoint for issuing MDM commands via the modern Jamf Pro API."""
    _uri = "/mdm/commands"
    _name = "mdm_commands"

    def send_command(self, command_type: str, management_ids: list[str], **kwargs) -> Response:
        """Build the command payload and POST it. All wrappers delegate here."""
        payload = {
            "clientData": [{"managementId": mid} for mid in management_ids],
            "commandData": {"commandType": command_type, **kwargs},
        }
        return self._api.do(Request(
            method="POST",
            url=self._api.url("2") + self._uri,          # mdm/commands is v2
            headers=self._api.header("read")["json"],
            json=payload,
        ))

    def lock_device(self, management_ids: list[str], message: str = "Device locked remotely",
                    pin: str = "1234", phone_number: str = None) -> Response:
        """Send a DEVICE_LOCK command."""
        return self.send_command(
            "DEVICE_LOCK",
            management_ids if isinstance(management_ids, list) else [management_ids],
            message=message, pin=pin, phoneNumber=phone_number,
        )

    def erase_device(self, management_ids: list[str], pin: str = "1234",
                     return_to_service: dict = None) -> Response:
        """Send an ERASE_DEVICE command."""
        if return_to_service is None:              # avoid a mutable default
            return_to_service = {"enabled": True}
        return self.send_command(
            "ERASE_DEVICE",
            management_ids if isinstance(management_ids, list) else [management_ids],
            pin=pin, returnToService=return_to_service,
        )
```

Idioms to reproduce:
- Each wrapper is a one-liner delegating to `send_command` with a fixed command string.
- Coerce a single id into a list: `ids if isinstance(ids, list) else [ids]`.
- Snake_case args → camelCase payload keys (`phone_number` → `phoneNumber`).
- Default dict/list args are set inside the method when `None` — never as mutable defaults.

Wire it: `self.mdm = MDMCommands(self)` in `ProAPI.__init__`.

---

## Legacy pattern — recognise, don't copy

`pro_scripts.Scripts.get_all` hand-rolls pagination and has an **inconsistent return
signature** (returns `(resp, list)` on the early-exit path, `resp` on the loop path, and
accumulates an `out_list` it never returns). It predates the current conventions. Its tests
deliberately *characterize* this quirk. Recognise it so you don't reproduce its shape — new
paginating endpoints should return one consistent type. `AGENTS.md` lists this under
"Known rough edges."

---

## Writing the test

Tests are **fully offline**. Endpoints only call `url()`, `header()`, and `do()` on their
API object, so the `FakeAPI` double in `tests/conftest.py` implements exactly those and
**records every `requests.Request` handed to `do()`**. One `tests/<module>_test.py` per
source module (note the non-default `*_test.py` naming, set in `pyproject.toml`).

What `FakeAPI` gives you:
- `api.last_request` — the most recently built `requests.Request`.
- `api.requests` — the full ordered list (for multi-call flows like pagination).
- `FakeAPI(responses=[make_response(...)])` — seed a response queue when the method actually
  reads the response (`.json()`, `.raise_for_status()`); `do()` pops them FIFO.
- `FQDN` and `make_response` are importable from `conftest`.

Assert on the recorded request: `.method`, `.url`, `.headers` (vs
`DEFAULT_HTTP_CONFIG_HEADERS["crud"][op][fmt]`), and the body — `.data` for Classic XML
strings, `.json` for Pro dicts. Delete with no headers asserts `req.headers == {}`.

### Classic test

```python
"""Unit tests for the Buildings endpoint."""
# pylint: disable=missing-function-docstring
from conftest import FakeAPI, FQDN
from jamfpy.endpoints.clc_endpoints import Buildings
from jamfpy.client.constants import DEFAULT_HTTP_CONFIG_HEADERS as H

BASE = f"{FQDN}/JSSResource"


def test_get_by_id_builds_id_url():
    api = FakeAPI()
    Buildings(api).get_by_id(7)
    req = api.last_request
    assert req.method == "GET"
    assert req.url == f"{BASE}/buildings/id/7"
    assert req.headers == H["crud"]["read"]["json"]


def test_create_posts_xml_to_id_zero():
    api = FakeAPI()
    Buildings(api).create("<building/>")
    req = api.last_request
    assert req.method == "POST"
    assert req.url == f"{BASE}/buildings/id/0"
    assert req.data == "<building/>"
```

### Pro test

```python
"""Unit tests for the Pro Things endpoint."""
# pylint: disable=missing-function-docstring
from conftest import FakeAPI, FQDN
from jamfpy.endpoints.pro_things import Things
from jamfpy.client.constants import DEFAULT_HTTP_CONFIG_HEADERS as H

BASE = f"{FQDN}/api/v1"      # Pro URLs carry the version


def test_get_by_id_builds_v1_url():
    api = FakeAPI()
    Things(api).get_by_id(5)
    req = api.last_request
    assert req.method == "GET"
    assert req.url == f"{BASE}/things/5"
    assert req.headers == H["crud"]["read"]["json"]


def test_create_sends_json_body():
    api = FakeAPI()
    Things(api).create({"name": "x"})
    req = api.last_request
    assert req.method == "POST"
    assert req.url == f"{BASE}/things"
    assert req.json == {"name": "x"}
```

Test-file conventions:
- Module docstring, then `# pylint: disable=missing-function-docstring`. Add
  `,redefined-outer-name` if you use fixtures as function args, and `,protected-access` (or
  inline) when touching `_uri`/`_name`.
- Function names are behavioural: `test_<what>_<expected>` (e.g. `test_get_by_id_builds_v1_url`).
- For a method that reads its response, seed it:
  `api = FakeAPI(responses=[make_response({...})])`, then assert on both the returned
  response and `api.last_request`.

Run the suite from the repo root: `.venv/bin/python -m pytest -q`.

---

## Definition of done

- [ ] Class added, with a docstring on every public class/method.
- [ ] Imported in `jamfpy/client/client.py` and attached in `ProAPI.__init__` /
      `ClassicAPI.__init__` (alias the import if the name clashes across APIs).
- [ ] Path, version, and body shape verified against the schema (the queries above — not a
      full read).
- [ ] A `tests/<module>_test.py` covers the Request(s) it builds (mock only, via `FakeAPI`).
- [ ] Smoke test: `.venv/bin/python -c "import jamfpy; print(jamfpy.Tenant)"`.
- [ ] Tests pass: `.venv/bin/python -m pytest -q`.
- [ ] Lint passes: `.venv/bin/pylint $(git ls-files '*.py') --fail-under=9.0`.
- [ ] No live-request "testing" (the suite mocks the network); no edits to version/CHANGELOG.
- [ ] If committing: Conventional Commit (`feat:` for a new endpoint).
