"""Classic writes: create, read, update and delete a category with XML bodies.

Classic writes take an XML string. Jamf answers a create or an update with 201 and the record's id as XML
(``<category><id>42</id></category>``), and a delete with 200. Reads come back as JSON by default.

WARNING: this example writes to the tenant. It creates one category named ``jamfpy-example-<8 hex>``, renames
it and deletes it again; if a step fails after the create, the ``finally`` block still deletes it.

Run it from the repository root:

    uv run --env-file .env python examples/classic_write_lifecycle.py

Needs ``JAMFPRO_INSTANCE_FQDN``, ``JAMFPRO_CLIENT_ID`` and ``JAMFPRO_CLIENT_SECRET`` (see ``.env.example``).
"""

import os
import secrets
from xml.etree import ElementTree
from xml.sax.saxutils import escape

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


def category_xml(name: str, priority: int) -> str:
    """The Classic XML body for a category."""
    # Escaped, because a name with & or < would otherwise make the body invalid XML.
    return f"<category><name>{escape(name)}</name><priority>{priority}</priority></category>"


def read_name(classic: jamfpy.ClassicAPI, category_id: int) -> str | None:
    """The category's name as Jamf now stores it, or ``None`` when the read fails."""
    response = classic.categories.get_by_id(category_id)
    return str(response.json()["category"]["name"]) if response.ok else None


def main() -> None:
    """Walk one category through create, read, update and delete."""
    tenant = jamfpy.Tenant(
        fqdn=tenant_fqdn(),
        auth_method="oauth2",
        client_id=require_env("JAMFPRO_CLIENT_ID"),
        client_secret=require_env("JAMFPRO_CLIENT_SECRET"),
    )
    categories = tenant.classic.categories
    name = f"jamfpy-example-{secrets.token_hex(4)}"
    created_id: int | None = None
    try:
        created = categories.create(category_xml(name, priority=9))
        if not created.ok:
            print("Create failed with", created.status_code)
            return
        id_text = ElementTree.fromstring(created.content).findtext("id")
        if id_text is None:
            print("Create answered without an id; look for a category named", name)
            return
        created_id = int(id_text)
        print(f"Created category {created_id}: {name}")
        print("Read back:", read_name(tenant.classic, created_id))

        updated = categories.update_by_id(created_id, category_xml(f"{name}-updated", priority=5))
        print("Update:", updated.status_code)
        print("Read back:", read_name(tenant.classic, created_id))

        deleted = categories.delete_by_id(created_id)
        print("Delete:", deleted.status_code)
        if deleted.ok:
            created_id = None
    finally:
        if created_id is not None:
            # A step after the create failed or raised: remove the record rather than leave it on the tenant.
            print("Cleanup delete:", categories.delete_by_id(created_id).status_code)
        tenant.classic.close()


if __name__ == "__main__":
    main()
