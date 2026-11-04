# Cyberpunk 2077 × Nexus Mods App — Linux Hash Fix

**Community workaround for the archived Nexus Mods App when a Cyberpunk 2077 Steam update shows `Version: Unknown` or triggers a giant game-file backup attempt.**

> **Status:** Experimental community utility, v0.1.0. The underlying method was confirmed working on one Linux system with **Cyberpunk 2077 2.5, Steam build `26161058`, depot `1091501`, manifest `3524634124112875626`** (November 2026). This newly packaged, generalized wrapper has **not yet had a separate end-to-end field test**. Please [report results](.github/ISSUE_TEMPLATE/bug_report.md) before recommending it as universally compatible.
>
> **Unofficial:** Not affiliated with CD PROJEKT RED, Valve, Nexus Mods, or SteamKit2.

## The problem

After Cyberpunk updates, the discontinued Nexus Mods App for Linux can be unable to identify the current Steam depot's original files. You may see:

- **Cyberpunk 2077 → Version: Unknown** in **My Games**.
- **`Cannot backup N files with total size ... GB, which exceeds maximum of 5 GB`** when applying mods.
- A mod loadout that can no longer deploy despite valid files on disk.

Nexus uses a **reference database of official game-file content hashes** to tell original Steam files apart from external modifications. Its reference database stopped receiving updates when the app was discontinued, so newer game versions may be unknown.

**This tool does not disable the 5 GB backup safety guard.** It recreates a reference database with the current installed Steam manifest, computing missing records only after checking each file against Steam's official SHA-1. It then installs the resulting database alongside Nexus's old one, after backing up Nexus's existing database and DataModel outside the app's automatic cleanup area.

### What this fixes—and what it doesn't

| Problem | Covered? |
| --- | --- |
| Unknown **Steam** Cyberpunk game version | **Yes**, if the cached depot manifest and local game files are available/valid |
| 5 GB backup error caused by missing official file hashes | **May fix**; the tested installation deployed successfully |
| An outdated **RED4ext / CET / redscript / Mod Settings** mod | **No**; update the mod itself |
| Game crashing with `mod_settings` in the Proton backtrace | **No**; update/remove incompatible Mod Settings |
| Phantom Liberty's separate depot, GOG, Epic, Windows | **Not supported/tested** |

## Requirements

