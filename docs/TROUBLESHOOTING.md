# Troubleshooting

**Read the failure message before changing your game.** Most problems can be diagnosed from `.work/runs/<build>-<manifest>/` logs.

## `Version: Unknown` even after installation

Close and reopen Nexus. Run `./cyberpunk-hashfix check`; confirm the app's `~/.local/share/NexusMods.App/FileHashesDatabase/` folder contains a new timestamped database. Check the app logs under `~/.local/state/NexusMods.App/Logs/`. The app may use a different XDG data directory; in that case pass `--appdata /actual/NexusMods.App` **before** the subcommand, e.g. `./cyberpunk-hashfix --appdata /path install`.

## `Cannot backup ... exceeds maximum of 5 GB`

The database may still be missing files, the installed game may differ from the Steam manifest, or another independently modified game file may be present. Do not disable the limit or delete `archive/pc/content` files. Re-check your original Steam depot and Nexus version. Compare your app log with the current build log.

## `Steam file size mismatch` / `Steam SHA-1 MISMATCH`

The local file is not identical to the official Steam manifest. **The tool stops intentionally.** Back up manually modified files/mods as appropriate; consider Steam's Verify integrity only after understanding that it can replace modded game files. Restart the build with `--rerun` after resolving the file mismatch.

## `Cannot find cached depot manifest`

The tool only uses the locally cached `1091501_<manifest>.manifest` file. Locate Steam's `depotcache` and pass it with `--cache`. You do not need to download the entire game again merely because this utility can't find the cache.

## `.NET` compiler warnings or missing SMAPI submodule

The original app has an old, complex .NET dependency tree. Warnings like `GenerateWeaveSources`, `NU1902` and obsolete APIs can appear while compiling. **A warning is not automatically a failure.** The script initializes Git submodules to prevent `Missing SMAPI submodule!`.

If the app build fails, check `app-build.log`. If it builds but the CLI fails at the assertion `gameIdToDomain.Count == gameDomainToId.Count`, inspect whether the cloned app's `obj/games.json` is available and normalized. The script tries to normalize it after compiling. No live AppImage metadata is changed.

## Mod Settings / RED4ext crashes after the hash fix

**A correct hash database does not make outdated mods compatible with Cyberpunk.** If Proton reports an access violation and the backtrace includes `mod_settings`, update Mod Settings for your game version. Similarly, update RED4ext, ArchiveXL, Codeware, redscript, TweakXL, CET and other native/script frameworks as needed.

## Rollback

Close Nexus and run `./cyberpunk-hashfix rollback`. If its last-install pointer has been lost, pass `--backup` pointing to a preserved folder inside `.work/backups/`. The previous database is restored; DataModel is deliberately not overwritten automatically.

## Reporting a reproducible bug

Include OS, Nexus Mods App version, Steam build ID, depot manifest ID, command, exit code, and the smallest relevant log excerpt. **Remove home paths, usernames, tokens, account identifiers, and private mod lists if you do not want to share them.** Do not upload your database backups or game files.
