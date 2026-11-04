"""Offline regression tests: these never call Steam, git, NuGet, or Nexus."""
import importlib.util
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "scripts/hashfix.py"
spec = importlib.util.spec_from_file_location("hashfix", SRC)
hashfix = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hashfix)


class TestSafety(unittest.TestCase):
    def test_steam_acf_installed_depot(self):
        acf = '''"AppState" { "appid" "1091500" "buildid" "26161058"
            "InstalledDepots" { "1091501" { "manifest" "3524634124112875626" "size" "66" } } }'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "appmanifest_1091500.acf"
            path.write_text(acf)
            self.assertEqual(hashfix.depot_from_acf(path), (26161058, 3524634124112875626))

    def test_alias_addition_is_scoped_and_no_duplicates(self):
        source = '''Cyberpunk 2077:\n  Windows:\n    - Name: 2.3\n      Steam:\n        - 11111\nFallout 4:\n'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "version_aliases.yaml"
            path.write_text(source)
            hashfix.insert_version_alias(path, "2.5", 3524634124112875626)
            self.assertIn("Name: 2.5\n      Steam:\n        - 3524634124112875626", path.read_text())
            self.assertIn("Fallout 4:", path.read_text())
            with self.assertRaises(hashfix.Fail):
                hashfix.insert_version_alias(path, "2.5", 3524634124112875626)

    def test_mapping_cache_duplicate_domain_fix(self):
        rows = [
            {"id": 3333, "domain_name": "cyberpunk2077"},
            {"id": 8703, "domain_name": "neverwinter"},
            {"id": 8704, "domain_name": "neverwinter"},
            {"id": 9193, "domain_name": "wrc5"},
            {"id": 9194, "domain_name": "wrc5"},
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "games.json"
            path.write_text(json.dumps(rows))
            hashfix.normalize_games_json(path)
            clean = json.loads(path.read_text())
            self.assertEqual(len(clean), 3)
            self.assertEqual(clean[0]["id"], 3333)
            self.assertTrue((Path(directory) / "games.json.before-hashfix").is_file())

    def test_does_not_remove_cyberpunk_mapping(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "games.json"
            original = json.dumps([{"id": 3333, "domain_name": "other"},
                                   {"id": 3334, "domain_name": "other"}])
            path.write_text(original)
            with self.assertRaises(hashfix.Fail):
                hashfix.normalize_games_json(path)
            self.assertEqual(path.read_text(), original)

    def test_reject_zip_path_traversal(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("../outside", b"test")
            with zipfile.ZipFile(path) as archive:
                with self.assertRaises(hashfix.Fail):
                    hashfix.zip_entries_safe(archive)

    def test_accept_rocksdb_like_zip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "good.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("CURRENT", "MANIFEST-000005")
                archive.writestr("MANIFEST-000005", "record")
            with zipfile.ZipFile(path) as archive:
                self.assertEqual(len(hashfix.zip_entries_safe(archive)), 2)


if __name__ == "__main__":
    unittest.main()
