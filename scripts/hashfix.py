#!/usr/bin/env python3
"""Community helper for local Cyberpunk 2077 Steam hashes in archived Nexus Mods App.

SPDX-License-Identifier: GPL-3.0-or-later
No game content, credentials, or ready-made game hash DBs are bundled.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
import zipfile
from pathlib import Path

APP_ID = 1091500
DEPOT_ID = 1091501
REPOS = {
    "NexusMods.App": "https://github.com/Nexus-Mods/NexusMods.App.git",
    "game-hashes": "https://github.com/Nexus-Mods/game-hashes.git",
}
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WORK = ROOT / ".work"
DEFAULT_APPDATA = Path.home() / ".local/share/NexusMods.App"


class Fail(Exception):
    pass


def require_file(path: Path, title: str = "File") -> Path:
    if not path.is_file():
        raise Fail(f"{title} not found: {path}")
    return path


def require_command(name: str) -> None:
    if not shutil.which(name):
        raise Fail(f"Required command not found: {name}")


def run(args: list[str], *, cwd: Path | None = None, log: Path | None = None,
        env: dict[str, str] | None = None) -> None:
    print("+", " ".join(args), flush=True)
    if log:
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("w", encoding="utf-8") as out:
            process = subprocess.Popen(args, cwd=cwd, env=env, stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT, text=True, errors="replace")
            assert process.stdout
            for line in process.stdout:
                print(line, end="")
                out.write(line)
            status = process.wait()
    else:
        status = subprocess.call(args, cwd=cwd, env=env)
    if status:
        raise Fail(f"Command exited with status {status}: {args[0]}; see {log or 'terminal output'}")


def depot_from_acf(path: Path) -> tuple[int, int]:
    """Read the InstalledDepots entry in the local Steam appmanifest, not SteamDB."""
    source = require_file(path, "Steam appmanifest").read_text(errors="replace")
    build = re.search(r'"buildid"\s*"(\d+)"', source, flags=re.I)
    installed_depots = source.find('"InstalledDepots"')
    if installed_depots < 0:
        raise Fail(f"InstalledDepots not present in {path}")
    depot = re.search(r'"1091501"\s*\{\s*"manifest"\s*"(\d+)"',
                      source[installed_depots:], flags=re.I)
    if not build or not depot:
        raise Fail(f"Could not read build/depot manifest IDs from {path}")
    return int(build.group(1)), int(depot.group(1))


def locate_cached_manifest(manifest_id: int, cache_arg: str | None) -> Path:
    if cache_arg:
        base = Path(cache_arg).expanduser().resolve()
        if base.is_file():
            return require_file(base, "Cached Steam depot manifest")
        candidates = [base / f"{DEPOT_ID}_{manifest_id}.manifest"]
    else:
        candidates = [
            Path.home() / ".var/app/com.valvesoftware.Steam/.local/share/Steam/depotcache" /
            f"{DEPOT_ID}_{manifest_id}.manifest",
            Path.home() / ".local/share/Steam/depotcache" / f"{DEPOT_ID}_{manifest_id}.manifest",
            Path.home() / ".steam/steam/depotcache" / f"{DEPOT_ID}_{manifest_id}.manifest",
        ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise Fail(f"Cannot find cached depot manifest {DEPOT_ID}_{manifest_id}.manifest. "
               "Pass --cache /path/to/depotcache or ensure Steam downloaded this build.")


def clone_if_needed(work: Path, name: str) -> Path:
    target = work / name
    if (target / ".git").is_dir():
        print(f"Using existing source checkout: {target}")
        return target
    if target.exists():
        raise Fail(f"Source path exists but is not a Git clone: {target}")
    run(["git", "clone", "--depth", "1", REPOS[name], str(target)])
    return target


def normalize_games_json(path: Path) -> None:
    """Fix duplicate game domains only inside this project's source-build cache.

    Nexus's old code asserts both maps have equal cardinality. We preserve the
    first mapping for each ID AND domain; we fail rather than losing Cyberpunk.
    """
    if not path.is_file():
        print("Note: games.json cache not present; no local mapping normalization required.")
        return
    data = json.loads(path.read_text())
    if not isinstance(data, list) or not all(isinstance(x, dict) and
         isinstance(x.get("id"), int) and isinstance(x.get("domain_name"), str) for x in data):
        raise Fail(f"Unexpected games.json schema; refusing to modify: {path}")
    unique_ids = {x["id"] for x in data}
    unique_domains = {x["domain_name"] for x in data}
    if len(unique_ids) == len(unique_domains) == len(data):
        print("Cached Nexus game mappings are already one-to-one.")
        return
    clean, seen_ids, seen_domains = [], set(), set()
    for row in data:
        if row["id"] in seen_ids or row["domain_name"] in seen_domains:
            continue
        seen_ids.add(row["id"])
        seen_domains.add(row["domain_name"])
        clean.append(row)
    if not any(x["id"] == 3333 and x["domain_name"] == "cyberpunk2077" for x in clean):
        raise Fail("Cyberpunk mapping (3333/cyberpunk2077) not preserved. Refusing to modify JSON.")
    backup = path.with_name(path.name + ".before-hashfix")
    if not backup.exists():
        shutil.copy2(path, backup)
    path.write_text(json.dumps(clean, separators=(",", ":")))
    print(f"Normalized local build cache: {len(data)} -> {len(clean)} mappings; original: {backup}")


def insert_version_alias(alias_file: Path, version: str, manifest_id: int) -> None:
    """Update only the isolated copy of version_aliases.yaml."""
    content = require_file(alias_file).read_text()
    anchor = "Cyberpunk 2077:\n  Windows:\n"
    if content.count(anchor) != 1:
        raise Fail(f"Unexpected version_aliases.yaml structure in {alias_file}; nothing changed")
    if re.search(rf"(?m)^\s*- {manifest_id}\s*$", content):
        raise Fail("This manifest already occurs in upstream aliases; refusing to relabel it blindly.")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+()-]{0,40}", version):
        raise Fail("Version label must be 1–41 characters: letters, numbers, . _ + ( ) -")
    insertion = f"    - Name: {version}\n      Steam:\n        - {manifest_id}\n"
    alias_file.write_text(content.replace(anchor, anchor + insertion, 1))
    print(f"Added Cyberpunk Windows Steam version alias: {version} -> {manifest_id}")


def zip_entries_safe(archive: zipfile.ZipFile) -> list[str]:
    names = []
    for item in archive.infolist():
        p = Path(item.filename)
        # Zip paths always use '/', regardless of platform.
        if item.filename.startswith("/") or "\\" in item.filename or ".." in p.parts or \
                not item.filename or (item.external_attr >> 16) & 0o170000 == 0o120000:
            raise Fail(f"Unsafe ZIP entry: {item.filename}")
        if not item.is_dir():
            names.append(item.filename)
    return names


def verify_output(run_dir: Path) -> dict:
    meta = json.loads(require_file(run_dir / "run.json", "Run metadata").read_text())
    out = run_dir / "output"
    artifact = require_file(out / "game_hashes_db.zip", "Generated database ZIP")
    release = json.loads(require_file(out / "manifest.json", "Generated release manifest").read_text())
    assets = [a for a in release.get("assets", []) if a.get("type") == "game_hash_db"]
    if len(assets) != 1 or int(assets[0].get("size", -1)) != artifact.stat().st_size:
        raise Fail("Release manifest does not match ZIP size")
    stem = str(meta["manifest_id"])
    dataset = run_dir / "dataset"
    steam_record = json.loads(require_file(dataset / "json/stores/steam/manifests" / f"{stem}.json").read_text())
    if int(steam_record["ManifestId"]) != int(meta["manifest_id"]) or \
            int(steam_record["DepotId"]) != DEPOT_ID or not steam_record.get("Files"):
        raise Fail("Exported Steam manifest has invalid identifiers or no files")
    alias_file = require_file(dataset / "contrib/version_aliases.yaml")
    expected_alias = f"    - Name: {meta['version']}\n      Steam:\n        - {stem}\n"
    if expected_alias not in alias_file.read_text():
        raise Fail("Game version mapping missing from rebuilt source dataset")
    log = require_file(run_dir / "build.log", "Database build log").read_text(errors="replace")
    if "Database built and exported to" not in log or \
            f"Failed to anchor Steam manifest {stem}" in log or f"Skipping Manifest {stem}" in log:
        raise Fail("Builder skipped current Steam manifest or did not report successful export")
    with zipfile.ZipFile(artifact) as archive:
        names = zip_entries_safe(archive)
        if not {"CURRENT"}.issubset(names) or not any(x.startswith("MANIFEST-") for x in names):
            raise Fail("Export ZIP does not contain a recognizable RocksDB database root")
        bad = archive.testzip()
        if bad:
            raise Fail(f"ZIP checksum failed for {bad}")
    print(f"Validated {meta['version']} / Steam build {meta['build_id']} / manifest {meta['manifest_id']}")
    print(f"Database ZIP: {artifact} ({artifact.stat().st_size:,} bytes)")
    return meta


def latest_run(work: Path) -> Path:
    last = require_file(work / "last-built.json", "Latest-build pointer")
    data = json.loads(last.read_text())
    value = Path(data["run_dir"]).resolve()
    if not value.is_dir() or not value.is_relative_to((work / "runs").resolve()):
        raise Fail("Latest build pointer does not point inside this work directory")
    return value


def build(args: argparse.Namespace) -> None:
    for tool in ("git", "dotnet"):
        require_command(tool)
    steamapps = Path(args.steamapps).expanduser().resolve()
    if not steamapps.is_dir():
        raise Fail(f"SteamLibrary/steamapps directory does not exist: {steamapps}")
    build_id, manifest_id = depot_from_acf(steamapps / f"appmanifest_{APP_ID}.acf")
    game = steamapps / "common/Cyberpunk 2077"
    if not game.is_dir():
        raise Fail(f"Cannot find Cyberpunk 2077 game directory: {game}")
    manifest = locate_cached_manifest(manifest_id, args.cache)
    work = Path(args.work).expanduser().resolve()
    work.mkdir(parents=True, exist_ok=True)
    print(f"Steam build: {build_id}; depot {DEPOT_ID} manifest {manifest_id}; version label: {args.version}")
    print(f"Game directory: {game}\nCached official manifest: {manifest}")
    print("No game files will be written by this build command.")

    nexus = clone_if_needed(work, "NexusMods.App")
    hashes = clone_if_needed(work, "game-hashes")
    run(["git", "submodule", "update", "--init", "--recursive"], cwd=nexus)

    runs = work / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    run_dir = runs / f"{build_id}-{manifest_id}"
    if run_dir.exists():
        if not args.rerun:
            raise Fail(f"Existing build run: {run_dir}. Pass --rerun to archive it and start again.")
        archived = runs / f"{run_dir.name}.previous-{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%d%H%M%S')}"
        if archived.exists():
            raise Fail(f"Archive path already exists: {archived}")
        run_dir.rename(archived)
        print(f"Previous run preserved: {archived}")
    run_dir.mkdir()
    dataset = run_dir / "dataset"
    dataset.mkdir()
    shutil.copytree(hashes / "json", dataset / "json")
    shutil.copytree(hashes / "contrib", dataset / "contrib")

    # Build a throwaway project; all project references point to our local source clone.
    probe = work / "HashProbe"
    probe.mkdir(exist_ok=True)
    shutil.copy2(ROOT / "src/HashProbe/Program.cs", probe / "Program.cs")
    shutil.copy2(ROOT / "src/HashProbe/HashProbe.csproj", probe / "HashProbe.csproj")
    run(["dotnet", "build", str(probe / "HashProbe.csproj"), "--verbosity", "quiet", "-p:WarningLevel=0"],
        log=run_dir / "probe-build.log")
    run(["dotnet", "run", "--project", str(probe / "HashProbe.csproj"),
         "--no-build", "--no-restore", "--", str(manifest), str(game),
         str(dataset), str(APP_ID), str(DEPOT_ID), str(manifest_id)], log=run_dir / "verification.log")
    insert_version_alias(dataset / "contrib/version_aliases.yaml", args.version, manifest_id)

    app_project = nexus / "src/NexusMods.App/NexusMods.App.csproj"
    run(["dotnet", "build", str(app_project), "--verbosity", "quiet", "-p:WarningLevel=0"],
        log=run_dir / "app-build.log")
    normalize_games_json(nexus / "src/NexusMods.Networking.NexusWebApi/obj/games.json")

    output = run_dir / "output"
    output.mkdir()
    env = dict(os.environ)
    env["DOTNET_ROLL_FORWARD"] = "Major"
    run(["dotnet", "run", "--project", str(app_project), "--no-build", "--",
         "as-main", "game-hashes-db", "build", "-p", str(dataset), "-o", str(output)],
        log=run_dir / "build.log", env=env)
    metadata = {
        "app_id": APP_ID, "depot_id": DEPOT_ID, "build_id": build_id,
        "manifest_id": manifest_id, "version": args.version,
        "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    (run_dir / "run.json").write_text(json.dumps(metadata, indent=2) + "\n")
    verify_output(run_dir)
    (work / "last-built.json").write_text(json.dumps({"run_dir": str(run_dir)}, indent=2) + "\n")
    print("\nBUILD SUCCEEDED. Next: ./cyberpunk-hashfix check ; ./cyberpunk-hashfix install")


def validate_appdata(appdata: Path) -> Path:
    if appdata.is_symlink() or not appdata.is_dir():
        raise Fail(f"Nexus data directory must exist and not be a symlink: {appdata}")
    dbroot = appdata / "FileHashesDatabase"
    if dbroot.is_symlink() or not dbroot.is_dir():
        raise Fail(f"Live Nexus hash database folder missing or symlinked: {dbroot}")
    return dbroot


def install(args: argparse.Namespace) -> None:
    work = Path(args.work).expanduser().resolve()
    run_dir = latest_run(work)
    meta = verify_output(run_dir)
    appdata = Path(args.appdata).expanduser().resolve()
    dbroot = validate_appdata(appdata)
    print("\nSTOP: Close the Nexus Mods App completely before installation.")
    if not args.yes:
        answer = input("Type INSTALL after closing Nexus Mods App: ")
        if answer != "INSTALL":
            raise Fail("Cancelled by user")
    backups = work / "backups"
    backups.mkdir(parents=True, exist_ok=True)
    backup = Path(tempfile.mkdtemp(prefix="nexus-before-hashfix-", dir=backups))
    print(f"Backing up current Nexus DB outside of its auto-cleanup directory: {backup}")
    shutil.copytree(dbroot, backup / "FileHashesDatabase", symlinks=True)
    if (appdata / "DataModel").is_dir():
        shutil.copytree(appdata / "DataModel", backup / "DataModel", symlinks=True)
    existing_stamps = []
    for folder in dbroot.iterdir():
        if folder.is_dir() and re.fullmatch(r"[0-9a-fA-F-]{36}_[0-9]+", folder.name):
            existing_stamps.append(int(folder.name.rsplit("_", 1)[1]))
    now = int(time.time())
    highest = max(existing_stamps, default=0)
    if highest > now + 300:
        raise Fail(f"Future-dated Nexus DB folder found; backup preserved in {backup}, no install performed")
    stamp = max(now, highest + 1)
    folder_name = f"{uuid.uuid4()}_{stamp}"
    final = dbroot / folder_name
    temporary = dbroot / (folder_name + "_tmp")
    if final.exists() or temporary.exists():
        raise Fail("New database destination already exists, refusing to overwrite")
    temporary.mkdir()
    try:
        with zipfile.ZipFile(run_dir / "output/game_hashes_db.zip") as archive:
            zip_entries_safe(archive)
            archive.extractall(temporary)
        temporary.rename(final)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    summary = {"custom_database": str(final), "backup": str(backup),
               "version": meta["version"], "build_id": meta["build_id"],
               "installed_utc": dt.datetime.now(dt.timezone.utc).isoformat()}
    (backup / "installation.json").write_text(json.dumps(summary, indent=2) + "\n")
    (work / "last-install.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(f"\nINSTALLED: {final}\nBACKUP: {backup}")
    print("Start Nexus and confirm Cyberpunk's version. Do NOT apply mods until its loadout looks correct.")


def rollback(args: argparse.Namespace) -> None:
    work = Path(args.work).expanduser().resolve()
    appdata = Path(args.appdata).expanduser().resolve()
    dbroot = validate_appdata(appdata)
    if args.backup:
        backup = Path(args.backup).expanduser().resolve()
    else:
        last = json.loads(require_file(work / "last-install.json", "Last-install metadata").read_text())
        backup = Path(last["backup"]).resolve()
    if not backup.is_relative_to((work / "backups").resolve()):
        raise Fail("Rollback backup must be located under this tool's backup directory")
    old = require_file(backup / "FileHashesDatabase/game-hashes-release.json", "Original database marker")
    _ = old  # confirms this backup contains the original database directory
    print(f"Restore Nexus hash database backup: {backup}")
    print("STOP: Completely close Nexus Mods App first. DataModel is NOT overwritten automatically.")
    if not args.yes:
        answer = input("Type RESTORE to move the current database aside and restore the backup: ")
        if answer != "RESTORE":
            raise Fail("Cancelled by user")
    quarantine = appdata / f"FileHashesDatabase.before-rollback-{int(time.time())}"
    if quarantine.exists():
        raise Fail(f"Quarantine path already exists: {quarantine}")
    dbroot.rename(quarantine)
    try:
        shutil.copytree(backup / "FileHashesDatabase", dbroot, symlinks=True)
    except Exception:
        if dbroot.exists():
            shutil.rmtree(dbroot)
        quarantine.rename(dbroot)
        raise
    print(f"Restored DB from {backup}. Current DB preserved at {quarantine}.")
    print("If you need to restore the Nexus DataModel too, do it manually from the same backup after reviewing changes.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Cyberpunk Steam hash database repair for archived Nexus Mods App (Linux)")
    parser.add_argument("--work", default=str(DEFAULT_WORK), help="Local work/backup directory (default: .work)")
    parser.add_argument("--appdata", default=str(DEFAULT_APPDATA), help="Nexus Mods App XDG data directory")
    sub = parser.add_subparsers(dest="command", required=True)
    p_build = sub.add_parser("build", help="Build a new database from Steam cache + verified local game files")
    p_build.add_argument("--steamapps", required=True, help="Path to SteamLibrary/steamapps with appmanifest_1091500.acf")
    p_build.add_argument("--version", required=True, help="Game version label (e.g. 2.5); supply the REAL game version")
    p_build.add_argument("--cache", help="Steam depotcache directory or exact cached 1091501_*.manifest file")
    p_build.add_argument("--rerun", action="store_true", help="Archive an earlier run of this build and start fresh")
    sub.add_parser("check", help="Validate generated database without touching Nexus")
    p_install = sub.add_parser("install", help="Backup and install generated DB; keeps rollback copy")
    p_install.add_argument("--yes", action="store_true", help="Skip interactive confirmation (close the app first)")
    p_rollback = sub.add_parser("rollback", help="Restore previous Nexus hash DB")
    p_rollback.add_argument("--backup", help="Backup path (defaults to last successful install)")
    p_rollback.add_argument("--yes", action="store_true", help="Skip interactive confirmation (close the app first)")
    args = parser.parse_args()
    try:
        if args.command == "build": build(args)
        elif args.command == "check":
            verify_output(latest_run(Path(args.work).expanduser().resolve()))
            print("CHECK ONLY: No installed game, Steam files, or Nexus files changed.")
        elif args.command == "install": install(args)
        else: rollback(args)
    except (Fail, OSError, json.JSONDecodeError, subprocess.SubprocessError, KeyboardInterrupt) as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
