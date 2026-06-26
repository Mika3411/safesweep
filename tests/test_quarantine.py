from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from unused_file_finder.quarantine import QuarantineError, QuarantineManager, QuarantineSettings


def test_quarantine_and_restore_file(tmp_path: Path) -> None:
    source = tmp_path / "docs" / "old.txt"
    source.parent.mkdir()
    source.write_text("important", encoding="utf-8")
    timestamp = time.time() - 1000
    os.utime(source, (timestamp, timestamp))

    manager = QuarantineManager(tmp_path / "quarantine")
    records = manager.quarantine([source])

    assert len(records) == 1
    record = records[0]
    assert not source.exists()
    assert record.quarantined_path.exists()
    assert manager.list_records()[0].original_path == source

    restored = manager.restore([record.record_id])

    assert len(restored) == 1
    assert source.read_text(encoding="utf-8") == "important"
    assert manager.list_records() == []

    history_actions = [record.action for record in manager.list_history()]
    assert "Mis en quarantaine" in history_actions
    assert "Restauré" in history_actions


def test_restore_refuses_to_overwrite_existing_file(tmp_path: Path) -> None:
    source = tmp_path / "docs" / "old.txt"
    source.parent.mkdir()
    source.write_text("important", encoding="utf-8")

    manager = QuarantineManager(tmp_path / "quarantine")
    record = manager.quarantine([source])[0]
    source.write_text("new file", encoding="utf-8")

    with pytest.raises(QuarantineError):
        manager.restore([record.record_id])

    assert source.read_text(encoding="utf-8") == "new file"
    assert record.quarantined_path.exists()


def test_direct_recycle_history_can_be_recorded(tmp_path: Path) -> None:
    manager = QuarantineManager(tmp_path / "quarantine")

    manager.record_recycle_paths([(tmp_path / "old.log", 123)])

    history = manager.list_history()
    assert len(history) == 1
    assert history[0].action == "Envoyé à la Corbeille"
    assert history[0].path == tmp_path / "old.log"
    assert history[0].size == 123


def test_quarantine_settings_persist(tmp_path: Path) -> None:
    manager = QuarantineManager(tmp_path / "quarantine")

    manager.save_settings(QuarantineSettings(retention_days=7, auto_prompt_enabled=False))

    settings = manager.load_settings()
    assert settings.retention_days == 7
    assert settings.auto_prompt_enabled is False


def test_expired_records_uses_retention_days(tmp_path: Path) -> None:
    source = tmp_path / "old.bin"
    source.write_bytes(b"data")
    manager = QuarantineManager(tmp_path / "quarantine")
    record = manager.quarantine([source])[0]

    raw_records = json.loads(manager.manifest_path.read_text(encoding="utf-8"))
    raw_records[0]["quarantined_at"] = time.time() - 40 * 24 * 60 * 60
    manager.manifest_path.write_text(json.dumps(raw_records), encoding="utf-8")

    expired_30_days = manager.expired_records(QuarantineSettings(retention_days=30))
    expired_60_days = manager.expired_records(QuarantineSettings(retention_days=60))

    assert [expired.record_id for expired in expired_30_days] == [record.record_id]
    assert expired_60_days == []
