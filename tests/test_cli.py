from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from unused_file_finder.cli import run_cli
from unused_file_finder.__main__ import main
from unused_file_finder.licensing import LicenseStatus


@pytest.fixture(autouse=True)
def allow_cli_license(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "unused_file_finder.cli._require_license_for_cli",
        lambda _args: LicenseStatus(
            can_use=True,
            valid=True,
            status="active",
            reason="Licence active.",
            source="test",
            device_id="safesweep-test",
            device_name="Test PC",
        ),
    )


def test_cli_scan_exports_csv_and_html(tmp_path: Path, capsys) -> None:
    source = tmp_path / "old.log"
    source.write_text("ancient log", encoding="utf-8")
    old_timestamp = time.time() - 5 * 24 * 60 * 60
    os.utime(source, (old_timestamp, old_timestamp))
    csv_path = tmp_path / "rapport.csv"
    html_path = tmp_path / "rapport.html"

    exit_code = run_cli(
        [
            "scan",
            "--root",
            str(tmp_path),
            "--days",
            "1",
            "--min-size-mb",
            "0",
            "--csv",
            str(csv_path),
            "--html",
            str(html_path),
            "--no-whitelist",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Analyse terminée" in captured.out
    assert "old.log" in csv_path.read_text(encoding="utf-8-sig")
    html = html_path.read_text(encoding="utf-8")
    assert "Rapport SafeSweep" in html
    assert "old.log" in html
    assert "Action recommandée" in html


def test_cli_profiles_lists_available_presets(capsys) -> None:
    exit_code = run_cli(["profiles"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Bureau rapide" in captured.out
    assert "Nettoyage prudent" in captured.out


def test_cli_executable_without_arguments_prints_help(monkeypatch, capsys) -> None:
    monkeypatch.setattr("sys.executable", r"C:\Apps\SafeSweep-CLI.exe")

    exit_code = main([])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "usage: SafeSweep" in captured.out
    assert "profiles" in captured.out
    assert "scan" in captured.out


def test_cli_scan_requires_root_or_profile(capsys) -> None:
    exit_code = run_cli(["scan", "--no-whitelist"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Indiquez --root ou --profile" in captured.err


def test_cli_scan_supports_uninstallers_mode(tmp_path: Path, capsys) -> None:
    uninstaller = tmp_path / "Program Files" / "Demo App" / "uninstall.exe"
    uninstaller.parent.mkdir(parents=True)
    uninstaller.write_bytes(b"demo")

    exit_code = run_cli(
        [
            "scan",
            "--root",
            str(tmp_path),
            "--mode",
            "uninstallers",
            "--no-whitelist",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Applications désinstallables" in captured.out
    assert "1 résultat" in captured.out
