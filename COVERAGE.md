# API coverage

> **Generated file: do not edit by hand.** `make coverage-doc` (`tools/coverage_doc.py`) writes it from the wired
> endpoints, `api_schemas/` and the live specs; run it after adding or changing an endpoint or a live spec, and
> commit the result. `make coverage-doc-check` (part of `make check` and CI) fails while this file is stale.

Which Jamf Pro server resources this SDK wraps, and which it doesn't yet. Jamf exposes **two** HTTP APIs (see
[`AGENTS.md`](AGENTS.md)); this SDK wraps a subset of each.

**How to read this**

- The endpoints are every `Endpoint` attribute of `ClassicAPI` and `ProAPI`, composites' children included, as
  `tests/contract_test.py` discovers them. The schemas are `api_schemas/`, read through `tools/schemas.py`, with
  `pro-supplement.json`'s probed paths merged into Pro.
- A *resource* is one top-level path group, not an HTTP operation: a schema path's first segment, after the
  `/v{n}` prefix for Pro (`/v1/scripts/{id}` → `scripts`, `/v2/mdm/commands` → `mdm`; an unversioned Pro path
  such as `/preview/computers` → `preview`), and its first segment under `/JSSResource` for Classic
  (`/accounts/userid/{id}` → `accounts`). Every count below counts resources. A resource is *covered* when at
  least one wired endpoint's path is in it, however few of its paths and verbs that endpoint wraps.
- *Methods* are an endpoint's public methods (`name()` is left out); one that sends nothing is marked *(no
  request)*. *Sends to* is what the endpoint really sends, not what the schema lists for its path: the
  generator calls every method with dummy arguments under a stub that records each request instead of sending
  it, the way `tests/contract_test.py` does (both use `tools/introspect.py`), and lists each path some method
  sends to with the verbs sent there. `[options-probe]` marks a path that is only in `pro-supplement.json`, not
  in Jamf's published schema; *not in schema* marks a path, or the verbs, that the schema lacks (the contract
  test fails on those, so they should not appear).
- Jamf ships new resources continuously, so the totals move with each `make schemas`: treat them as an
  order-of-magnitude gauge.

---

## Summary

| API | Endpoints wired | Resources covered | Resources in schema | Rough coverage |
|---|--:|--:|--:|--:|
| **Classic** (`tenant.classic.*`) | 18 | 16 | 79 | ~20% |
| **Pro** (`tenant.pro.*`) | 4 | 4 | 125 | ~3% |

Pro's 125 resources include 1 whose paths are only in `pro-supplement.json` (`app-installers`): the tenant serves those paths, but Jamf's published schema leaves them out.

---

## Classic — covered (`tenant.classic.*`)

Classic write bodies are **XML strings**.

