# Entry points

Every way jamfpy can be started or called by another app, and every way it emits information. One line per entry; [AGENTS.md](AGENTS.md) has the how and why, and each section names where.

## Python API

jamfpy is a library, so `import jamfpy` is its runtime entry. It needs Python 3.13 or newer (`requires-python`; CI runs 3.15, 3.14 and 3.13), depends on `requests` alone, and ships a `py.typed` marker (PEP 561) so type checkers use its inline hints. It installs no console scripts.

### Exported names

`jamfpy.__all__` holds these eleven names:

| Name | Role | Module |
|---|---|---|
| `Tenant` | Main entry point: validates config, builds one auth object and both APIs | `jamfpy/client/tenant.py` |
| `OAuth` | Auth with an API client ID and secret (`auth_method="oauth2"`) | `jamfpy/client/auth.py` |
| `BasicAuth` | Auth with a username and password, or a prebuilt `basic_auth_token` (`auth_method="basic"`) | `jamfpy/client/auth.py` |
| `API` | Base class of both APIs: owns the session, `do()`, `url()`, `header()` and `close()` | `jamfpy/client/api.py` |
| `ProAPI` | The modern Jamf Pro API (`/api/v{n}`), as `tenant.pro` | `jamfpy/client/client.py` |
| `ClassicAPI` | The Classic API (`/JSSResource`), as `tenant.classic` | `jamfpy/client/client.py` |
| `configure_logging` | Attaches one text or JSON handler to the `jamfpy` logger and returns it | `jamfpy/client/logger.py` |
| `Timeout` | Type alias: seconds as a `float`, or a `(connect, read)` tuple | `jamfpy/client/constants.py` |
| `RetryConfig` | Frozen dataclass of retry rules, for `Tenant(retries=...)` | `jamfpy/client/retry.py` |
| `Hooks` | Registry of request hooks: `before_request`, `after_response`, `on_retry`, `remove` | `jamfpy/client/hooks.py` |
| `RequestContext` | Frozen dataclass handed to every hook: `tenant`, `api`, `attempt`, `started` | `jamfpy/client/hooks.py` |

`jamfpy.client.logger` also keeps `DEFAULT_FORMAT` (equal to `TEXT_FORMAT`) and `DEFAULT_LEVEL` (`logging.INFO`), public there on 2.x, as compatibility aliases. They are not in `__all__`.

