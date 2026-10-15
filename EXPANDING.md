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

### Scaffold first

`make scaffold` reads the path from the schema, picks the variant for you and writes everything a
new endpoint needs. Preview it with `DRY_RUN=1` (writes nothing):

```bash
make scaffold API=pro PATH=/v1/categories DRY_RUN=1
# shape: Pro CRUD -> Categories(ProEndpoint): get_all, get_by_id, create, update_by_id, delete_by_id
# would write:
#   new      jamfpy/endpoints/pro_categories.py
#   changed  jamfpy/client/client.py
#   new      tests/pro_categories_test.py
#   changed  tests/integration/pro_resources_live_test.py
#   changed  tests/contract_test.py
# next: fill in the live builders in tests/integration/pro_resources_live_test.py; review _name ('categories') and the docstrings
# next: names come from the path alone (class Categories, attribute categories); for a multi-word resource use NAME=<PascalCaseName> instead (undo this run first if it wrote)
# regenerate COVERAGE.md with make coverage-doc
```

For a Classic resource whose path runs its words together, pass `NAME=` (the jamfpy-dev skill should too), otherwise the
class and attribute are one unreadable word:

```bash
make scaffold API=classic PATH=/advancedmobiledevicesearches NAME=AdvancedMobileDeviceSearches
# class AdvancedMobileDeviceSearches, attribute advanced_mobile_device_searches; _uri and _name stay "/advancedmobiledevicesearches" / "advancedmobiledevicesearches"
```