| SDK accessor | Path (`/JSSResource`) | Methods | Sends to |
|---|---|---|---|
| `classic.accounts` | `/accounts` | `get_all` | `/accounts` GET |
| `classic.accounts.groups` | `/accounts` | `create`, `delete_by_id`, `get_all`, `get_by_id`, `update_by_id` | `/accounts` GET; `/accounts/groupid/{id}` DELETE GET POST PUT |
| `classic.accounts.users` | `/accounts` | `create`, `delete_by_id`, `get_all`, `get_by_id`, `update_by_id` | `/accounts` GET; `/accounts/userid/{id}` DELETE GET POST PUT |
| `classic.buildings` | `/buildings` | `create`, `delete_by_id`, `get_all`, `get_by_id`, `update_by_id` | `/buildings` GET; `/buildings/id/{id}` DELETE GET POST PUT |
| `classic.categories` | `/categories` | `create`, `delete_by_id`, `get_all`, `get_by_id`, `update_by_id` | `/categories` GET; `/categories/id/{id}` DELETE GET POST PUT |
| `classic.computer_extension_attributes` | `/computerextensionattributes` | `create`, `delete_by_id`, `get_all`, `get_by_id`, `update_by_id` | `/computerextensionattributes` GET; `/computerextensionattributes/id/{id}` DELETE GET POST PUT |
| `classic.computer_groups` | `/computergroups` | `create`, `delete_by_id`, `get_all`, `get_by_id`, `update_by_id` | `/computergroups` GET; `/computergroups/id/{id}` DELETE GET POST PUT |
| `classic.computer_searches` | `/advancedcomputersearches` | `create`, `delete_by_id`, `get_all`, `get_by_id`, `update_by_id` | `/advancedcomputersearches` GET; `/advancedcomputersearches/id/{id}` DELETE GET POST PUT |
| `classic.computers` | `/computers` | `create`, `delete_by_id`, `get_all`, `get_by_id`, `update_by_id` | `/computers` GET; `/computers/id/{id}` DELETE GET POST PUT |
| `classic.configuration_profiles` | `/osxconfigurationprofiles` | `create`, `delete_by_id`, `get_all`, `get_by_id`, `update_by_id` | `/osxconfigurationprofiles` GET; `/osxconfigurationprofiles/id/{id}` DELETE GET POST PUT |
| `classic.departments` | `/departments` | `create`, `delete_by_id`, `get_all`, `get_by_id`, `update_by_id` | `/departments` GET; `/departments/id/{id}` DELETE GET POST PUT |
| `classic.mobile_device_groups` | `/mobiledevicegroups` | `create`, `delete_by_id`, `get_all`, `get_by_id`, `update_by_id` | `/mobiledevicegroups` GET; `/mobiledevicegroups/id/{id}` DELETE GET POST PUT |
| `classic.mobile_devices` | `/mobiledevices` | `create`, `delete_by_id`, `get_all`, `get_by_id`, `update_by_id` | `/mobiledevices` GET; `/mobiledevices/id/{id}` DELETE GET POST PUT |
| `classic.packages` | `/packages` | `create`, `delete_by_id`, `get_all`, `get_by_id`, `update_by_id` | `/packages` GET; `/packages/id/{id}` DELETE GET POST PUT |
| `classic.policies` | `/policies` | `create`, `delete_by_id`, `get_all`, `get_by_id`, `update_by_id` | `/policies` GET; `/policies/id/{id}` DELETE GET POST PUT |
| `classic.restricted_software` | `/restrictedsoftware` | `create`, `delete_by_id`, `get_all`, `get_by_id`, `update_by_id` | `/restrictedsoftware` GET; `/restrictedsoftware/id/{id}` DELETE GET POST PUT |
| `classic.scripts` | `/scripts` | `create`, `delete_by_id`, `get_all`, `get_by_id`, `update_by_id` | `/scripts` GET; `/scripts/id/{id}` DELETE GET POST PUT |
| `classic.sites` | `/sites` | `create`, `delete_by_id`, `get_all`, `get_by_id`, `update_by_id` | `/sites` GET; `/sites/id/{id}` DELETE GET POST PUT |

## Pro — covered (`tenant.pro.*`)

Pro bodies are **JSON dicts**; a Pro `get_all` paginates and aggregates every page into one response. *Version*
is the `/v{n}` of the paths the methods send to: *per method* when they hit different versions, *none* when
they send to no versioned path.

