# API coverage

Which Jamf Pro server resources this SDK currently wraps, and which it doesn't yet. Jamf exposes
**two** HTTP APIs (see [`AGENTS.md`](AGENTS.md)); this SDK wraps a subset of each.

**How to read this**

- A *resource* here is one top-level path group — `/JSSResource/computers` (Classic) or `/v1/scripts`
  (Pro) — **not** an individual HTTP operation. Counts below are resources, not endpoints-times-verbs.
- A covered resource exposes the **full inherited CRUD** unless its *Notes* say otherwise:
  `get_all`, `get_by_id`, `create`, `update_by_id`, `delete_by_id` (Pro `get_all` also paginates).
- "In schema snapshot" is the resource count found in the bundled `api_schemas/*.json`. Jamf ships new
  resources continuously, so the denominators drift — treat them as an order-of-magnitude gauge, not gospel.

**Keep this current:** adding or removing an endpoint means editing this file in the same change — move
its row between the covered table and the *Not yet covered* list and adjust the summary counts. This is a
line item in `AGENTS.md` → *Definition of done*. Regeneration commands are at the bottom.

---

## Summary

| API | Resources covered | In schema snapshot | Rough coverage |
|-----|------------------:|-------------------:|---------------:|
| **Classic** (`tenant.classic.*`) | 16 | 79 | ~20% |
| **Pro** (`tenant.pro.*`) | 3 in-snapshot **+ 1** outside it | 123 | ~2% |

---

## Classic — covered (`tenant.classic.*`)

All rows expose **full CRUD** (`get_all`, `get_by_id`, `create`, `update_by_id`, `delete_by_id`) unless noted.
Classic write bodies are **XML strings**.

| SDK accessor | Resource (`/JSSResource`) | Notes |
|---|---|---|
| `classic.computers` | `/computers` | |
| `classic.computer_groups` | `/computergroups` | |
| `classic.computer_extension_attributes` | `/computerextensionattributes` | |
| `classic.computer_searches` | `/advancedcomputersearches` | |
| `classic.configuration_profiles` | `/osxconfigurationprofiles` | |
| `classic.mobile_devices` | `/mobiledevices` | |
| `classic.mobile_device_groups` | `/mobiledevicegroups` | |
| `classic.policies` | `/policies` | |
| `classic.scripts` | `/scripts` | Classic scripts (distinct from `pro.scripts`) |
| `classic.packages` | `/packages` | |
| `classic.categories` | `/categories` | |
| `classic.buildings` | `/buildings` | |
| `classic.departments` | `/departments` | |
| `classic.sites` | `/sites` | |
| `classic.restricted_software` | `/restrictedsoftware` | |
| `classic.accounts` | `/accounts` | Composite: `.get_all()` returns the whole payload; sub-endpoints `.users` and `.groups` each expose full CRUD (no top-level `create`/`get_by_id`) |

## Pro — covered (`tenant.pro.*`)

Pro bodies are **JSON dicts**. Full CRUD = the five methods above (with a paginating `get_all`).

| SDK accessor | Path | Version | Methods / notes |
|---|---|---|---|
| `pro.scripts` | `/scripts` | v1 | full CRUD |
| `pro.dock_items` | `/dock-items` | v1 | full CRUD — collection path is **POST-only** in the schema, so `get_all` is best-effort |
| `pro.mdm` | `/mdm/commands` | v2 | **Verb endpoint** (not CRUD): `send_command` + ~29 convenience wrappers (`lock_device`, `erase_device`, `restart_device`, …) |
| `pro.app_installers` | `/app-installers/deployments` | v1 | full CRUD inherited, but this resource is **not in the bundled `pro.json` snapshot** — `get_all`/`update_by_id` are best-effort |

---

## Live integration test coverage (min/max)

Which covered resources have live min/max lifecycle tests (`tests/integration/` — create with
required fields only / all writable fields, then read → update → read → delete against a real
tenant; see `AGENTS.md` → *Quality gates*). Specs live in
`tests/integration/clc_resources_live_test.py` and `pro_resources_live_test.py`.

**Keep this current:** adding an endpoint, or adding/changing a spec, means updating this table in
the same change — this is a line item in `AGENTS.md` → *Definition of done*.

| SDK accessor | API | Min | Max | Notes |
|---|---|:-:|:-:|---|
| `classic.categories` | Classic | ✅ | ✅ | |
| `classic.buildings` | Classic | ✅ | ✅ | |
| `classic.departments` | Classic | ✅ | ✅ | Name-only resource — min ≡ max |
| `classic.sites` | Classic | ✅ | ✅ | Name-only resource — min ≡ max |
| `classic.scripts` | Classic | ✅ | ✅ | |
| `classic.packages` | Classic | ✅ | ✅ | Metadata only — no file upload |
| `classic.computer_extension_attributes` | Classic | ✅ | ✅ | Text Field input type |
| `classic.computer_groups` | Classic | ✅ | ✅ | Min = static, max = smart; `criteria` sent, not echo-asserted |
| `classic.mobile_device_groups` | Classic | ✅ | ✅ | Min = static, max = smart; `criteria` sent, not echo-asserted |
| `classic.policies` | Classic | ✅ | ✅ | Created disabled, no scope |
| `classic.configuration_profiles` | Classic | ✅ | ✅ | Minimal plist; `payloads` sent, not echo-asserted |
| `classic.computer_searches` | Classic | ✅ | ✅ | `criteria`/`display_fields` sent, not echo-asserted |
| `classic.computers` | Classic | ✅ | ✅ | Fabricated inventory record |
| `classic.mobile_devices` | Classic | ✅ | ✅ | Fabricated udid/serial |
| `classic.restricted_software` | Classic | ✅ | ✅ | |
| `classic.accounts.users` | Classic | ✅ | ✅ | Creates a real (Custom, zero-privilege) account; generated password, never echo-asserted |
| `classic.accounts.groups` | Classic | ✅ | ✅ | `privileges` sent, not echo-asserted |
| `classic.accounts` (top level) | Classic | N/A | N/A | Composite `get_all` only — no CRUD surface of its own |
| `pro.scripts` | Pro | ✅ | ✅ | categoryId/categoryName omitted (instance-state dependent) |
| `pro.dock_items` | Pro | ✅ | ✅ | All fields required — min ≡ max |
| `pro.mdm` | Pro | N/A | N/A | Verb endpoint (send-command); no CRUD to lifecycle-test |
| `pro.app_installers` | Pro | ❌ | ❌ | Needs an App Installers catalog title + accepted T&Cs on the instance |