`Tenant` takes keyword arguments only: `fqdn` (a full URL such as `https://acme.jamfcloud.com`), `auth_method` (`"oauth2"` or `"basic"`), `client_id`, `client_secret`, `username`, `password`, `http_config`, `token_exp_threshold_mins`, `log_level`, `safe_mode`, `cert_path`, `verify_path`, `timeout`, `retries` and `parallelism`. Construction makes no network call. The request path is in [Architecture and request lifecycle](AGENTS.md#architecture--request-lifecycle).

### Exceptions

Not exported from the package root; import them from `jamfpy.client.exceptions`.

- `JamfpyConfigError`: `Tenant` raises it for an unknown `auth_method`, empty credentials, or a `cert_path` or `verify_path` that is missing or a directory.
- `JamfAuthError`: the auth classes raise it when the token or keep-alive request is refused; it reaches the caller from `Tenant.authenticate()` or the first request.
- `JamfAPIError`: defined, but nothing raises it.
- `JamfpyInitError`: defined, but nothing raises it.
- Other errors: `ValueError` for a bad `parallelism`, `RetryConfig` field or `configure_logging` format; `requests` exceptions from the send once retries are spent. A non-2xx status never raises.

### Per-API objects

- `tenant.pro` (`ProAPI`) and `tenant.classic` (`ClassicAPI`): the two APIs, each with its endpoints as attributes (`tenant.pro.scripts`, `tenant.classic.buildings`).
- `tenant.hooks` (`Hooks`): the one registry both APIs share.
- `tenant.authenticate()`: fetches a token now, so bad credentials or an unreachable FQDN fail there; without it the first request authenticates.
- `api.do(request, timeout=None)`: sends a `requests.Request` with the token, retries and hooks, and returns the raw `requests.Response`; `timeout` overrides the configured one for that call.
- `api.url(target=None)`: the API's base URL; Pro takes the version string as `target`, Classic ignores it.
- `api.header(key)`: a header set from `jamfpy/client/constants.py`, such as `"read"`.
- `api.close()`: invalidates the token. Pro and Classic share one auth object, so closing either ends it for both; `Tenant` has no `close()`.

### Endpoint methods

Every endpoint method returns a `requests.Response`.

- Classic endpoints: `get_all(suffix=None, xml_response=False)`, `get_by_id(target_id, xml_response=False)`, `create(config_profile)`, `update_by_id(target_id, updated_configuration)`, `delete_by_id(target_id)` and `name()`; write bodies are XML strings.
- Pro endpoints compose capability mixins: `get_all(page_size=None, sort=None)`, `get_by_id(target_id)`, `create(payload)`, `update_by_id(target_id, payload)`, `delete_by_id(target_id)` and `name()`; bodies are dicts. `get_all` pages in parallel and returns one aggregated `Response`. An endpoint composes only the verbs it needs (`pro.dock_items` has no `get_all`).
- Action and composite endpoints: `pro.mdm` has `send_command(command_type, management_ids, **kwargs)` and convenience wrappers; `classic.accounts` holds `.users` and `.groups`.
- The wired endpoints, their paths, methods and live-test status are in [COVERAGE.md](COVERAGE.md), which is generated.

Retries, hooks, concurrency and logging: [Retries](AGENTS.md#retries), [Request hooks](AGENTS.md#request-hooks), [Concurrency](AGENTS.md#concurrency), [Logging](AGENTS.md#logging).

## Make targets

`make help` lists them, and it is the default goal. Run them from the repo root; the Python ones go through `uv run`.

| Target | What it does | Arguments | Reads `.env` | Needs the live tenant |
|---|---|---|---|---|
| `help` | List the available targets | none | no | no |
| `setup` | Create or refresh `.venv` from `uv.lock` (`uv sync`) | none | no | no (fetches packages) |
| `lock` | Re-resolve `uv.lock` after a dependency change in `pyproject.toml` (`uv lock`); commit both | none | no | no (reads the package index) |
| `lint` | pylint over every tracked Python file; fails under 9.0 | none | no | no |
| `typecheck` | mypy, strict, over `jamfpy` and `tools` | none | no | no |
| `test` | The offline unit suite | none | no | no |
| `coverage` | The unit suite with branch coverage of `jamfpy`; fails under 90% | none | no | no |
| `test-integration` | The live suite: `pytest -m integration tests/integration -v` | none | yes, when `.env` exists | yes |
| `check` | `lint typecheck coverage coverage-doc-check`: every gate CI runs, none live | none | no | no |
| `check-matrix` | `check` once per interpreter, each in its own `.venv-<version>` | `PYTHON_VERSIONS` (default `3.15 3.14 3.13`) | no | no |
| `schemas` | Pull both schemas and re-probe `pro-supplement.json` (verbs and observed shapes); writes all three files only if every step succeeds. Its probe creates and deletes one disabled App Installers deployment | none | yes, when `.env` exists | yes |
| `schema-paths` | List schema paths and their verbs | `API=` (`pro` or `classic`, required), `MATCH=` (optional text) | no | no |
| `schema-path` | Show one path's methods, parameters and resolved request body | `API=` (required), `PATH=` or `SCHEMA_PATH=` (required) | no | no |
| `scaffold` | Generate an endpoint, its wiring, tests and live spec from the schema | `API=` (required), `PATH=` or `SCHEMA_PATH=` (required), `NAME=` (a PascalCase class name), `DRY_RUN=1` | no | no |
| `coverage-doc` | Regenerate `COVERAGE.md` | none | no | no |
| `coverage-doc-check` | Fail with a diff when `COVERAGE.md` is stale | none | no | no |

- Only `test-integration` and `schemas` pass `--env-file .env` to `uv run`, and only when the file exists; CI sets the variables directly. Nothing else reads `.env`.
- A missing `API=` or path makes `schema-paths`, `schema-path` and `scaffold` print a `usage:` line on stderr and exit 2. `test-integration` checks its three variables first and exits non-zero with `test-integration: missing or empty env vars: ...` before pytest starts.
- `MATCH`, `NAME` and `DRY_RUN` switch on with any non-empty value.
- `PATH=` is also make's search path. The Makefile keeps the value as the schema path and restores the `PATH` make inherited, which works on macOS make 3.81 and GNU make up to 4.3. On GNU make 4.4 and newer it stops with a message; pass `SCHEMA_PATH=<path>` there, which works everywhere. See [Schemas](AGENTS.md#schemas).

## Tools scripts

Run from the repo root as `uv run python -m tools.<name>`; the make targets wrap them. `tools/` is dev tooling and is not packaged. None of the scripts reads `.env` itself, so run directly they need the variables exported. A refusal is a line on stderr prefixed with the tool's name (`schemas:`, `scaffold:`, `coverage-doc:`) and exit 1; a usage error exits 2.

### tools.schemas

Reads and queries `api_schemas/`, and is the only code that parses those files. Exit 0 on success; 1 with one `schemas: <reason>` line on stderr (no source set, probe credentials missing, unknown path with the closest matches, a failed fetch or probe), nothing written; 2 for a usage error.

| Subcommand | Arguments | Reads | Writes |
|---|---|---|---|
| `refresh` | none (`make schemas`) | The three `JAMFPRO_*` variables, optional source overrides, `pro-supplement.json`; fetches both schemas and probes the tenant as `probe` does | `api_schemas/pro.json`, `classic.json` and `pro-supplement.json`, all or none; prints the probe's `probe:` lines, then each drift |
| `pull` | `[--api {pro,classic}]` (default both) | `JAMFPRO_INSTANCE_FQDN` or the source override; fetches the schema | `pro.json` and/or `classic.json`; prints the drift |
| `probe` | none | The three `JAMFPRO_*` variables, `pro-supplement.json`; probes the tenant: OPTIONS per path, a GET and a `POST {}` per path without a `{param}`, and one disabled App Installers deployment created, read and deleted | `pro-supplement.json`; on the tenant, that one deployment (deleted again, or the run fails naming it); prints a `probe:` line for its create and delete, then the drift |
| `drift` | `--api {pro,classic}` (required), `[--source URL-or-path]` | The committed schema and the source (default as `pull`) | nothing; prints the drift |
| `paths` | `--api {pro,classic}` (required), `[--match TEXT]` (`make schema-paths`) | The committed schemas | nothing; prints paths and verbs |
| `path` | `--api {pro,classic}` (required), `PATH` (`make schema-path`) | The committed schemas | nothing; prints one path as JSON, `$ref`s resolved |

### tools.scaffold

`uv run python -m tools.scaffold --api {pro,classic} --path PATH [--name NAME] [--root ROOT] [--dry-run]` (`make scaffold`). `--path` is the collection path exactly as the schema has it, `--name` a PascalCase class name, `--root` the repo to scaffold into (default this one), `--dry-run` prints the shape and the files and writes nothing.

- Reads: `<root>/api_schemas` (through `tools.schemas`) and the files it edits or checks against, under `jamfpy/` and `tests/`. No `.env`, no network.
- Writes, all or nothing (each file is staged as `.<name>.scaffold-tmp`, then swapped in): a new `jamfpy/endpoints/pro_<slug>.py` or `clc_endpoints_<slug>.py` (a simple Classic class goes into `clc_endpoints.py`); `jamfpy/client/client.py`; the unit test module (or rows in `tests/clc_endpoints_test.py`); a spec in `tests/integration/pro_resources_live_test.py` or `clc_resources_live_test.py` when the endpoint has the four lifecycle methods; `EXPECTED_ENDPOINT_COUNT` in `tests/contract_test.py`. It never writes `COVERAGE.md`.
- Exit 0 prints the shape, a `would write:` or `wrote:` file list, `next:` lines and `regenerate COVERAGE.md with make coverage-doc`. Exit 1 is a refusal or failed write: one `scaffold: <reason>` line on stderr, nothing written. Exit 2 is a usage error.
- The shapes and refusal rules: [Scaffold first](AGENTS.md#scaffold-first-make-scaffold).

### tools.coverage_doc

`uv run python -m tools.coverage_doc [--root ROOT] [--check]` (`make coverage-doc`, `make coverage-doc-check`). `--root` is the repo whose `COVERAGE.md` to write or check (default this one; its `jamfpy` must be the one imported); `--check` writes nothing.

- Reads: the wired endpoints, the two live modules' `SPECS` and `LIVE_NOT_COVERED` (imported, so no tenant variables are needed), and `<root>/api_schemas`. It sends no request.
- Writes: `<root>/COVERAGE.md` only, and only when it differs.
- Exit 0 prints `wrote COVERAGE.md` or `COVERAGE.md is up to date`. Exit 1 prints one `coverage-doc: <problem>` line per problem on stderr and writes nothing; under `--check` a stale file also gets a unified diff on stdout and `coverage-doc: COVERAGE.md is stale; run make coverage-doc` on stderr.
- What it records and refuses: [COVERAGE.md](AGENTS.md#coveragemd-make-coverage-doc).

### tools.introspect

A library module with no command line: `python -m tools.introspect` runs nothing and prints nothing. `tools.coverage_doc` and `tests/contract_test.py` import it for what counts as a public endpoint method, the dummy arguments and the stub `do` that records requests. It sends nothing and writes nothing.

## Environment variables

| Variable | Read by | Required |
|---|---|---|
| `JAMFPRO_INSTANCE_FQDN` | A `.env` key. The live `tenant` fixture, the `test-integration` check, `tools.schemas` (schema URLs, the probe's tenant) | For `make test-integration`, `refresh` and `probe`; for `pull` and `drift` unless the source override is set. The SDK never reads it |
| `JAMFPRO_CLIENT_ID` | A `.env` key. The live fixture, the `test-integration` check, the `tools.schemas` probe | For `make test-integration`, `refresh` and `probe` |
| `JAMFPRO_CLIENT_SECRET` | A `.env` key. The same readers as the client ID | For `make test-integration`, `refresh` and `probe` |
| `JAMFPY_PRO_SCHEMA_SOURCE` | `tools.schemas` `refresh`, `pull` and `drift`: a URL or local path that replaces the Pro schema URL on the tenant | No |
| `JAMFPY_CLASSIC_SCHEMA_SOURCE` | The same, for the Classic schema | No |
| `UV_PYTHON` | uv. `make check-matrix` sets it per version; every CI job sets it | No |
| `UV_PROJECT_ENVIRONMENT` | uv. `make check-matrix` sets it to `.venv-<version>` | No |
| `UV_FROZEN` | uv. Every CI job sets it to `1` so `uv run` never rewrites `uv.lock` | No |
| `REQUESTS_CA_BUNDLE`, `CURL_CA_BUNDLE` | `requests`, on API and auth calls; an explicit `verify_path` wins | No |
| `HTTP_PROXY`, `HTTPS_PROXY`, `NO_PROXY` | `requests`, on API and auth calls | No |
| `GITHUB_RUN_ID` | The `unique_name` fixture, which falls back to `local`; GitHub Actions sets it | No |

The three `JAMFPRO_*` keys are the whole of `.env.example`. `jamfpy` itself reads no environment variable of its own: credentials are `Tenant` arguments. In CI the integration workflow takes them from a repository variable and two secrets.

## Inputs the project reads

- `api_schemas/pro.json` and `classic.json`: Jamf's schemas as the tenant serves them. Only `make schemas` writes them. Only `tools/schemas.py` parses them; `make schema-paths`, `make schema-path`, `tools.scaffold`, `tools.coverage_doc` and `tests/contract_test.py` all go through it.
- `api_schemas/pro-supplement.json`: Pro paths the tenant serves but `pro.json` leaves out, with the verbs an OPTIONS probe found and the shapes it observed (`x-jamfpy-observed`). `make schemas` writes it; the only hand edit is adding or removing a path template. `tools.schemas` merges it into the Pro schema.
- `api_schemas/api-reference-url.txt`: a pointer for people to Jamf's reference; no code reads it.
- `.env`: gitignored; `.env.example` is the tracked template. Read by `make test-integration` and `make schemas` only.
- `uv.lock`: read by `uv sync` (`make setup`, and `uv sync --frozen` in CI). Only `make lock` (`uv lock`) changes it, after an edit to `pyproject.toml`.
- `pyproject.toml` and `.pylintrc`: package metadata and the pytest, mypy and pylint configuration.

The schema rules are in [Schemas](AGENTS.md#schemas).

## Outputs the project emits

### HTTP requests to a Jamf Pro tenant

All go to the `fqdn` you give `Tenant`. Certificate verification is always on: `verify_path` or the CA-bundle variables only choose the bundle.

- Auth, never retried and never hooked: `POST /api/oauth/token` (OAuth), `POST /api/v1/auth/token` (Basic), `POST /api/v1/auth/keep-alive` (Basic, a token inside the refresh buffer) and `POST /api/v1/auth/invalidate-token` (`close()`).
- Classic: `GET`, `POST`, `PUT` and `DELETE` to `/JSSResource/...`, with XML bodies for writes.
- Pro: the same verbs to `/api/v{n}/...`, with JSON bodies; the version is per endpoint.
- Every API request carries `Authorization: Bearer <token>`. API and auth calls send `User-Agent: jamfpy/<installed version>`, or `jamfpy/unknown` when jamfpy is not installed as a distribution.
- `tools.schemas` (not the SDK): unauthenticated `GET /api/schema/` and `GET /classicapi/doc/swagger.yaml` with requests' default User-Agent, or the URL in a source override; and, for the probe, through the SDK: an `OPTIONS` to each path template in `pro-supplement.json`, with `0` for each `{param}`; a `GET` and a `POST {}` (which fails validation, so creates nothing) to each template without a `{param}`; and its one write, `POST /api/v1/app-installers/deployments` creating a deployment with `enabled: false` named `jamfpy-schemas-probe-<8 hex>`, then `GET` and `DELETE` of that deployment and a `GET` that must answer 404.

### Log records

- The `jamfpy` logger has only a `NullHandler`, so nothing is printed until `configure_logging()` is called.
- Each tenant logs through `jamfpy.{tenant}-auth`, `jamfpy.{tenant}-pro` and `jamfpy.{tenant}-clc`, where `{tenant}` is the FQDN's host up to its first dot (`acme` for `https://acme.jamfcloud.com`).
- `configure_logging(level=INFO, fmt="text", stream=None)` writes to `stream` (`sys.stdout` when `None`). Text lines are `%(asctime)s [%(levelname)s] (%(name)s): %(message)s` with `jamfpy.` stripped from the name. `fmt="json"` writes one object per line: `ts` (UTC, ISO 8601, milliseconds, `Z`), `level`, `sender`, `message`, and each of the structured fields below when the record has it.
- The API request lines pass `method`, `url`, `status`, `duration_ms` and `attempt` as `extra`, so they are attributes on those `LogRecord`s for filters and formatters, as well as the JSON keys above (auth lines carry the first four).
- Levels, what each logs and what `safe_mode` redacts: [Logging](AGENTS.md#logging).

### Callbacks

Request hooks registered on `tenant.hooks` fire per HTTP attempt for API requests only: `before_request(prepared, ctx)`, `after_response(prepared, response, ctx)` and `on_retry(prepared, ctx, reason, delay)`. See [Request hooks](AGENTS.md#request-hooks).

### Generated files

- `COVERAGE.md`: written by `make coverage-doc`; no timestamps, so the same tree gives the same bytes. Never hand-edited.
- Scaffolded files: those listed under tools.scaffold above.
- `api_schemas/pro.json`, `classic.json` and `pro-supplement.json`: rewritten by `make schemas`.

### Packages

`uv build` produces `dist/` (gitignored): a wheel holding the `jamfpy` package with `py.typed`, and an sdist with the same package, `README.md`, `pyproject.toml` and setuptools' generated `setup.cfg` and `.egg-info`. Neither includes `tools/`, `tests/` or `api_schemas/`. `README.md` is the PyPI long description. No workflow runs `uv build`; `pypi-publish.yml` builds with `python -m build`.

### Test evidence

The repo keeps none. `make coverage` writes `.coverage`; `.pytest_cache/` and `.mypy_cache/` appear too, and `htmlcov/` and `coverage.xml` are ignored although no target produces them. All are gitignored. The live suite writes nothing locally; it creates and deletes records on the tenant (see Live tenant contract).

## CI and release workflows

All four are in `.github/workflows/`.

- `ci.yml`: runs on every `pull_request` (no base-branch filter, so stacked PRs are checked) and every `push` to `main`. Read-only permissions; the concurrency group `ci-${{ github.ref }}` cancels an older run on the same ref. Four jobs on `ubuntu-latest`: `lint` (3.13, `make lint`), `typecheck` (3.13, `make typecheck`), `test` (matrix 3.15, 3.14 and 3.13 with `fail-fast: false`, `make coverage`) and `coverage-doc` (3.13, `make coverage-doc-check`). Each job runs `actions/checkout@v4`, `astral-sh/setup-uv@v10.3.0` with its cache on, `uv python install <version>`, `uv sync --frozen`, then the make target, with `UV_PYTHON` and `UV_FROZEN=1` set.
- `integration-test.yml`: runs on `workflow_dispatch` and on `pull_request` to `main` only, so a stacked PR aimed at another branch does not trigger it. The job is skipped, not failed, unless the repository variable `JAMFPRO_INSTANCE_FQDN` is non-empty and the run is a manual dispatch or the PR head is in this repository (forks get no secrets). It needs the variable `JAMFPRO_INSTANCE_FQDN` and the secrets `JAMFPRO_CLIENT_ID` and `JAMFPRO_CLIENT_SECRET`. The concurrency group `jamf-live-tenant` runs one live job at a time and never cancels one in progress. It installs with uv on 3.13 and runs `make test-integration`.
- `release-please.yml`: runs on `push` to `main` with `googleapis/release-please-action@v4`, `release-type: python` and the `TOKEN_RELEASE_PLEASE` secret; the repo has no release-please config file, so defaults apply. It opens or updates a release PR that edits `CHANGELOG.md` and the version in `pyproject.toml`. `feat:` is a minor bump, `fix:` a patch, and `chore:` or `docs:` no release. A `!` after the type or a `BREAKING CHANGE:` footer is a major bump.
- `pypi-publish.yml`: `workflow_dispatch` only, so nothing publishes automatically. It builds an sdist and wheel with `python -m build` and publishes with `pypa/gh-action-pypi-publish@release/v1` through PyPI trusted publishing (`id-token: write`; no token is referenced). It builds on Python 3.12 although `requires-python` is `>=3.13`; the workflow has not been updated to match.

The gates and the commit rules: [Quality gates and workflow](AGENTS.md#quality-gates--workflow).

## Live tenant contract

The live suite is opt-in: `make test-integration` or `integration-test.yml`. Every test under `tests/integration` is marked `integration`, which the default run deselects.

- Needs `JAMFPRO_INSTANCE_FQDN` (`https://` is added when the value does not start with `http`), `JAMFPRO_CLIENT_ID` and `JAMFPRO_CLIENT_SECRET`. With any missing it fails, never skips. It authenticates with OAuth client credentials at fixture setup and invalidates the token at teardown.
- Creates, for each live spec in `tests/integration/*_resources_live_test.py`, a minimal record and, where the spec has a `max` builder, a maximal one, each taken through create, read, update, read, delete and a 404 read; and a few extra records for the SDK-behaviour checks in `sdk_behaviour_live_test.py`. The resources covered are in [COVERAGE.md](COVERAGE.md).
- Every created record is named `jamfpy-it-{GITHUB_RUN_ID or local}-{8 hex characters}` (the `unique_name` fixture), so a leftover traces back to its run.
- The `janitor` fixture holds every `(endpoint, id, ok_codes)` registered right after a create and deletes them at teardown, even when the test failed. A 404 counts as success; any other status fails the run with `cleanup failed for: ...`, and the surviving record keeps the `jamfpy-it-` prefix.
- Reads existing records only where a test needs them (listing `categories`, `scripts`, the app installer catalog titles and deployments). It deletes only ids it registered.
- Every App Installers deployment it creates has `enabled: false`, so none reaches a device.
- Outside the live suite, `make schemas` is the one other thing that writes to the tenant: its probe creates one disabled deployment named `jamfpy-schemas-probe-<8 hex>` and deletes it in the same run, or fails naming it (see [Schemas](AGENTS.md#schemas)).
- Never sends an MDM command (`pro.mdm` has no live spec) and never changes tenant-wide settings: no live spec or test touches a settings path, and the app installers `global-settings` path is not wired in the SDK.