| SDK accessor | Path (`/api`) | Version | Methods | Sends to |
|---|---|---|---|---|
| `pro.app_installers` | `/v1/app-installers/deployments` | v1 | `create`, `delete_by_id`, `get_all`, `get_by_id`, `update_by_id` | `/v1/app-installers/deployments` GET POST [options-probe]; `/v1/app-installers/deployments/{id}` DELETE GET PUT [options-probe] |
| `pro.dock_items` | `/v1/dock-items` | v1 | `create`, `delete_by_id`, `get_by_id`, `update_by_id` | `/v1/dock-items` POST; `/v1/dock-items/{id}` DELETE GET PUT |
| `pro.mdm` | `/v2/mdm/commands` | v2 | `apply_redemption_code`, `certificate_list`, `clear_passcode`, `clear_restrictions_password`, `declerative_management`, `delete_user`, `device_information`, `device_location`, `disable_lost_mode`, `disable_remote_desktop`, `enable_lost_mode`, `enable_remote_desktop`, `erase_device`, `lock_device`, `log_out_user`, `managed_application_list`, `managed_media_list`, `play_lost_mode_sound`, `refresh_cellular_plans`, `request_mirroring`, `restart_device`, `security_info`, `send_command`, `set_auto_admin_password`, `set_recovery_lock`, `shut_down_device`, `stop_mirroring`, `unlock_user_account`, `validate_applications`, `validate_recovery_lock` | `/v2/mdm/commands` POST |
| `pro.scripts` | `/v1/scripts` | v1 | `create`, `delete_by_id`, `get_all`, `get_by_id`, `update_by_id` | `/v1/scripts` GET POST; `/v1/scripts/{id}` DELETE GET PUT |

---

## Live integration test coverage (min/max)

Which wired endpoints have live min/max lifecycle tests (`tests/integration/`: create with the required fields
only / with every writable field, then read → update → read → delete against a real tenant; see `AGENTS.md` →
*Quality gates*). A row with ✅/❌ comes from a spec in `SPECS` in `tests/integration/clc_resources_live_test.py`
or `pro_resources_live_test.py`: ✅ where the spec has that builder, ❌ where it has none or still has the
placeholder `make scaffold` writes; *Notes* is the spec's `notes`. An N/A row comes from the module's
`LIVE_NOT_COVERED`, with the reason the endpoint has no spec. Every wired endpoint has one or the other:
`make coverage-doc` refuses an endpoint with neither. Behaviour that is not per resource (lazy auth, parallel
pagination, hooks over a lifecycle, `close()` invalidating the token) is checked live in
`tests/integration/sdk_behaviour_live_test.py`, which is not in this table.

