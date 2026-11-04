# Changelog

## v0.1.0 — 2026-11-03 (experimental)

- First packaged community tool based on a successfully reproduced Cyberpunk 2077 2.5 / Steam / Linux game-hash database rebuild.
- Reads the installed Steam depot manifest, builds missing file-hash records using Nexus's MultiHasher and validates new records against Steam SHA-1.
- Builds the archived Nexus Mods App reference database without modifying the AppImage.
- Validates the generated database, backs up Nexus's hash database and DataModel, installs a timestamped database, and includes rollback.
- Includes public-facing README, privacy/safety notes and troubleshooting guide.

**Verification disclosure:** The source workflow was successfully completed in one real installation. This newly consolidated/parameterized wrapper was statically checked and unit-tested, but not independently run end-to-end against a complete game installation before packaging.