- Linux, x86-64, an existing **Nexus Mods App** installation, and Cyberpunk 2077 installed through **Steam**.
- Local Steam `appmanifest_1091500.acf` (in the relevant Steam library's `steamapps` directory).
- The cached **unencrypted** Steam depot manifest (`1091501_<manifest-id>.manifest`). Flatpak Steam is supported.
- The game's official files must match the Steam manifest. If a required file was modified, the builder **stops**, rather than pretending the modified file is original.
- Python **3.10+**, Git, a .NET **10 SDK**, internet access for cloning GitHub source and restoring NuGet dependencies.
- Free space for the app source, archived hash repo, a working dataset, generated database and backups. The tool **does not copy 66 GB of game archives**, but may read that much data to hash it.
- Close the Nexus Mods App before `install` or `rollback`.

The original application and game-hashes repositories are GPL-3.0 licensed and archived. This repository **does not bundle** their code, binaries, generated hash database, game content, or mod archives. Instead, it fetches the original public repositories as build dependencies.

## Quick start

First, get this repository onto your computer (clone it after publication, or extract the ZIP release).

```bash
cd cyberpunk-nexus-app-hashfix
chmod +x cyberpunk-hashfix
```

Find the Steam library holding Cyberpunk. This is the directory containing `appmanifest_1091500.acf`, **not** the game's `Cyberpunk 2077` directory.

```bash
# 1) Prepare hashes and compile a database. Use your ACTUAL game version.
./cyberpunk-hashfix build \
  --steamapps "/path/to/SteamLibrary/steamapps" \
  --version 2.5

# 2) Validate the output without changing Nexus.
./cyberpunk-hashfix check

# 3) Completely close Nexus Mods App, then install (prompts for confirmation).
./cyberpunk-hashfix install
```

In Nexus Mods App, open **My Games → Cyberpunk 2077**. Check that the expected game version appears and that your installed mod loadout is intact. Only then attempt applying updated mods.

**Steam Flatpak example:** If your library is `/media/YOUR_USER/Games/SteamLibrary`, pass `/media/YOUR_USER/Games/SteamLibrary/steamapps`. The tool automatically checks Flatpak's usual depotcache path under `~/.var/app/com.valvesoftware.Steam/.local/share/Steam/depotcache`.

If the manifest is cached somewhere nonstandard, use `--cache`:

```bash
./cyberpunk-hashfix build --steamapps "/path/to/steamapps" \
  --version 2.5 \
  --cache "/path/to/Steam/depotcache"
```

**Do not lie about the version number:** `--version` is only a label for the actual installed build. It is *not* an update/downgrade command and does *not* verify version naming against CDPR's release history.

## Rollback

If Nexus doesn't start, doesn't recognize the database, or develops new problems, **close the app completely**, then:

```bash
./cyberpunk-hashfix rollback
```

The last pre-install backup is found automatically. You can also choose an earlier one:

```bash
./cyberpunk-hashfix rollback --backup "/path/to/.work/backups/nexus-before-hashfix-..."
```

Rollback **restores only `FileHashesDatabase`**, not the app's `DataModel`, so it won't silently undo your recent loadout changes. A protected DataModel copy is available under the same backup folder for manual recovery if necessary. The currently installed database is moved aside rather than deleted.

### Where the files go

All downloaded sources and generated files stay within the local, Git-ignored `.work/` directory:

```text
.work/
  NexusMods.App/           original archived application source (Git clone)
  game-hashes/             original archived reference data (Git clone)
  HashProbe/              compiled local verification tool
  runs/<build>-<manifest>/
    dataset/               isolated copies + newly verified hash records
    output/                game_hashes_db.zip and manifest.json
    verification.log
    build.log
    run.json
  backups/                 pre-install database and DataModel backups
```

The installer places the compiled RocksDB hash database into a new timestamped folder under `~/.local/share/NexusMods.App/FileHashesDatabase/`. Nexus chooses the latest database at startup. Because Nexus may delete older database folders automatically, the tool **backs up the original outside that location** first.

## How it works

1. Read Steam's *installed* `buildid` and depot manifest ID from `appmanifest_1091500.acf`.
2. Load Steam's locally cached, unencrypted depot manifest using **SteamKit2 3.5.0**.
3. Clone the archived `NexusMods.App` and `game-hashes` repositories into `.work/`.
4. Copy the original hash dataset into a build-only staging directory.
5. For Steam SHA-1 values missing from the dataset, compute hashes using **Nexus's own `MultiHasher`** and verify that the file's SHA-1 equals Steam's manifest SHA-1 before adding it. (Existing reference hashes are trusted from the archived dataset.)
6. Export the Steam manifest into the format accepted by Nexus's database builder; add an explicit Cyberpunk Windows/Steam version alias.
7. Build using the original app's `game-hashes-db build` command. If its cached `games.json` contains duplicate domain mappings, normalize **only the cloned source's build cache**, preserving the original in a `.before-hashfix` file.
8. Validate the generated ZIP, release manifest, builder output and version mapping; back up Nexus's installed database; install a new timestamped copy.

The tool does **not** connect to your Steam account, access credentials, download game archives, modify the game's files, or remove the 5 GB safety guard.

## Updating after another Cyberpunk patch

1. Let Steam update Cyberpunk. Check that the correct depot manifest exists in your Steam cache.
2. Determine the actual game version from the patch notes.
3. Run `build --steamapps ... --version NEW_VERSION`, followed by `check` and `install`.
4. If you rebuild the same Steam build, use `build --rerun` to preserve the old build output and start a fresh run.

**Caveat:** Future game updates may change Steam depot structure, the game's official files, or the modding frameworks. This workflow is designed to *try* newer builds, not guaranteed to work indefinitely. The current release only targets Cyberpunk's **base Steam app/depot**.

## Troubleshooting

See [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) for common failures. If you get a `C0000005` game crash **after Nexus successfully applies mods**, that is a separate mod-compatibility issue: check the Proton backtrace for plugin names and update the offending mod. **In our original case, `mod_settings` was the remaining culprit.**

## Security and privacy

- **Review scripts before running.** This is a community utility with local filesystem write access to the Nexus database during `install` and `rollback`.
- **No `curl | bash`, no root/sudo, no automatic upload, no game-file redistribution.** The script calls `git clone` for the archived source and restores build dependencies from NuGet.
- The `build` and `check` commands do not write to the installed game, Steam client, or Nexus's live database.
- The `install` command asks for confirmation, preserves recovery backups, and never edits the executable AppImage.
- The Git-ignored `.work/` folder may contain **your local paths, logs, backup data and identifiers**. **Never commit or upload `.work/`.**
- Nexus's app source has an older dependency tree and may emit security advisory warnings during the build; run only in an environment you trust.

## Contributing and publishing

Issues, code review and reproducibility reports are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md). If you are the repository owner, see [docs/PUBLISHING.md](docs/PUBLISHING.md). This repo is **GPL-3.0-or-later** (see [LICENSE](LICENSE)) and remains unofficial.

### Credits

This project builds on the open-source work of [Nexus Mods App](https://github.com/Nexus-Mods/NexusMods.App), [Nexus game-hashes](https://github.com/Nexus-Mods/game-hashes), and [SteamKit2](https://github.com/SteamRE/SteamKit). Thanks to their original authors and maintainers.
