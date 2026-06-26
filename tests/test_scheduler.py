from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from unused_file_finder.licensing import LicenseStatus
from unused_file_finder.scheduler import (
    SchedulerError,
    ScheduledScanConfig,
    build_task_xml,
    load_config,
    run_scheduled_scan,
    save_config,
)


@pytest.fixture(autouse=True)
def allow_scheduled_license(monkeypatch: pytest.MonkeyPatch) -> None:
    class AllowedLicenseManager:
        def require_valid_license(self) -> LicenseStatus:
            return LicenseStatus(
                can_use=True,
                valid=True,
                status="active",
                reason="Licence active.",
                source="test",
                device_id="safesweep-test",
                device_name="Test PC",
            )

    monkeypatch.setattr("unused_file_finder.scheduler.LicenseManager", AllowedLicenseManager)


def test_schedule_config_roundtrip_normalizes_extensions(tmp_path: Path) -> None:
    config_path = tmp_path / "planification.json"
    config = ScheduledScanConfig(
        root=tmp_path,
        scan_mode="installers",
        days_unused=90,
        min_size_bytes=10 * 1024 * 1024,
        extension_filter=(".EXE", "iso"),
        frequency="monthly",
        month_day=12,
        start_time="08:30",
        report_dir=tmp_path / "rapports",
    )

    save_config(config, config_path)
    loaded = load_config(config_path)

    assert loaded.root == tmp_path
    assert loaded.scan_mode == "installers"
    assert loaded.extension_filter == (".exe", ".iso")
    assert loaded.frequency == "monthly"
    assert loaded.month_day == 12
    assert loaded.start_time == "08:30"


def test_task_xml_contains_interactive_weekly_trigger_and_action(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("USERDOMAIN", "PC")
    monkeypatch.setenv("USERNAME", "admin")
    config = ScheduledScanConfig(root=tmp_path, frequency="weekly", weekday="Tuesday", start_time="19:45")

    xml = build_task_xml(
        config,
        Path(r"C:\Apps\SafeSweep.exe"),
        ("--scheduled-scan", "--config", r"C:\Users\admin\AppData\Local\SafeSweep\planification.json"),
    )

    assert "<Tuesday />" in xml
    assert "<LogonType>InteractiveToken</LogonType>" in xml
    assert "<UserId>PC\\admin</UserId>" in xml
    assert "SafeSweep scheduled analysis" in xml
    assert "--scheduled-scan" in xml
    assert "C:\\Users\\admin\\AppData\\Local\\SafeSweep\\planification.json" in xml


def test_invalid_schedule_time_is_rejected(tmp_path: Path) -> None:
    config = ScheduledScanConfig(root=tmp_path, start_time="25:00")

    with pytest.raises(SchedulerError):
        build_task_xml(config, "app.exe", ("--scheduled-scan",))


def test_scheduled_scan_writes_reports_without_deleting_files(tmp_path: Path) -> None:
    old_file = tmp_path / "old.log"
    old_file.write_text("journal", encoding="utf-8")
    old_timestamp = time.time() - 3 * 24 * 60 * 60
    os.utime(old_file, (old_timestamp, old_timestamp))

    config_path = tmp_path / "planification.json"
    reports_dir = tmp_path / "rapports"
    save_config(
        ScheduledScanConfig(
            root=tmp_path,
            scan_mode="unused",
            days_unused=1,
            min_size_bytes=1,
            report_dir=reports_dir,
            start_time="07:00",
        ),
        config_path,
    )

    result = run_scheduled_scan(config_path, notify=False)

    assert old_file.exists()
    assert len(result.results) == 1
    assert result.results[0].path == old_file
    assert result.html_report.exists()
    assert result.csv_report.exists()
    assert "old.log" in result.html_report.read_text(encoding="utf-8")
