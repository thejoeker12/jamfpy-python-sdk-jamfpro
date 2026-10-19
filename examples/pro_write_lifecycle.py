"""Pro writes: create, read, update and delete a script with JSON bodies.

Pro writes take a dict, sent as JSON. Jamf answers a create with 201 and ``{"id": "42", "href": ...}`` (the id is
a JSON string), an update with 200, and a delete with 204.

WARNING: this example writes to the tenant. It creates one script named ``jamfpy-example-<8 hex>``, updates it
and deletes it again; if a step fails after the create, the ``finally`` block still deletes it. The script is
never scoped to a policy, so it never runs on a device.

Run it from the repository root:

    uv run --env-file .env python examples/pro_write_lifecycle.py

Needs ``JAMFPRO_INSTANCE_FQDN``, ``JAMFPRO_CLIENT_ID`` and ``JAMFPRO_CLIENT_SECRET`` (see ``.env.example``).
"""

import os
import secrets
from typing import Any

import jamfpy


def require_env(name: str) -> str:
    """The value of an environment variable this example needs, or exit naming the one that is missing."""
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"Set {name}: copy .env.example to .env and run with uv run --env-file .env")
    return value


def tenant_fqdn() -> str:
    """The tenant URL from ``JAMFPRO_INSTANCE_FQDN``.

    ``Tenant`` needs the scheme, and a ``.env`` often holds the bare host, so ``https://`` is added when missing.
    """
    fqdn = require_env("JAMFPRO_INSTANCE_FQDN")
    return fqdn if fqdn.startswith("http") else f"https://{fqdn}"


def script_body(name: str, notes: str) -> dict[str, Any]:
    """The Pro JSON body for a script (``make schema-path API=pro PATH=/v1/scripts`` lists every field)."""
    return {
        "name": name,
        "notes": notes,
        "priority": "AFTER",
        "scriptContents": '#!/bin/sh\necho "jamfpy example"\n',
    }


def read_name(pro: jamfpy.ProAPI, script_id: int) -> str | None:
    """The script's name as Jamf now stores it, or ``None`` when the read fails."""
    response = pro.scripts.get_by_id(script_id)
    return str(response.json()["name"]) if response.ok else None


def main() -> None:
    """Walk one script through create, read, update and delete."""
    tenant = jamfpy.Tenant(
        fqdn=tenant_fqdn(),
        auth_method="oauth2",
        client_id=require_env("JAMFPRO_CLIENT_ID"),
        client_secret=require_env("JAMFPRO_CLIENT_SECRET"),
    )
    scripts = tenant.pro.scripts
    name = f"jamfpy-example-{secrets.token_hex(4)}"
    created_id: int | None = None
    try:
        created = scripts.create(script_body(name, notes="Created by examples/pro_write_lifecycle.py"))
        if not created.ok:
            print("Create failed with", created.status_code)
            return
        created_id = int(created.json()["id"])
        print(f"Created script {created_id}: {name}")
        print("Read back:", read_name(tenant.pro, created_id))

        # The whole body again, not only the changed fields: jamfpy sends it as given and merges nothing.
        updated = scripts.update_by_id(created_id, script_body(f"{name}-updated", notes="Updated"))
        print("Update:", updated.status_code)
        print("Read back:", read_name(tenant.pro, created_id))

        deleted = scripts.delete_by_id(created_id)
        print("Delete:", deleted.status_code)
        if deleted.ok:
            created_id = None
    finally:
        if created_id is not None:
            # A step after the create failed or raised: remove the record rather than leave it on the tenant.
            print("Cleanup delete:", scripts.delete_by_id(created_id).status_code)
        tenant.pro.close()


if __name__ == "__main__":
    main()
