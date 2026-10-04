# Changelog

## [0.3.0](https://github.com/LycheeHome/palsave-api/compare/v0.2.0...v0.3.0) (2026-10-04)


### Features

* publish a container image ([afea1f0](https://github.com/LycheeHome/palsave-api/commit/afea1f0a0fe34f7861313540d6cdda6fdaa7e404))
* publish a container image ([0e30316](https://github.com/LycheeHome/palsave-api/commit/0e303167c39c43f30dfe6a5a79e7dc37c8f7ad42))


### Bug Fixes

* gate the image publish on tests, and give the image a HEALTHCHECK ([f8a79b5](https://github.com/LycheeHome/palsave-api/commit/f8a79b5fd096af13eebd783cffef37cb32c71b34))
* give the image a state directory the service user owns ([4b495f6](https://github.com/LycheeHome/palsave-api/commit/4b495f617a5fb1d2008105df9cb0f29e70d1465f))
* keep image tests out of the deploy-gating test job ([ab44abd](https://github.com/LycheeHome/palsave-api/commit/ab44abdc9a2a2af1a0bda2a49c4872cb32d0faf2))
* let the container bind beyond its own loopback ([059222f](https://github.com/LycheeHome/palsave-api/commit/059222fd2a2eb2f058db48dbea6d96fb7eeab24a))

## [0.2.0](https://github.com/LycheeHome/palsave-api/compare/v0.1.0...v0.2.0) (2026-10-01)


### Features

* configurable Oodle library path, CI, and release tooling ([a3f6f73](https://github.com/LycheeHome/palsave-api/commit/a3f6f73c347512223aef392f81e17bfc63cd9958))
* the Oodle library path comes from configuration ([53e9236](https://github.com/LycheeHome/palsave-api/commit/53e923643a6ec61465164f7bc2df290fafdc685d))


### Bug Fixes

* new-but-unowned wild pal spawns were misreported as acquisitions ([6f9547a](https://github.com/LycheeHome/palsave-api/commit/6f9547a3234eb0850b2b344081a9decdd28b95cc))
