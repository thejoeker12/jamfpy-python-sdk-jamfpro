# Changelog

## [3.0.0](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/compare/v2.7.0...v3.0.0) (2026-10-20)


### ⚠ BREAKING CHANGES

* pro.dock_items.get_all is removed (the schema has no collection GET). ProEndpoint.get_all and the accounts users/groups get_all return a non-ok Response instead of raising. Tenant(parallelism=5) fans out get_all page fetches; set parallelism=1 for the old sequential behaviour. DockItems no longer subclasses ProEndpoint (it composes four capability mixins, so isinstance(x, ProEndpoint) is False for it). JamfAPIError is no longer importable from jamfpy.endpoints.models; import it from jamfpy.client.exceptions.
* jamfpy.new_logger is removed; use jamfpy.configure_logging(). Logger names are now jamfpy.{tenant}-auth / -pro / -clc under a jamfpy parent with a NullHandler, with no name padding. safe_mode=False now logs raw secrets (headers and bodies) rather than merely not redacting headers.
* Tenant() no longer raises on bad credentials or an unreachable FQDN; the first request (or Tenant.authenticate()) does. AUTH_REQUEST_TIMEOUT is removed; use Tenant(timeout=...). API.do()'s timeout default is None (the configured value) instead of 10. The auth-call timeout default moves from 20 s to the configured timeout (30 s by default). API requests now carry requests' default headers (Accept-Encoding, Accept: */*, Connection) plus User-Agent: jamfpy/<version>, where before every session default was stripped; endpoint-supplied accept/content-type still win.
* API requests are now TLS-verified (they were sent with verify=None before); tenants with a self-signed or internal CA must pass verify_path or set REQUESTS_CA_BUNDLE. Tenant.cert_path and Tenant.verify_path are str, not Path. utility.fix_jamf_time_to_iso and AccountChild.pass_response are removed. Auth no longer raises when the token buffer exceeds the token lifetime; it clamps and warns instead.
* requires-python is now >=3.13 (was >=3.10).
* Consolidated pro endpoints

### Features

* Consolidated pro endpoints ([6148a67](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/commit/6148a67b484b5fc52f3d8b3752acc1aaba2af840))
* COVERAGE.md generator (make coverage-doc) and CI drift check ([4010fb8](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/commit/4010fb8897162193b4177999128cfded16e6fb0f))
* endpoint capability mixins, parallel pagination and non-raising get_all ([d731429](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/commit/d73142958b1f41c7939bc51e02604df2777fffbb))
* endpoint scaffolder (make scaffold) ([01faea5](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/commit/01faea517947a3f58cbf6ba1cf015501c95c6c18))
* lazy auth, configurable timeout, thread-safe tokens, User-Agent ([72c7ed0](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/commit/72c7ed09ead30a7e33157bd2c6253282e7e290f3))
* logging hierarchy, configure_logging, JSON format and redaction ([a4a6a6b](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/commit/a4a6a6bbd33ba1350a1c42ebb30723f0d4a50aea))
* retries with backoff and request hooks ([b51457e](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/commit/b51457e2c6655deb5b3267e151a0159e898edce0))
* schema tooling, refreshed schemas and app-installers supplement ([afddd14](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/commit/afddd14225c5059d220ec8e0979ddfefa761e11a))


### Bug Fixes

* accept a bare host as the Tenant fqdn ([e9106c6](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/commit/e9106c6a2b30701bec438257e61e78cfedff8a69))
* Apache-2.0 license, PyPI build on 3.13, bare-host fqdn ([2eb1584](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/commit/2eb158466e6dfaa77e778d311077889f7918c2bd))
* TLS verification, invalidate URL, token buffer and other bugs ([4d15cd9](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/commit/4d15cd971b695cc3892934a553d482e9d4786e5c))
* Update required Python version to 3.10 ([#48](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/issues/48)) ([fa2da8b](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/commit/fa2da8b82c8c73737d0bdb32f3bd32ec518e2536))


### Documentation

* AGENTS.md for the license, publish build and bare-host fqdn ([c301aaa](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/commit/c301aaab5e27f350b7c0c65392b06d1be7a2bcdd))
* correct the current PyPI release (2.6.0) in README and AGENTS.md ([277be6d](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/commit/277be6d37001e767de82f879f6b18010f9064627))
* drop the hard-coded commit count from the round status ([6faf8a1](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/commit/6faf8a10df172111e78c0667bc8919224fbe802a))
* ENTRYPOINTS.md and AGENTS.md link ([65c377a](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/commit/65c377aed3e28f23b9483f23b75879f5c27ca388))
* fold the round handover and decision index into AGENTS.md ([fc42fe5](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/commit/fc42fe52654088e261eaae5bef4e227b8b22fdbc))
* merge ENTRYPOINTS.md into AGENTS.md ([f389830](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/commit/f389830438d2db4d7e5e215ca5595f6d12da63da))
* README and EXPANDING.md ([f2cafbd](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/commit/f2cafbdd92cd28e0d52f40892a11d4e84ba44ebb))
* review fixes for README, EXPANDING.md and AGENTS.md ([d2236f2](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/commit/d2236f2ea3d6afde23eaa1be5d19fb39057fe0cb))
* round status after the stack merged ([627709d](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/commit/627709da4f62df321dedddea839c21a367b0c21a))
* round status after the stack merged ([166f06b](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/commit/166f06b6e9b3111abdddbca02be88878b38b993b))
* round status and outstanding items in AGENTS.md ([0d2bc78](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/commit/0d2bc7833c690fc49061e0a033e5a134e7904727))
* say ENTRYPOINTS.md is merged into AGENTS.md and tidy/all has moved past [#66](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/issues/66) ([d1d841c](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/commit/d1d841cc9e3a884507d93e154cdadacd06f7abe4))
* the plan and rulings files are deleted from the owner's machine ([03b1fdf](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/commit/03b1fdf35f192b61ddcf579c506bfb9eeb412c4c))
* usage examples in examples/ ([c0e0266](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/commit/c0e02662f710f354ad158dfdfdafc991a4a48fc2))
* usage examples in examples/ ([824037d](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/commit/824037d10e096851614ae81f5be3c4201ca163b2))


### Miscellaneous Chores

* tooling: uv, Makefile, CI matrix, mypy, Python 3.13 floor ([6a30162](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/commit/6a301623ef8683c733859a60285a56937389b527))

## [2.7.0](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/compare/v2.6.0...v2.7.0) (2026-02-04)


### Features

* add MobileDevices endpoint and integrate into ClassicAPI ([#46](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/issues/46)) ([29470ce](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/commit/29470ce622c58f621ea94736c4def7196012c8b8))

## [2.6.0](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/compare/v2.5.0...v2.6.0) (2026-01-19)


### Features

* add get app installer  ([#44](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/issues/44)) ([d9882b1](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/commit/d9882b1c3722445f016b8b04f27ab81a718b2984))

## [2.5.0](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/compare/v2.4.2...v2.5.0) (2026-01-05)


### Features

* Add MobileDeviceGroups endpoint to client ([#42](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/issues/42)) ([290821b](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/commit/290821b6f565955717b89ac0fc0fa43b000fa0e6))

## [2.4.2](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/compare/v2.4.1...v2.4.2) (2025-12-03)


### Bug Fixes

* Fixing delete by id scripts ([#40](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/issues/40)) ([04c8618](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/commit/04c8618f1a0e8d14223f6b6e9f4c4b09c430ac75))

## [2.4.1](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/compare/v2.4.0...v2.4.1) (2025-11-18)


### Bug Fixes

* fixing cert_path logic to work correctly ([#38](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/issues/38)) ([603b583](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/commit/603b583e4a3128d6c5f6db76000b7b74bb137638))

## [2.4.0](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/compare/v2.3.0...v2.4.0) (2025-11-18)


### Features

* added restricted software ([6b87c7a](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/commit/6b87c7a730a6846e1f45cec5e0ae9884f939ef46))
* Adding cert and verify to http requests to allow passing certs ([#36](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/issues/36)) ([f45826e](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/commit/f45826ef7258d9855043f322d9d179f4120cf637))
* all the changes please ([cea8c88](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/commit/cea8c880e8e5615c15102cfe2a5e1d4b55b9634e))
* delete ([d0178d4](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/commit/d0178d4ba7ec826b465ba638666448985dacc7d0))
* implement pro app installers ([e0fb6a4](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/commit/e0fb6a435972104491bef86f55c5cdc1d8859ee1))


### Bug Fixes

* correct header ([eec1480](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/commit/eec1480c61404edb31ab1a11a23fcd6af174107c))
* data - ([3e6ebd7](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/commit/3e6ebd7dcf35314ac6cb1451f80fe568264c5dd8))
* Fixing Cert Path and Verify Path logic to ensure correct working with Path module ([#37](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/issues/37)) ([9b3d563](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/commit/9b3d563e5f1ef45b6d6b08e547e31ffe9b31dd1e))
* header key ([4640daf](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/commit/4640dafb674ee35a77eae08f6fed38e3c2f0a81b))
* url change ([d99f13a](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/commit/d99f13a4e9a4e3c9e28f24a893aa46276ab966b0))

## [2.3.0](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/compare/v2.2.5...v2.3.0) (2025-09-08)


### Features

* added back xml response optionally ([c5b1796](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/commit/c5b1796211fc0c359db3e3feb8e16cd85342d436))


### Bug Fixes

* appeasing pylint ([ccddea2](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/commit/ccddea210c9eac85bf48734fe1d14bdcbee882bf))
* datetime import ([4ac9b11](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/commit/4ac9b115c57ea2e05a602d9a4804a91da1fcbd68))
* undone the datetime thing it was bad ([011bf04](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/commit/011bf04b44c193bd148743abecc33e8e735c45a2))

## [2.2.5](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/compare/v2.2.4...v2.2.5) (2025-09-05)


### Bug Fixes

* the httpconfig thing ([4f1d31e](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/commit/4f1d31e8af294e19dcc1c446026900628b2bbe35))

## [2.2.4](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/compare/v2.2.3...v2.2.4) (2025-09-04)


### Bug Fixes

* various ([0149314](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/commit/0149314b494393038b1c89bb97fe8c4d418fa188))

## [2.2.3](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/compare/v2.2.2...v2.2.3) (2025-09-01)


### Bug Fixes

* docstring ([c06887a](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/commit/c06887a2b8c5a1a8bc4b4660f8caeefe450292b2))

## [2.2.2](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/compare/v2.2.1...v2.2.2) (2025-08-30)


### Bug Fixes

* multiple bug fixes, mainly the log output ([#26](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/issues/26)) ([fa86be5](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/commit/fa86be5a17a3b848cb26191ea4e6bcdb560ae550))

## [2.2.1](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/compare/v2.2.0-rc...v2.2.1) (2025-05-28)


### Bug Fixes

* add accounts, fix account child outputs, pyproject.toml conversion ([#23](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/issues/23)) ([989429b](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/commit/989429b4e4a886b9b6da3f55d30f7598407abd10))


### Miscellaneous Chores

* release 2.2.1 ([#25](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/issues/25)) ([b54c023](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/commit/b54c023e7e1c1e90fe22ded9a75b6df07ddad016))

## [2.2.0-rc](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/compare/v2.1.0-rc...v2.2.0-rc) (2025-05-27)


### Features

* Add accounts endpoint ([#20](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/issues/20)) ([8bcb823](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/commit/8bcb823e29aad9bbd5df14f2568da26402cd9ae0))
* pylint ([b110ad3](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/commit/b110ad39861edcb1eb6e217a6fd5dec092a215fb))
* release-please ([9c4eac5](https://github.com/thejoeker12/jamfpy-python-sdk-jamfpro/commit/9c4eac5763065c87d15c973c7995dccc59a15910))
