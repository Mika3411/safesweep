from __future__ import annotations

import json
import os
import shutil
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence


class QuarantineError(RuntimeError):
    pass


DEFAULT_RETENTION_DAYS = 30


@dataclass(frozen=True)
class QuarantineRecord:
    record_id: str
    original_path: Path
    quarantined_path: Path
    size: int
    quarantined_at: float
    accessed_at: float
    modified_at: float
    created_at: float


@dataclass(frozen=True)
class QuarantineSettings:
    retention_days: int = DEFAULT_RETENTION_DAYS
    auto_prompt_enabled: bool = True


@dataclass(frozen=True)
class ActionHistoryRecord:
    event_id: str
    action: str
    path: Path
    size: int
    occurred_at: float
    details: str = ""


class QuarantineManager:
    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root) if root else _default_quarantine_root()
        self.files_dir = self.root / "files"
        self.manifest_path = self.root / "manifest.json"
        self.settings_path = self.root / "settings.json"
        self.history_path = self.root / "history.json"

    def list_records(self) -> list[QuarantineRecord]:
        records = self._load_records()
        records.sort(key=lambda item: item.quarantined_at, reverse=True)
        return records

    def list_history(self) -> list[ActionHistoryRecord]:
        records = self._load_history()
        records.sort(key=lambda item: item.occurred_at, reverse=True)
        return records

    def load_settings(self) -> QuarantineSettings:
        if not self.settings_path.exists():
            return QuarantineSettings()

        try:
            raw = json.loads(self.settings_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise QuarantineError(f"Impossible de lire les réglages de quarantaine: {exc}") from exc

        retention_days = int(raw.get("retention_days", DEFAULT_RETENTION_DAYS))
        if retention_days < 1:
            retention_days = 1
        return QuarantineSettings(
            retention_days=retention_days,
            auto_prompt_enabled=bool(raw.get("auto_prompt_enabled", True)),
        )

    def save_settings(self, settings: QuarantineSettings) -> None:
        retention_days = max(1, int(settings.retention_days))
        self.root.mkdir(parents=True, exist_ok=True)
        payload = {
            "retention_days": retention_days,
            "auto_prompt_enabled": bool(settings.auto_prompt_enabled),
        }
        temp_path = self.settings_path.with_suffix(".tmp")
        temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_path.replace(self.settings_path)

    def expires_at(self, record: QuarantineRecord, settings: QuarantineSettings | None = None) -> float:
        active_settings = settings or self.load_settings()
        return record.quarantined_at + active_settings.retention_days * 24 * 60 * 60

    def expired_records(
        self,
        settings: QuarantineSettings | None = None,
        reference_time: float | None = None,
    ) -> list[QuarantineRecord]:
        active_settings = settings or self.load_settings()
        now = time.time() if reference_time is None else reference_time
        return [record for record in self.list_records() if self.expires_at(record, active_settings) <= now]

    def quarantine(self, paths: Sequence[str | Path]) -> list[QuarantineRecord]:
        self.files_dir.mkdir(parents=True, exist_ok=True)
        records = self._load_records()
        new_records: list[QuarantineRecord] = []

        for path_value in paths:
            source = Path(path_value).resolve(strict=False)
            if not source.exists():
                raise QuarantineError(f"Fichier introuvable: {source}")
            if not source.is_file():
                raise QuarantineError(f"Ce chemin n'est pas un fichier: {source}")
            if _same_or_child(source, self.root):
                raise QuarantineError("Ce fichier est déjà dans la quarantaine.")

            stat_result = source.stat()
            record_id = uuid.uuid4().hex
            target_dir = self.files_dir / record_id
            target_dir.mkdir(parents=True, exist_ok=False)
            target = target_dir / source.name

            shutil.move(str(source), str(target))

            record = QuarantineRecord(
                record_id=record_id,
                original_path=source,
                quarantined_path=target,
                size=stat_result.st_size,
                quarantined_at=time.time(),
                accessed_at=stat_result.st_atime,
                modified_at=stat_result.st_mtime,
                created_at=stat_result.st_ctime,
            )
            records.append(record)
            new_records.append(record)
            self._save_records(records)
            self._append_history(
                "Mis en quarantaine",
                record.original_path,
                record.size,
                f"Quarantaine : {record.quarantined_path}",
            )

        return new_records

    def restore(self, record_ids: Sequence[str]) -> list[QuarantineRecord]:
        wanted = set(record_ids)
        records = self._load_records()
        restored: list[QuarantineRecord] = []
        remaining: list[QuarantineRecord] = []

        for record in records:
            if record.record_id not in wanted:
                remaining.append(record)
                continue

            if not record.quarantined_path.exists():
                raise QuarantineError(f"Fichier de quarantaine introuvable: {record.quarantined_path}")
            if record.original_path.exists():
                raise QuarantineError(f"Impossible de restaurer, le chemin existe déjà: {record.original_path}")

            record.original_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(record.quarantined_path), str(record.original_path))
            try:
                os.utime(record.original_path, (record.accessed_at, record.modified_at))
            except OSError:
                pass
            _remove_empty_parent(record.quarantined_path.parent, stop_at=self.files_dir)
            restored.append(record)
            self._append_history(
                "Restauré",
                record.original_path,
                record.size,
                f"Depuis : {record.quarantined_path}",
            )

        self._save_records(remaining)
        return restored

    def remove_records(self, record_ids: Sequence[str]) -> list[QuarantineRecord]:
        wanted = set(record_ids)
        records = self._load_records()
        removed: list[QuarantineRecord] = []
        remaining: list[QuarantineRecord] = []

        for record in records:
            if record.record_id not in wanted:
                remaining.append(record)
                continue

            if record.quarantined_path.exists():
                record.quarantined_path.unlink()
                _remove_empty_parent(record.quarantined_path.parent, stop_at=self.files_dir)
            removed.append(record)
            self._append_history("Retiré de la quarantaine", record.original_path, record.size)

        self._save_records(remaining)
        return removed

    def send_to_recycle_bin(self, record_ids: Sequence[str]) -> list[QuarantineRecord]:
        from .recycle import move_to_recycle_bin

        wanted = set(record_ids)
        records = self._load_records()
        selected = [record for record in records if record.record_id in wanted]
        paths = [record.quarantined_path for record in selected if record.quarantined_path.exists()]
        move_to_recycle_bin(paths)

        remaining = [record for record in records if record.record_id not in wanted]
        for record in selected:
            _remove_empty_parent(record.quarantined_path.parent, stop_at=self.files_dir)
            self._append_history(
                "Envoyé à la Corbeille",
                record.original_path,
                record.size,
                f"Depuis la quarantaine : {record.quarantined_path}",
            )

        self._save_records(remaining)
        return selected

    def record_recycle_paths(self, paths_and_sizes: Sequence[tuple[str | Path, int]]) -> None:
        for path_value, size in paths_and_sizes:
            self._append_history(
                "Envoyé à la Corbeille",
                Path(path_value),
                int(size),
                "Depuis les résultats d'analyse",
            )

    def _load_records(self) -> list[QuarantineRecord]:
        if not self.manifest_path.exists():
            return []

        try:
            raw_records = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise QuarantineError(f"Impossible de lire la quarantaine: {exc}") from exc

        records: list[QuarantineRecord] = []
        for raw in raw_records:
            records.append(
                QuarantineRecord(
                    record_id=str(raw["record_id"]),
                    original_path=Path(raw["original_path"]),
                    quarantined_path=Path(raw["quarantined_path"]),
                    size=int(raw["size"]),
                    quarantined_at=float(raw["quarantined_at"]),
                    accessed_at=float(raw["accessed_at"]),
                    modified_at=float(raw["modified_at"]),
                    created_at=float(raw["created_at"]),
                )
            )
        return records

    def _save_records(self, records: Sequence[QuarantineRecord]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        serializable = []
        for record in records:
            data = asdict(record)
            data["original_path"] = str(record.original_path)
            data["quarantined_path"] = str(record.quarantined_path)
            serializable.append(data)

        temp_path = self.manifest_path.with_suffix(".tmp")
        temp_path.write_text(json.dumps(serializable, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_path.replace(self.manifest_path)

    def _load_history(self) -> list[ActionHistoryRecord]:
        if not self.history_path.exists():
            return []

        try:
            raw_records = json.loads(self.history_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise QuarantineError(f"Impossible de lire l'historique: {exc}") from exc

        records: list[ActionHistoryRecord] = []
        for raw in raw_records:
            records.append(
                ActionHistoryRecord(
                    event_id=str(raw["event_id"]),
                    action=str(raw["action"]),
                    path=Path(raw["path"]),
                    size=int(raw["size"]),
                    occurred_at=float(raw["occurred_at"]),
                    details=str(raw.get("details", "")),
                )
            )
        return records

    def _save_history(self, records: Sequence[ActionHistoryRecord]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        serializable = []
        for record in records:
            data = asdict(record)
            data["path"] = str(record.path)
            serializable.append(data)

        temp_path = self.history_path.with_suffix(".tmp")
        temp_path.write_text(json.dumps(serializable, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_path.replace(self.history_path)

    def _append_history(self, action: str, path: Path, size: int, details: str = "") -> None:
        records = self._load_history()
        records.append(
            ActionHistoryRecord(
                event_id=uuid.uuid4().hex,
                action=action,
                path=path,
                size=size,
                occurred_at=time.time(),
                details=details,
            )
        )
        self._save_history(records)


def _default_quarantine_root() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base) / "NettoyeurFichiers" / "Quarantine"
    return Path.home() / "AppData" / "Local" / "NettoyeurFichiers" / "Quarantine"


def _remove_empty_parent(path: Path, stop_at: Path) -> None:
    current = path
    stop = stop_at.resolve(strict=False)
    while current.resolve(strict=False) != stop:
        try:
            current.rmdir()
        except OSError:
            break
        current = current.parent


def _same_or_child(path: Path, parent: Path) -> bool:
    try:
        path_resolved = path.resolve(strict=False)
        parent_resolved = parent.resolve(strict=False)
        return os.path.commonpath([os.fspath(path_resolved), os.fspath(parent_resolved)]) == os.fspath(parent_resolved)
    except (OSError, ValueError):
        return False