| SDK accessor | API | Min | Max | Notes |
|---|---|:-:|:-:|---|
| `classic.accounts` | Classic | N/A | N/A | Parent only exposes `get_all` (the whole `/accounts` payload); `users` and `groups` have specs |
| `classic.accounts.groups` | Classic | ✅ | ✅ | `privileges` sent, not echo-asserted |
| `classic.accounts.users` | Classic | ✅ | ✅ | Creates a real Custom, zero-privilege account; generated password, never echo-asserted |
| `classic.buildings` | Classic | ✅ | ✅ | Classic building is id + name only; address fields sent, not echo-asserted |
| `classic.categories` | Classic | ✅ | ✅ |  |
| `classic.computer_extension_attributes` | Classic | ✅ | ✅ | Text Field input type |
| `classic.computer_groups` | Classic | ✅ | ✅ | Min = static, max = smart; `criteria` sent, not echo-asserted |
| `classic.computer_searches` | Classic | ✅ | ✅ | `criteria`/`display_fields` sent, not echo-asserted |
| `classic.computers` | Classic | ✅ | ✅ | Fabricated inventory record |
| `classic.configuration_profiles` | Classic | ✅ | ✅ | Minimal plist; `payloads` sent, not echo-asserted; `level` sent as `System` (the server stores `computer` that way) |
| `classic.departments` | Classic | ✅ | ✅ | Name-only resource; min ≡ max |
| `classic.mobile_device_groups` | Classic | ✅ | ✅ | Min = static, max = smart; `criteria` sent, not echo-asserted |
| `classic.mobile_devices` | Classic | ✅ | ✅ | Fabricated udid/serial |
| `classic.packages` | Classic | ✅ | ✅ | Metadata only, no file upload |
| `classic.policies` | Classic | ✅ | ✅ | Created disabled, no scope |
| `classic.restricted_software` | Classic | ✅ | ✅ |  |
| `classic.scripts` | Classic | ✅ | ✅ | `filename` sent without `.sh` and `script_contents` without a trailing newline (server strips both) |
| `classic.sites` | Classic | ✅ | ✅ | Name-only resource; min ≡ max |
| `pro.app_installers` | Pro | ✅ | ❌ | No max: the body is in no published schema (`/v1/app-installers` is only in `pro-supplement.json`, which has no bodies), so its writable fields are unknown. Min sends the four fields a 400 on `{}` names as required (`name`, `appTitleId`, `deploymentType`, `updateBehavior`), with the first catalog title from `GET /v1/app-installers/titles` (the spec's `setup`), `SELF_SERVICE` / `MANUAL`, and `enabled: false` so nothing reaches a device. Best-effort: the resource is undocumented, so `get_all`'s pagination and the body shapes are unverified beyond this lifecycle, which does not call `get_all`. |
| `pro.dock_items` | Pro | ✅ | ✅ | All fields required; min ≡ max |
| `pro.mdm` | Pro | N/A | N/A | Verb endpoint (send-command) with no CRUD surface to lifecycle-test |
| `pro.scripts` | Pro | ✅ | ✅ | categoryId/categoryName omitted (instance-state dependent) |

---

## Not yet covered

Resources in the schemas that no wired endpoint's path is in. Adding any of these follows `AGENTS.md` → *How to
add an endpoint* (start with `make scaffold`).

### Classic (63)

```
activationcode, advancedmobiledevicesearches, advancedusersearches, allowedfileextensions, classes,
commandflush, computerapplications, computerapplicationusage, computercheckin, computercommands,
computerhardwaresoftwarereports, computerhistory, computerinventorycollection, computerinvitations,
computermanagement, computerreports, directorybindings, diskencryptionconfigurations,
distributionpoints, dockitems, ebooks, fileuploads, gsxconnection, healthcarelistener,
healthcarelistenerrule, ibeacons, infrastructuremanager, jsonwebtokenconfigurations, jssuser,
ldapservers, licensedsoftware, logflush, macapplications, mobiledeviceapplications,
mobiledevicecommands, mobiledeviceconfigurationprofiles, mobiledeviceenrollmentprofiles,
mobiledeviceextensionattributes, mobiledevicehistory, mobiledeviceinvitations,
mobiledeviceprovisioningprofiles, networksegments, patchavailabletitles, patches,
patchexternalsources, patchinternalsources, patchpolicies, patchreports, patchsoftwaretitles,
peripherals, peripheraltypes, printers, removablemacaddresses, savedsearches, smtpserver,
softwareupdateservers, userextensionattributes, usergroups, users, vppaccounts, vppassignments,
vppinvitations, webhooks
```

### Pro (121)

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
enrollment-customizations, environment-type, groups, gsx-connection, health-check, health-status,
icon, impact-alert-notification-settings, inventory-information, inventory-preload, jamf-connect,
jamf-management-framework, jamf-package, jamf-pro-information, jamf-pro-server-url,
jamf-pro-version, jamf-protect, jamf-remote-assist, jcds, last-login, ldap, ldap-keystore,
local-admin-password, locales, log-flushing, login-customization, m2m,
macos-managed-software-updates, managed-software-updates, mdm-renewal, mobile-device-apps,
mobile-device-enrollment-profile, mobile-device-extension-attributes, mobile-device-groups,
mobile-device-prestages, mobile-devices, notifications, oauth, oauth2, oidc, onboarding, packages,
parent-app, patch-management-accept-disclaimer, patch-policies, patch-software-title-configurations,
pki, policy-properties, preview, reenrollment, return-to-service, scheduler, self-service,
self-service-plus, service-discovery-enrollment, settings, sites, slasa, smart-computer-groups,
smart-mobile-device-groups, smart-user-groups, smtp-server, sso, startup-status, static-user-groups,
supervision-identities, system, teacher-app, time-zones, user, user-sessions, users,
volume-purchasing-locations, volume-purchasing-subscriptions
```