---

## Not yet covered

Resource groups present in the bundled schema that the SDK does **not** wrap. Adding any of these follows
`AGENTS.md` → *How to add an endpoint*.

### Classic (63)

```
activationcode, advancedmobiledevicesearches, advancedusersearches, allowedfileextensions,
classes, commandflush, computerapplications, computerapplicationusage, computercheckin,
computercommands, computerhardwaresoftwarereports, computerhistory, computerinventorycollection,
computerinvitations, computermanagement, computerreports, directorybindings,
diskencryptionconfigurations, distributionpoints, dockitems, ebooks, fileuploads, gsxconnection,
healthcarelistener, healthcarelistenerrule, ibeacons, infrastructuremanager,
jsonwebtokenconfigurations, jssuser, ldapservers, licensedsoftware, logflush, macapplications,
mobiledeviceapplications, mobiledevicecommands, mobiledeviceconfigurationprofiles,
mobiledeviceenrollmentprofiles, mobiledeviceextensionattributes, mobiledevicehistory,
mobiledeviceinvitations, mobiledeviceprovisioningprofiles, networksegments, patchavailabletitles,
patches, patchexternalsources, patchinternalsources, patchpolicies, patchreports,
patchsoftwaretitles, peripherals, peripheraltypes, printers, removablemacaddresses, savedsearches,
smtpserver, softwareupdateservers, userextensionattributes, usergroups, users, vppaccounts,
vppassignments, vppinvitations, webhooks
```

> Note: Classic also exposes `dockitems`; the SDK currently implements the **Pro** dock-items resource only.

### Pro (120)

```
account-groups, account-preferences, accounts, activation-code, adue-session-token-settings,
advanced-mobile-device-searches, advanced-user-content-searches, api-integrations,
api-role-privileges, api-roles, apns-client-push-status, app-request, app-store-country-codes, auth,
branding-images, buildings, cache-settings, categories, check-in, classic-ldap, cloud-azure,
cloud-distribution-point, cloud-idp, cloud-information, cloud-ldaps, computer-extension-attributes,
computer-groups, computer-inventory, computer-inventory-collection-settings, computer-prestages,
computers, computers-inventory, computers-inventory-detail, conditional-access, csa, dashboard, ddm,
departments, deploy-package, device-communication-settings, device-enrollments, devices,
distribution-points, dss-declarations, ebooks, enrollment, enrollment-customization,
enrollment-customizations, groups, gsx-connection, health-check, health-status, icon,
impact-alert-notification-settings, inventory-information, inventory-preload, jamf-connect,
jamf-management-framework, jamf-package, jamf-pro-information, jamf-pro-server-url, jamf-pro-version,
jamf-protect, jamf-remote-assist, jcds, last-login, ldap, ldap-keystore, local-admin-password,
locales, log-flushing, login-customization, m2m, macos-managed-software-updates,
managed-software-updates, mdm-renewal, mobile-device-apps, mobile-device-enrollment-profile,
mobile-device-extension-attributes, mobile-device-groups, mobile-device-prestages, mobile-devices,
notifications, oauth, oauth2, oidc, onboarding, packages, parent-app,
patch-management-accept-disclaimer, patch-policies, patch-software-title-configurations, pki,
policy-properties, preview, reenrollment, return-to-service, scheduler, self-service,
self-service-plus, service-discovery-enrollment, settings, sites, slasa, smart-computer-groups,
smart-mobile-device-groups, smart-user-groups, smtp-server, sso, startup-status, static-user-groups,
supervision-identities, system, teacher-app, time-zones, user, user-sessions, users,
volume-purchasing-locations, volume-purchasing-subscriptions
```

---

## Regenerating this document

The covered lists come from the endpoint classes; the schema totals come from `api_schemas/`. To refresh
the numbers after adding endpoints:

```bash
# Covered: introspect the wired endpoint classes (accessor <- client.py, metadata <- the class)
.venv/bin/python -c "import inspect, jamfpy.endpoints.clc_endpoints as c, jamfpy.endpoints.pro_scripts as s; \
print([(n,o._uri) for n,o in vars(c).items() if inspect.isclass(o) and getattr(o,'_uri',None)])"

# Pro resource groups (first path segment after the /v{n} prefix)
.venv/bin/python -c "import json,re,collections; d=json.load(open('api_schemas/pro.json')); \
g=sorted({(re.match(r'^/v\d+/([^/]+)', p) or re.match(r'^/([^/]+)', p)).group(1) for p in d['paths']}); \
print(len(g)); print(', '.join(g))"

# Classic resource groups (classic.json is not valid JSON — grep the path keys)
grep -oE '\"/[a-zA-Z][a-zA-Z0-9_-]*' api_schemas/classic.json | sed -E 's/^\"\///' | sort -u | grep -v '^JSSResource$'
```
