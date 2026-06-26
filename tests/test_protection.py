from __future__ import annotations

from pathlib import Path

from unused_file_finder.protection import ProtectionList, normalize_extensions


def test_normalize_protected_extensions() -> None:
    assert normalize_extensions(".PSD, blend;URL") == (".psd", ".blend", ".url")


def test_protection_list_persists_paths_and_extensions(tmp_path: Path) -> None:
    storage = tmp_path / "liste-blanche.json"
    protected_path = tmp_path / "Projects"

    protection = ProtectionList(storage)
    protection.add_paths([protected_path])
    protection.add_extensions(".psd, .blend")

    reloaded = ProtectionList(storage).load()

    assert reloaded.protected_paths == (protected_path.resolve(strict=False),)
    assert reloaded.protected_extensions == (".psd", ".blend")

