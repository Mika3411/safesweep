from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


class ProtectionError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProtectionSettings:
    protected_paths: tuple[Path, ...] = ()
    protected_extensions: tuple[str, ...] = ()


class ProtectionList:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else _default_protection_path()

    def load(self) -> ProtectionSettings:
        if not self.path.exists():
            return ProtectionSettings()

        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ProtectionError(f"Impossible de lire la liste blanche: {exc}") from exc

        paths = _normalize_paths(raw.get("protected_paths", ()))
        extensions = normalize_extensions(raw.get("protected_extensions", ()))
        return ProtectionSettings(protected_paths=paths, protected_extensions=extensions)

    def save(self, settings: ProtectionSettings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "protected_paths": [str(path) for path in settings.protected_paths],
            "protected_extensions": list(settings.protected_extensions),
        }
        temp_path = self.path.with_suffix(".tmp")
        temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_path.replace(self.path)

    def add_paths(self, paths: Iterable[str | Path]) -> ProtectionSettings:
        current = self.load()
        merged_paths = _normalize_paths((*current.protected_paths, *paths))
        updated = ProtectionSettings(
            protected_paths=merged_paths,
            protected_extensions=current.protected_extensions,
        )
        self.save(updated)
        return updated

    def add_extensions(self, extensions: str | Iterable[str]) -> ProtectionSettings:
        current = self.load()
        updated = ProtectionSettings(
            protected_paths=current.protected_paths,
            protected_extensions=normalize_extensions((*current.protected_extensions, *normalize_extensions(extensions))),
        )
        self.save(updated)
        return updated

    def remove_paths(self, paths: Iterable[str | Path]) -> ProtectionSettings:
        current = self.load()
        removed = {os.path.normcase(os.fspath(Path(path).expanduser().resolve(strict=False))) for path in paths}
        kept = tuple(
            path
            for path in current.protected_paths
            if os.path.normcase(os.fspath(path.resolve(strict=False))) not in removed
        )
        updated = ProtectionSettings(protected_paths=kept, protected_extensions=current.protected_extensions)
        self.save(updated)
        return updated

    def remove_extensions(self, extensions: Iterable[str]) -> ProtectionSettings:
        current = self.load()
        removed = set(normalize_extensions(extensions))
        kept = tuple(extension for extension in current.protected_extensions if extension not in removed)
        updated = ProtectionSettings(protected_paths=current.protected_paths, protected_extensions=kept)
        self.save(updated)
        return updated


def normalize_extensions(value: str | Iterable[str]) -> tuple[str, ...]:
    if isinstance(value, str):
        raw_parts = re.split(r"[\s,;]+", value.strip())
    else:
        raw_parts = list(value)

    normalized: list[str] = []
    seen: set[str] = set()
    for raw in raw_parts:
        item = str(raw).strip().casefold()
        if not item:
            continue
        if not item.startswith("."):
            item = f".{item}"
        if item not in seen:
            normalized.append(item)
            seen.add(item)
    return tuple(normalized)


def _normalize_paths(paths: Iterable[str | Path]) -> tuple[Path, ...]:
    normalized: list[Path] = []
    seen: set[str] = set()
    for raw_path in paths:
        if not raw_path:
            continue
        path = Path(raw_path).expanduser().resolve(strict=False)
        key = os.path.normcase(os.fspath(path))
        if key not in seen:
            normalized.append(path)
            seen.add(key)
    return tuple(normalized)


def _default_protection_path() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base) / "NettoyeurFichiers" / "liste-blanche.json"
    return Path.home() / "AppData" / "Local" / "NettoyeurFichiers" / "liste-blanche.json"

