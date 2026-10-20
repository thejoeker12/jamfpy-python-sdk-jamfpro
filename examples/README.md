# jamfpy examples

Standalone scripts, one per topic. Each builds its own `jamfpy.Tenant` from environment variables, prints a short
summary (counts, ids, names and status codes, never a token or a credential) and invalidates its token when it
finishes. Each file's docstring says what it shows.

| Example | What it shows |
|---|---|
| [quickstart.py](quickstart.py) | An OAuth tenant, `authenticate()`, a Classic and a Pro `get_all`, checking `.ok`, `close()`. |
| [basic_auth.py](basic_auth.py) | `auth_method="basic"` with a Jamf Pro user's username and password. |
| [error_handling.py](error_handling.py) | A 404 that comes back as a `Response`, and catching `JamfpyConfigError`, `JamfAuthError` and `requests` exceptions. |
| [unwrapped_endpoint.py](unwrapped_endpoint.py) | Calling an endpoint jamfpy doesn't wrap through `api.do()`, with `api.url()`, `api.header()` and a per-call `timeout=`. |
| [logging_output.py](logging_output.py) | `configure_logging` in text at INFO and JSON at DEBUG, `Tenant(log_level=...)` and `safe_mode`. |
| [timeouts_and_retries.py](timeouts_and_retries.py) | `timeout=` as a float and a `(connect, read)` tuple, `RetryConfig(...)` with `retry_post`, and `retries=None`. |
| [pagination.py](pagination.py) | A Pro `get_all(page_size=..., sort=...)`, its aggregated body, `parallelism` (and `1` for sequential), and a failed page returned raw. |
| [certificates.py](certificates.py) | `verify_path` and `cert_path`, and the CA bundle and proxy variables requests honours. |
| [request_hooks.py](request_hooks.py) | Thread-safe metrics hooks with `before_request`, `after_response` and `on_retry` as decorators, `RequestContext`, and `remove`. |
| [concurrent_requests.py](concurrent_requests.py) | Many `get_by_id` calls from a thread pool sharing one `Tenant`; `parallelism` does not cap them. |
| [classic_write_lifecycle.py](classic_write_lifecycle.py) | Create, read, update and delete a Classic category with XML bodies. |
| [pro_write_lifecycle.py](pro_write_lifecycle.py) | Create, read, update and delete a Pro script with JSON bodies. |

## Running them

From the repository root, after `make setup`:

```bash
uv run --env-file .env python examples/quickstart.py
```

Copy `.env.example` to `.env` and fill it in first. The variables:

| Variable | Read by |
|---|---|
| `JAMFPRO_INSTANCE_FQDN` | Every example. A bare host is fine: the examples add `https://`. |
| `JAMFPRO_CLIENT_ID`, `JAMFPRO_CLIENT_SECRET` | Every example except `basic_auth.py`. |
| `JAMFPRO_USERNAME`, `JAMFPRO_PASSWORD` | `basic_auth.py` only. Not in `.env.example`; add them to `.env` or export them. |
| `JAMFPY_EXAMPLE_CA_BUNDLE`, `JAMFPY_EXAMPLE_CLIENT_CERT` | `certificates.py` only, both optional: a CA bundle passed as `verify_path` and a PEM with client certificate and key passed as `cert_path`. |

`error_handling.py` also sends one token request with a deliberately wrong secret, and one to
`jamfpy-example.invalid`, a reserved name that never resolves.

## Write examples

**`classic_write_lifecycle.py` and `pro_write_lifecycle.py` change the tenant.** Each creates one record named
`jamfpy-example-<8 hex characters>` (a category, or a script), updates it and deletes it again, and deletes it in a
`finally` block if a step after the create fails. Run them against a development tenant. If one is interrupted
before the delete, look for the `jamfpy-example-` prefix and remove the record by hand. Every other example only
reads.

## Tests

`tests/examples_test.py` runs every example offline under `responses` as part of `make test`, so a change to jamfpy
that breaks an example fails the unit suite. `make typecheck` and `make lint` cover this folder too. Nothing runs the
examples against a real tenant.
