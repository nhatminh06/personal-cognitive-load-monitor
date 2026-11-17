"""Synthetic scanner controls; no real credentials are stored in fixtures."""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.check_secret_scan import verify


ROOT = Path(__file__).resolve().parents[2]
SCANNER = Path(os.environ.get("GITLEAKS_BIN", "/tmp/cogniflow-validation-tools/gitleaks"))


class SecretScanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def scan(self) -> tuple[int, Path]:
        if not SCANNER.is_file():
            self.skipTest("exact scanner unavailable in this test job")
        report = self.root / "scan-report.json"
        result = subprocess.run(
            [str(SCANNER), "dir", str(self.root), "--config", str(ROOT / ".gitleaks.toml"),
             "--redact", "--no-banner", "--report-format", "json",
             "--report-path", str(report)],
            capture_output=True, text=True, timeout=20, check=False,
        )
        return result.returncode, report

    @staticmethod
    def fake_token() -> str:
        return "gh" + "p_" + "A7kP3mR9qT2vX5zB8cD1eF4gH6jK0nL7pQ3r"

    def test_synthetic_token_fails_in_multiple_filenames(self) -> None:
        for name in ("new.txt", "nested/changed.json", "docs/track-b/phase-0a1/captures/other.json"):
            with self.subTest(name=name):
                path = self.root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('token = "' + self.fake_token() + '"\n')
                exit_code, report = self.scan()
                self.assertEqual(exit_code, 1)
                self.assertTrue(json.loads(report.read_text()))
                with self.assertRaises(ValueError):
                    verify([report])
                path.unlink()

    def test_public_advisory_url_is_allowed(self) -> None:
        path = self.root / "docs/track-b/phase-0a1/captures/calico-node-scan.json"
        path.parent.mkdir(parents=True)
        path.write_text('  "https://github.com/PCRE2Project/pcre2/commit/'
                        + '1dcd0cf42a6a7cb62cc9a7c024196733abcfda95'
                        + '%20%28pcre2-10.48-RC1%29",\n')
        exit_code, report = self.scan()
        self.assertEqual(exit_code, 0)
        verify([report])

    def test_commit_range_catches_token_removed_from_final_tree(self) -> None:
        if not SCANNER.is_file():
            self.skipTest("exact scanner unavailable in this test job")
        def git(*args: str) -> str:
            return subprocess.check_output(["git", "-C", str(self.root), *args], text=True).strip()

        git("init", "-q")
        git("config", "user.name", "Synthetic Fixture")
        git("config", "user.email", "fixture@example.invalid")
        path = self.root / "fixture.txt"
        path.write_text("baseline\n")
        git("add", "fixture.txt")
        git("commit", "-qm", "baseline")
        base = git("rev-parse", "HEAD")
        path.write_text('token = "' + self.fake_token() + '"\n')
        git("commit", "-qam", "synthetic-token")
        path.write_text("clean again\n")
        git("commit", "-qam", "remove-token")
        head = git("rev-parse", "HEAD")
        report = self.root / "range-report.json"
        result = subprocess.run(
            [str(SCANNER), "git", str(self.root), "--log-opts", f"{base}..{head}",
             "--config", str(ROOT / ".gitleaks.toml"), "--redact", "--no-banner",
             "--report-format", "json", "--report-path", str(report)],
            capture_output=True, text=True, timeout=20, check=False,
        )
        self.assertEqual(result.returncode, 1)
        self.assertTrue(json.loads(report.read_text()))

    def test_missing_or_malformed_report_fails_closed(self) -> None:
        with self.assertRaises(OSError):
            verify([self.root / "missing.json"])
        report = self.root / "invalid.json"
        report.write_text("{}")
        with self.assertRaises(ValueError):
            verify([report])
        report.write_text("[]")
        verify([report])


if __name__ == "__main__":
    unittest.main()