Then drop `DRY_RUN=1` to write them. It produces Variant A (Classic simple), B (Classic composite),
C (Pro CRUD, `ProEndpoint` or exactly the mixins the verbs back, `ProGetAll` only when the collection GET is
paginated) or D (Pro action, a single
`send(payload)` with no convenience wrappers), wires the endpoint in `client.py`, writes the unit tests
from the templates in [Writing the test](#writing-the-test), appends a live spec whose builders fail
until written, and bumps `EXPECTED_ENDPOINT_COUNT`. The shape rules, the names it derives and every
refusal are in `AGENTS.md` → *How to add an endpoint* → *Scaffold first*. A path it can't classify
(a Classic resource missing one of DELETE GET POST PUT by id, a non-`id` parameter, a multipart or
non-JSON body, an endpoint that already exists, ...) is refused with a one-line reason and nothing is
written.

What to fill in afterwards:

- **The live builders.** The new `SPECS` entry in `tests/integration/pro_resources_live_test.py` (or
  `clc_resources_live_test.py`) has `"min"` and `"max"` set to
  `lambda n: pytest.fail("fill in the builders")`, so `make test-integration` fails on it until you
  write them: `min` with the required fields from `make schema-path`, `max` with every writable one,
  as the existing specs do. For Classic, check `root` too: it starts as the `_name`, but it is the XML
  root element of one record (`printer`, not `printers`). A Pro action, or a partial CRUD without
  `create`/`get_by_id`/`update_by_id`/`delete_by_id`, gets no spec: give it an N/A row in COVERAGE.md.
- **`_name`.** The scaffolder uses the path's snake_case slug (the snake_case of `NAME=` for Pro) unless the
  Classic schema names the JSON top-level key (it currently never does). Keep it aligned with Jamf's key, as
  Variant A says.
- **The names.** A Classic path that runs its words together gives a one-word class and attribute
  (`Advancedmobiledevicesearches`); the `next:` line says so. Undo the run and repeat it with
  `NAME=<PascalCaseName>`: the attribute is its snake_case, a Pro module and `_name` or a composite's module
  follow it, `_uri` stays the path. The same `NAME=` scaffolds a second version beside the first (`/v2/groups` after
  `/v1/groups` is refused for its attribute and says to pass `NAME=`).
- **A missing `get_all`.** A Pro collection GET that is not paginated (no `page`/`page-size` parameters and no
  `totalCount`/`results` response, e.g. a bare array as `/v1/static-user-groups`) gets no `ProGetAll`, because
  `get_all` would page a URL that does not page. The class docstring and a `next:` line say so; write `get_all`
  by hand if you want one.
- **A composite's `get_all`.** The children inherit `ClassicEndpoint.get_all`, which returns the whole
  collection, not the sliced payload the hand-written `AccountUsers` returns. Override it as
  `clc_endpoints_accounts.py` does if the resource needs slicing.
- **Docstrings.** They are plain ("Endpoint for managing printers in Jamf Pro."). Say more where the
  resource deserves it, e.g. why a Pro endpoint lacks a verb, or what a Pro action's payload holds.
- **An action's wrappers.** Variant D's convenience wrappers are yours to add on top of `send`.

The four variants below stay the reference for what the scaffolder writes and for writing an
endpoint by hand when it refuses one.

### The four variants

The SDK has two APIs (Classic = XML writes under `/JSSResource`; Pro = JSON under
`/api/v{n}`) and four concrete endpoint shapes across them. Find your row, then jump to that
section.

| Your target | Standard CRUD? | Variant | Base class | Reference file |
|---|---|---|---|---|
| Classic resource, normal `/id/{id}` CRUD | yes | **A. Classic simple** | `ClassicEndpoint` | `clc_endpoints.py` |
| Classic resource with sub-resources / non-`/id/` paths | no | **B. Classic composite** | `Endpoint` + `ClassicEndpoint` children | `clc_endpoints_accounts.py` |
| Pro resource, CRUD (+ paginated list) | all five verbs, or some | **C. Pro CRUD** | `ProEndpoint`, or just the capability mixins the schema supports | `pro_scripts.py`, `pro_app_installers.py`, `pro_dock_items.py` |
| Pro action / command endpoint (verbs, not CRUD) | n/a | **D. Pro action + wrappers** | `Endpoint` | `pro_mdm_commands.py` |

**By far the most common job is Variant A** — a Classic resource that gets full CRUD for free.
Start there unless your target clearly doesn't fit. **Variant C is its Pro twin**: `ProEndpoint`
gives Pro resources the same inherit-everything CRUD (with a paginating `get_all`), and a resource
whose schema has only some of the verbs composes just those capability mixins.

Whichever variant you pick, wiring is the same three steps (detailed per-variant below; `make scaffold` does all three):

1. Define the class in the right `jamfpy/endpoints/` module.
2. Import it in `jamfpy/client/client.py`.
3. Attach it as `self.<attr> = MyEndpoint(self)` in `ClassicAPI.__init__` or `ProAPI.__init__`.

You never touch `jamfpy/__init__.py` — endpoints are reached through a client
(`tenant.classic.buildings`), not exported at the top level.

---

## The three helpers every endpoint uses

Endpoints never hardcode URLs, headers, or auth. They call three methods on `self._api`
(the API client instance passed into the constructor). Source: `jamfpy/client/api.py`.

### `self._api.url(target: str | None = None) -> str`

- **Classic** ignores `target` and returns the base, e.g. `https://<fqdn>/JSSResource`.
- **Pro** *requires* `target` = the API version string and interpolates it:
  `self._api.url("2")` → `https://<fqdn>/api/v2`. The version differs per endpoint
  (scripts = v1, mdm/commands = v2, app-installers = v1). **The version string is literally
  the `/v{n}` prefix on the path in `pro.json`** (see [Querying the schemas](#querying-the-api-schemas)).
  Calling a Pro `url()` with no target yields the literal string `.../api/vNone` — always pass one.

### `self._api.header(key: str) -> dict[str, Any]`

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

### `self._api.do(request: Request, timeout: Timeout | None = None) -> Response`

The single choke point every request goes through. It adds `Authorization: Bearer <token>`
from `auth.token()` to the request's own headers (never the shared session, whose headers are
just requests' defaults plus `User-Agent: jamfpy/<version>`), preps the `requests.Request`, sends it
with the configured timeout (`Tenant(timeout=...)`, default 30 s; `timeout=` overrides it for
that one API call, not for a token fetch it triggers), and returns the **raw** `requests.Response`. Endpoints never touch auth or
timeouts — they just build a `Request` and hand it to `do()`. Session defaults sit under the
endpoint's headers, so an endpoint's `accept` replaces the default `Accept: */*`.

`do()` also retries a failed attempt (a listed status, a timeout or a connection error, per the
`RetryConfig`; see **Retries** in AGENTS.md) and fires the request hooks on every attempt (see
**Request hooks**). Neither changes what an endpoint does: it still builds one `Request` and returns
what `do()` returns. Two consequences for the `Request` you build: `do()` re-prepares it for each
attempt, so pass a replayable body (`data=` a string, or `json=`), never a file object or generator;
and a POST is only retried after a connect timeout unless the caller opted in with `retry_post`, so an
endpoint that POSTs needs no special handling.

### Base classes (`jamfpy/endpoints/models.py`)

```python
class Endpoint:                 # stores self._api; class attrs _uri, _name; _repackage_response helper
class ClassicEndpoint(Endpoint) # full CRUD: get_all, get_by_id, update_by_id, create, delete_by_id, name
class ProBase(Endpoint)         # base of the Pro capability mixins: class attrs _version="1", _page_size=100; name()
class ProGetAll(ProBase)        # get_all: paginates, fetching pages in parallel (see Pagination)
class ProGetById(ProBase)       # get_by_id
class ProCreate(ProBase)        # create
class ProUpdateById(ProBase)    # update_by_id
class ProDeleteById(ProBase)    # delete_by_id
class ProEndpoint(ProGetAll, ProGetById, ProCreate, ProUpdateById, ProDeleteById)   # full CRUD (Pro idioms)
```

Classic vs Pro idioms at a glance (`ClassicEndpoint` and `ProEndpoint` implement the same method set —
these are the differences baked into the Pro mixins):

| Aspect | Classic (`ClassicEndpoint`) | Pro (`ProEndpoint`) |
|---|---|---|
| URL base | `self._api.url()` (no arg) | `self._api.url(self._version)` (e.g. `url("1")`) |
| ID path | `self._uri + f"/id/{target_id}"` | `self._uri + f"/{target_id}"` (**no `/id/`**) |
| Create path | `self._uri + "/id/0"` | `self._uri` (POST to the collection) |
| Write body | XML string via `data=` | dict via `json=` |
| Write headers | `header("create-update")["xml"]` | `header("create-update")["json"]` |
| `get_all` | one GET, one Response (Classic isn't paginated) | fetches page 0, then the rest in parallel (up to `parallelism`), and aggregates every page into one Response `{"totalCount", "results"}`; a failed page comes back raw |
| `update_by_id` | PUT | PUT (best-effort default — some resources need PATCH or are read-only) |

---

## Querying the API schemas

`api_schemas/pro.json` is **~2.1 MB** and `classic.json` is **~330 KB** — never read either
whole; it wastes context. Query them with the two make targets below. Both go through
`tools/schemas.py`, the one reader of those files: it merges the probed
`api_schemas/pro-supplement.json` into Pro and normalises Classic's verb keys. Human-readable
docs, if the schema isn't enough: <https://developer.jamf.com/jamf-pro/reference> (also in
`api_schemas/api-reference-url.txt`). How the files are refreshed is in `AGENTS.md` → *Schemas*.

### 1. Find the paths with `make schema-paths`

```bash
make schema-paths API=pro MATCH=scripts
# /v1/scripts                get post
# /v1/scripts/{id}           delete get put
# /v1/scripts/{id}/download  get
# /v1/scripts/{id}/history   get post
```

`MATCH` is a case-insensitive substring (leave it off to list every path); verbs are lower-case
and sorted. **The `/v1`, `/v2`... prefix on a Pro path IS the string `url()` needs**:
`/v1/scripts` → `"1"`, `/v2/mdm/commands` → `"2"`. A path Jamf's schema leaves out but the tenant
serves comes from the supplement and is marked, e.g.
`/v1/app-installers/deployments  get post  [options-probe]`.

`API=classic` works the same way (Swagger 2.0, basePath `/JSSResource/`). `/id/{id}` and
`/name/{name}` path shapes (`make schema-paths API=classic MATCH=buildings` lists `/buildings`,
`/buildings/id/{id}`, `/buildings/name/{name}`) confirm a resource fits **Variant A**. If a
resource's sub-paths look like `/accounts/userid/{id}` instead, it's **Variant B**.

### 2. Read one path with `make schema-path`

```bash
make schema-path API=pro PATH=/v1/scripts
```

It prints JSON: for each verb, the summary-level fields, `parameters` (path-level ones merged in)
and, when the verb takes a body, `requestBody` with `required`, `contentTypes` and the body's
`schema`, with every `$ref` resolved in place (`x-jamfpy-ref` keeps the reference, so `Script`
below is `components.schemas.Script`). Trimmed to the POST and three of its properties:

```json
{
  "api": "pro",
  "path": "/v1/scripts",
  "methods": {
    "post": {
      "summary": "Create a Script\n",
      "x-required-privileges": ["Create Scripts"],
      "parameters": [],
      "requestBody": {
        "required": true,
        "contentTypes": ["application/json"],
        "schema": {
          "x-jamfpy-ref": "#/components/schemas/Script",
          "required": ["name"],
          "type": "object",
          "properties": {
            "id": {"minLength": 1, "type": "string", "readOnly": true, "example": "1"},
            "name": {"type": "string", "example": "Install Developer Utils Script"},
            "priority": {"type": "string", "example": "AFTER", "enum": ["BEFORE", "AFTER", "AT_REBOOT"]}
          }
        }
      }
    }
  }
}
```

`required` lists the fields a min payload needs; `readOnly` ones never go in a body. Classic works
the same way (`make schema-path API=classic PATH=/mobiledevicecommands/command`; braces in a path such as
`/buildings/id/{id}` need no quoting, and that one declares no body, so none of its verbs has a `requestBody`).
`requestBody` always has the shape `{"required", "contentTypes", "schema"}`. Swagger 2's `in: body`
parameter gives its schema as it is; where Classic declares several `in: body` parameters on one
operation (16 on `POST /mobiledevicecommands/command`, one per XML element), none is dropped: `schema`
is a synthesised object schema whose `properties` map each parameter's name to its resolved schema,
whose `required` lists the parameters marked required, and whose `x-jamfpy-note` says `<N> in: body
parameters merged into one object schema`. An unknown path fails with the closest matches.

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
def get_all(self, suffix: str | None = None, xml_response: bool = False) -> Response:  # GET  url()+_uri
def get_by_id(self, target_id: int, xml_response: bool = False) -> Response:           # GET  url()+_uri+/id/{id}
def update_by_id(self, target_id: int, updated_configuration: str) -> Response:        # PUT  ...+/id/{id}, data=<xml>
def create(self, config_profile: str) -> Response:                                     # POST url()+_uri+/id/0, data=<xml>
def delete_by_id(self, target_id: int) -> Response:                                    # DELETE ...+/id/{id}, sets no headers of its own
```

Note: Classic **create posts to `/id/0`**, and **delete sets no headers of its own** (only the session defaults and `Authorization` go out). `get_by_id`/
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
    _by_id_uri: str
    _by_name_uri: str

    def get_by_id(self, target_id: int) -> Response:  # type: ignore[override]
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

The accounts overrides of `get_by_id` and `get_all` drop the base's `xml_response` argument, which
mypy rejects as an incompatible override, so they carry `# type: ignore[override]` to keep their
public signatures. A new composite should keep the base signature instead and needs no ignore.

To repackage a filtered JSON payload into a fresh `Response` (so a transforming `get_all` still
returns a real `requests.Response`), use the inherited `Endpoint._repackage_response(original, new_data)`:
it keeps the original's status, headers, encoding, url and request and resets `Content-Length`.
Don't write another copy of it.

**2. The concrete children**, composing their URIs off a shared `_uri`, each overriding
`get_all` to slice the shared payload down to its part:

```python
class AccountUsers(AccountChild):
    """Endpoint for managing account users in Jamf Pro."""
    _name = "users"
    _uri = "/accounts"
    _by_id_uri = _uri + "/userid"       # "/accounts/userid"
    _by_name_uri = _uri + "/username"   # "/accounts/username"

    def get_all(self, suffix: str | None = None) -> Response:  # type: ignore[override]
        """Get all users, sliced out of the shared /accounts payload."""
        original = super().get_all(suffix=None)      # hits /accounts
        if not original.ok:                          # never raise: a failed read goes back raw
            return original
        users = {self._name: original.json().get("accounts", {}).get("users", [])}
        return self._repackage_response(original, users)

class AccountGroups(AccountChild):
    """Endpoint for managing account groups in Jamf Pro."""
    _name = "groups"
    _uri = "/accounts"
    _by_id_uri = _uri + "/groupid"      # "/accounts/groupid"
    _by_name_uri = _uri + "/groupname"  # "/accounts/groupname"
    # get_all mirrors AccountUsers, slicing accounts.groups
```

**3. The composite parent — subclasses bare `Endpoint`, NOT `ClassicEndpoint`** — and wires
the children in its `__init__`. The `API` hint comes from the same `TYPE_CHECKING` import that
`models.py` uses, so the endpoint never imports the client layer at runtime:

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..client.api import API


class Accounts(Endpoint):
    """Composite endpoint for Jamf Pro accounts, exposing .users and .groups."""
    _uri = "/accounts"
    _name = "accounts"

    def __init__(self, api_client: "API") -> None:
        """Wire the user and group sub-endpoints onto the shared API client."""
        super().__init__(api_client)
        self._api = api_client
        self.users = AccountUsers(self._api)
        self.groups = AccountGroups(self._api)

    def get_all(self) -> Response:
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

## Variant C — Pro CRUD (inherit `ProEndpoint`, or compose the mixins)

Pro CRUD comes from five **capability mixins** in `models.py`, each contributing exactly one method
(`ProGetAll`, `ProGetById`, `ProCreate`, `ProUpdateById`, `ProDeleteById`, all on `ProBase`).
`ProEndpoint` composes all five and mirrors `ClassicEndpoint`. Check the verbs first:

```bash
make schema-paths API=pro MATCH=dock-items
# /v1/dock-items       post                 <- collection: get -> get_all, post -> create
# /v1/dock-items/{id}  delete get put       <- by id: get -> get_by_id, put -> update_by_id, delete -> delete_by_id
```

All five verbs → **C1**, inherit `ProEndpoint`. Fewer → **C2**, compose exactly the mixins for the
verbs listed, so the endpoint never offers a method the server can only reject.

### C1 — full CRUD: inherit `ProEndpoint`

A simple Pro resource is just a subclass that sets `_uri`, `_name`, and `_version` — no methods of
your own. Reference: `jamfpy/endpoints/pro_scripts.py` and `pro_app_installers.py`.

**1. Add the class** in a `jamfpy/endpoints/pro_<thing>.py` module:

```python
from .models import ProEndpoint


class Things(ProEndpoint):
    """Endpoint for managing things in the modern Jamf Pro API."""
    _uri = "/things"
    _name = "things"
    _version = "1"        # the /v{n} prefix on the path in pro.json
```

You inherit `get_all`, `get_by_id`, `create`, `update_by_id`, `delete_by_id`, `name`. What the
inherited methods do (differs from Classic — see the idiom table above):
- **Version is explicit** via `_version`: methods build `self._api.url(self._version)`. Set it to
  the `/v{n}` prefix from the schema for *your* path (scripts = `"1"`, mdm/commands = `"2"`).
- **ID path is `{_uri}/{id}`**, no `/id/` segment. **Create POSTs to `{_uri}`** (the collection).
- **Bodies are dicts passed with `json=`**; write headers use `["json"]`.
- **`get_all(page_size=None, sort=None)` paginates**: it fetches page 0 (default page size 100),
  then, when the body carries a `totalCount`, the remaining pages in parallel on up to
  `parallelism` worker threads, and returns **one** aggregated `Response` whose body is
  `{"totalCount": N, "results": [...all pages...]}` (built via `Endpoint._repackage_response`).
  A page that isn't `ok` is returned raw instead (the lowest page number when several fail); it
  never raises on a status. Callers check `.ok`, then read `.json()["results"]`. See
  [Pagination](#pagination--inherited-dont-hand-roll).
- **`update_by_id` uses PUT** as a best-effort default — override if your resource needs PATCH.

For reference, exactly what you inherit (one method per mixin, `models.py`):

```python
def get_all(self, page_size: int | None = None, sort: str | None = None) -> Response:  # ProGetAll: paginates -> one aggregated Response
def get_by_id(self, target_id: int) -> Response:                                       # ProGetById: GET  url(_version)+_uri+/{id}
def create(self, payload: dict[str, Any]) -> Response:                                 # ProCreate: POST url(_version)+_uri, json=<dict>
def update_by_id(self, target_id: int, payload: dict[str, Any]) -> Response:           # ProUpdateById: PUT  ...+/{id}, json=<dict>
def delete_by_id(self, target_id: int) -> Response:                                    # ProDeleteById: DELETE ...+/{id}, delete json header
```

### C2 — partial CRUD: compose the mixins the schema supports

When the schema has only some of the verbs, subclass exactly those mixins instead of
`ProEndpoint`. Reference: `jamfpy/endpoints/pro_dock_items.py` — `/v1/dock-items` takes POST only
(no collection GET), so `DockItems` has no `get_all`:

```python
from .models import ProCreate, ProDeleteById, ProGetById, ProUpdateById


class DockItems(ProGetById, ProCreate, ProUpdateById, ProDeleteById):
    """Endpoint for managing dock items in the modern Jamf Pro API (v1+).

    Composes the four verbs the schema has: ``/v1/dock-items`` takes only POST, so there is no ``get_all``.
    """
    _uri = "/dock-items"
    _name = "dock_items"
    _version = "1"
```

Each mixin's method is identical to the one `ProEndpoint` has, and every mixin brings `ProBase`
(`_version`, `_page_size`, `name()`), so any combination works. List the mixins in the order
`ProEndpoint` does (`ProGetAll`, `ProGetById`, `ProCreate`, `ProUpdateById`, `ProDeleteById`) and say
in the class docstring which verbs are missing and why. Test that the missing method is absent
(`assert not hasattr(DockItems, "get_all")`) next to the usual request tests.

### Either way

**When to hand-roll:** only when a resource deviates from this shape — a nested path, a query
param the base doesn't build, or a non-JSON body. In that case override just the method that
differs and build the `requests.Request` explicitly, e.g.:

```python
    def get_by_id(self, target_id: int) -> Response:
        """Get a thing by its ID (custom nested path)."""
        return self._api.do(Request(
            "GET",
            url=self._api.url(self._version) + self._uri + f"/nested/{target_id}",
            headers=self._api.header("read")["json"],
        ))
```

Wire it: import in `client.py` (alias if the name clashes with a Classic class —
`from ..endpoints.pro_scripts import Scripts as ProScripts`), then
`self.things = Things(self)` in `ProAPI.__init__`.

---

## Variant D — Pro action + convenience wrappers

For endpoints that are **verbs, not CRUD** — sending commands to devices, etc. Reference:
`jamfpy/endpoints/pro_mdm_commands.py`. Pattern: **one core worker method** that builds the
JSON payload and POSTs, plus **many thin named wrappers** that fix the command string and map
snake_case Python args to Jamf's camelCase payload keys.

**Subclass the bare `Endpoint`, not `ProEndpoint` or any Pro mixin** — an action endpoint has no
`/{id}` CRUD to inherit, and pulling in `get_all`/`get_by_id`/… would just expose meaningless
methods. (Same reason the composite Classic `Accounts` parent subclasses bare `Endpoint`.)

```python
from typing import Any

from requests import Request, Response
from .models import Endpoint


class MDMCommands(Endpoint):
    """Endpoint for issuing MDM commands via the modern Jamf Pro API."""
    _uri = "/mdm/commands"
    _name = "mdm_commands"

    def send_command(self, command_type: str, management_ids: list[str], **kwargs: object) -> Response:
        """Build the command payload and POST it. All wrappers delegate here."""
        payload: dict[str, Any] = {
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
                    pin: str = "1234", phone_number: str | None = None) -> Response:
        """Send a DEVICE_LOCK command."""
        return self.send_command(
            "DEVICE_LOCK",
            management_ids if isinstance(management_ids, list) else [management_ids],
            message=message, pin=pin, phoneNumber=phone_number,
        )

    def erase_device(self, management_ids: list[str], pin: str = "1234",
                     return_to_service: dict[str, bool | str] | None = None) -> Response:
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

## Pagination — inherited, don't hand-roll

Pro list endpoints paginate with `page`/`page-size` and return `{"totalCount": N, "results": [...]}`.
`ProGetAll.get_all` (in every `ProEndpoint`) handles this centrally — do **not** hand-roll a paging
loop in your endpoint. It fetches page 0; when that carries a `totalCount` it fetches the remaining
pages in parallel, on up to `Tenant(parallelism=5)` worker threads (one at a time at
`parallelism=1`), and reads them in page order. Without a `totalCount` it walks one page at a time
until a short or empty page. A page that isn't `ok` is returned raw (the lowest page number wins);
a page repeating page 0's results means the server ignores `page`, so it stops there with a WARNING.
Otherwise it returns **one** aggregated `Response`. Just set `_uri`/`_name`/`_version` and call
`endpoint.get_all()` — pass `page_size=` / `sort=` to tune it. The full algorithm is in AGENTS.md →
**Concurrency**. If a resource paginates differently, override `get_all` and still return a single
`Response` (aggregate via `Endpoint._repackage_response`), returning a failed page raw rather than
raising.

---

## Writing the test

Unit tests are **fully offline** (the sanctioned live suite is `tests/integration/` —
marker-gated, deselected by default; see AGENTS.md Quality gates). They drive the real SDK
stack and mock only the network edge with [`responses`](https://github.com/getsentry/responses):
your endpoint runs on a real `Tenant`, `API.do()` adds the Bearer token from the real `Auth`,
and `responses` answers the request and records it. An unregistered URL raises
`ConnectionError`, so a wrong URL fails the test and nothing leaves the process. One
`tests/<module>_test.py` per source module (note the non-default `*_test.py` naming, set in
`pyproject.toml`).

What `tests/conftest.py` gives you:
- `mocked_responses` — an active `responses.RequestsMock`. Register what the endpoint should
  call (`mocked_responses.get(url, json={...})`, `mocked_responses.post(url, status=201, body="<xml/>")`);
  `mocked_responses.calls` records every request in order. Every registration must be used:
  one the code never requests fails the test at teardown.
- `classic_api` / `pro_api` — the two APIs of a real OAuth `Tenant` (the `tenant` fixture),
  already authenticated against the mocked token endpoint (`Tenant()` itself is lazy and sends
  nothing). The call log is reset after that, so `calls` holds only your test's requests. Reach your endpoint through its wired attribute
  (`classic_api.buildings`), which also exercises the wiring in `client.py`. At teardown the
  fixture fails the test if any call other than a token request went out without the
  `Authorization: Bearer` header, so every endpoint test checks it without asserting it.
- `response_registry` — the registry class behind `mocked_responses`. A module whose endpoint
  may request the same URL repeatedly (a paginated `get_all`) overrides it to return
  `responses.registries.OrderedRegistry`, as `tests/models_test.py` does. `OrderedRegistry` is one
  FIFO for the whole mock, so it only suits requests sent in a known order: a `get_all` with three
  or more pages fetches pages 1..N in parallel, in any order. Such a test keeps the default
  registry (`TestParallelGetAll` in `tests/models_test.py` puts it back) and registers each page
  under its own `page=` URL, or builds its API with `parallelism=1`.
- `with_bearer(header_set)` — every header `API.do()` sends for a config header set: requests'
  session defaults with the jamfpy `User-Agent`, the set over them, and the
  `Authorization: Bearer <fake token>` header. Names are lower-cased to match `sent_headers`.
- `sent_headers(request)` — a recorded request's headers minus `Content-Length`, which
  requests derives from the body, with names lower-cased (header names are case-insensitive,
  and an endpoint's `accept` replaces the session's `Accept` under its own spelling).
- `FQDN`, `FAKE_TOKEN`, `TOKEN_URL` and `register_oauth_token(rsps)` for tests that build their
  own `Tenant`. `Tenant()` sends nothing, so register the token endpoint only when the test
  authenticates or sends a request (an unused registration fails the test).

Assert on `mocked_responses.calls[-1].request` (a `requests.PreparedRequest`): `.method`, the
full `.url` (`.../JSSResource/...` for Classic, `.../api/v{n}/...` for Pro),
`sent_headers(req) == with_bearer(DEFAULT_HTTP_CONFIG_HEADERS["crud"][op][fmt])`, and the body:
`req.body` is the XML string for Classic, `json.loads(req.body)` the dict for Pro. A Classic
delete passes no header set, so assert `sent_headers(req) == with_bearer({})`. A URL with a
query string (a Pro `get_all` page, `?page=0&page-size=100`) matches only that exact query;
several registrations of one URL are served in order, the last repeating (under
`OrderedRegistry`, one request each, in order, and a surplus request raises); a
`re.compile(...)` URL matches any URL it prefixes.

The `tenant` APIs keep the default `RetryConfig`, so a retryable status (429, 500, 502, 503,
504) on a GET, PUT or DELETE is retried up to three times; the fixture swaps the backoff sleep for
the `sleeps` list, so it costs no time. With the default registry one registration answers every
attempt; under `OrderedRegistry` register the URL once per attempt (`RetryConfig().total + 1`
times), as `test_pro_get_all_returns_a_failed_first_page_raw` in `tests/models_test.py` does. Error-path tests that
don't care about retries can use a status that isn't retried (400, 404).

### Classic test

(For a Classic simple endpoint the scaffolder adds rows to `tests/clc_endpoints_test.py` instead of
writing this file; a composite gets a file like it.)

```python
"""Unit tests for the Buildings endpoint."""
# pylint: disable=missing-function-docstring
from conftest import FQDN, sent_headers, with_bearer
from jamfpy.client.constants import DEFAULT_HTTP_CONFIG_HEADERS as H

BASE = f"{FQDN}/JSSResource"


def test_get_by_id_builds_id_url(classic_api, mocked_responses):
    mocked_responses.get(f"{BASE}/buildings/id/7", json={"building": {"id": 7}})
    classic_api.buildings.get_by_id(7)
    req = mocked_responses.calls[-1].request
    assert req.method == "GET"
    assert req.url == f"{BASE}/buildings/id/7"
    assert sent_headers(req) == with_bearer(H["crud"]["read"]["json"])


def test_create_posts_xml_to_id_zero(classic_api, mocked_responses):
    mocked_responses.post(f"{BASE}/buildings/id/0", status=201, body="<building><id>8</id></building>")
    classic_api.buildings.create("<building/>")
    req = mocked_responses.calls[-1].request
    assert req.method == "POST"
    assert req.url == f"{BASE}/buildings/id/0"
    assert sent_headers(req) == with_bearer(H["crud"]["create-update"]["xml"])
    assert req.body == "<building/>"
```

### Pro test

(The scaffolder writes this file, one test per composed method, for every Pro CRUD endpoint; an
action gets a single `send` test.)

```python
"""Unit tests for the Pro Things endpoint."""
# pylint: disable=missing-function-docstring
import json

from conftest import FQDN, sent_headers, with_bearer
from jamfpy.client.constants import DEFAULT_HTTP_CONFIG_HEADERS as H

BASE = f"{FQDN}/api/v1"      # Pro URLs carry the version


def test_get_by_id_builds_v1_url(pro_api, mocked_responses):
    mocked_responses.get(f"{BASE}/things/5", json={"id": "5"})
    pro_api.things.get_by_id(5)
    req = mocked_responses.calls[-1].request
    assert req.method == "GET"
    assert req.url == f"{BASE}/things/5"
    assert sent_headers(req) == with_bearer(H["crud"]["read"]["json"])


def test_create_sends_json_body(pro_api, mocked_responses):
    mocked_responses.post(f"{BASE}/things", status=201, json={"id": "6"})
    pro_api.things.create({"name": "x"})
    req = mocked_responses.calls[-1].request
    assert req.method == "POST"
    assert req.url == f"{BASE}/things"
    assert sent_headers(req) == with_bearer(H["crud"]["create-update"]["json"])
    assert json.loads(req.body) == {"name": "x"}
```

Test-file conventions:
- Module docstring, then `# pylint: disable=missing-function-docstring`. Add
  `,redefined-outer-name` if the module defines a fixture its tests take as an argument, and
  `,protected-access` (or inline) when touching `_uri`/`_name`.
- Function names are behavioural: `test_<what>_<expected>` (e.g. `test_get_by_id_builds_v1_url`).
- For a method that reads its response (`get_all`, the accounts transforms), register a
  realistic body (and status) and assert on both the returned response and the request(s) in
  `mocked_responses.calls`.

Run the suite from the repo root: `make test`.

`make scaffold` writes these tests for you: for a Pro endpoint one test per method in the shape of the
Pro test below (plus a check of the methods it has and lacks, and `name()`); for a Classic composite
the same for the parent's `get_all` and each child's methods, parametrised over the children; for a
Classic simple endpoint, which inherits everything, a row in `CLASSIC_ENDPOINTS` and an entry in
`EXPECTED_ATTRS` in `tests/clc_endpoints_test.py`, whose parametrised tests cover every Classic endpoint.

### The contract test

`tests/contract_test.py` checks every endpoint against the schemas, and you don't add anything
to it for a new endpoint. At collection it builds a throwaway `Tenant` (which sends nothing) and
discovers the endpoints by introspection: every `Endpoint` instance attribute of `tenant.classic`
and `tenant.pro`, recursing into endpoints that hold endpoints (`classic.accounts.users`). So the
`self.things = Things(self)` line in `client.py` is what puts an endpoint under test. Every public
method on it (bar `name()`) becomes one test, with an id like `pro.things.get_by_id`: the method is
called with dummy arguments built from its signature (`int` → `1`, `str` → the sentinel
`"jamfpy-contract-arg"`, `list[str]` → `["jamfpy-contract-arg"]`, `dict` → `{}`, defaults as declared)
under a catch-all `responses` registration, and each
request it sends must be a path and verb in the schema once ids are normalised (`/v1/things/1` →
`/v1/things/{id}`, `/buildings/id/1` → `/buildings/id/{id}`; every `{param}` in the schema →
`{id}`; a path segment equal to the sentinel, URL-encoded or not, is `{id}` too, so a name-based lookup
like `/accounts/username/jamfpy-contract-arg` matches `/accounts/username/{id}`). A Classic write must
send an XML string as `data=`, a Pro write a `json=` body. Another test checks that `_uri` (with
`_version` for Pro) names paths the schema has. Discovery takes every public callable, so a public
`@staticmethod` or a callable assigned in `__init__` is tested as well. The check is that the
`(path, verb)` pair exists, so a valid verb that is wrong for the method on a path with several verbs
is for your `tests/<module>_test.py` to catch.

There is no allowlist. A failure reads
`pro.things.get_all sent GET /v1/things, which the pro schema has only for ['post']`: the
endpoint offers a method the API doesn't have, so fix the endpoint (compose only the mixins for the
verbs listed, or correct the URL), not the test. The one edit the test needs is bumping
`EXPECTED_ENDPOINT_COUNT` when you wire an endpoint (`make scaffold` does it); a parameter type it can't fill raises
`TypeError` naming the parameter, so teach `dummy_value` that type.

---

## Definition of done

- [ ] Scaffolded with `make scaffold API=… PATH=…` (or written by hand for a shape it refuses), its
      `_name` and docstrings reviewed, and its live builders filled in.
- [ ] Class added, with a docstring on every public class/method.
- [ ] Imported in `jamfpy/client/client.py` and attached in `ProAPI.__init__` /
      `ClassicAPI.__init__` (alias the import if the name clashes across APIs).
- [ ] Path, version, verbs and body shape verified against the schema (`make schema-paths` /
      `make schema-path` — not a full read); a Pro endpoint composes exactly the mixins for the
      verbs listed.
- [ ] A `tests/<module>_test.py` covers the request(s) it sends (mock only, via `responses` and the
      `tests/conftest.py` fixtures).
- [ ] Smoke test: `uv run python -c "import jamfpy; print(jamfpy.Tenant)"`.
- [ ] Tests pass: `make test`.
- [ ] The contract test passes for the new endpoint (`tests/contract_test.py`, part of `make test`): it
      finds the endpoint through its `client.py` attribute and tests every public method; bump its
      `EXPECTED_ENDPOINT_COUNT` (`make scaffold` does).
- [ ] Lint passes: `make lint`.
- [ ] Type check passes: `make typecheck` (every new parameter and return hinted).
- [ ] No live-request testing outside `tests/integration/` (the unit suite mocks the network); no edits to version/CHANGELOG.
- [ ] If committing: Conventional Commit (`feat:` for a new endpoint).
