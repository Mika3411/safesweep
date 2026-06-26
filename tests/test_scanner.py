from __future__ import annotations

import os
import time
from pathlib import Path

from unused_file_finder.scanner import (
    ScanOptions,
    format_bytes,
    normalize_extensions,
    scan_for_duplicate_files,
    scan_for_forgotten_installers,
    scan_for_large_folders,
    scan_for_uninstallers,
    scan_for_unused_files,
)


def _write_file(path: Path, size: int, age_days: int) -> None:
    _write_bytes(path, b"x" * size, age_days)


def _write_bytes(path: Path, content: bytes, age_days: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    timestamp = time.time() - (age_days * 24 * 60 * 60)
    os.utime(path, (timestamp, timestamp))


def test_normalize_extensions() -> None:
    assert normalize_extensions(".zip, iso;PDF pdf") == (".zip", ".iso", ".pdf")


def test_format_bytes() -> None:
    assert format_bytes(0) == "0.0 o"
    assert format_bytes(1024) == "1.0 Ko"
    assert format_bytes(1024 * 1024) == "1.0 Mo"


def test_scan_finds_old_large_files(tmp_path: Path) -> None:
    old_big = tmp_path / "archive.zip"
    old_small = tmp_path / "tiny.log"
    recent = tmp_path / "recent.iso"
    ignored = tmp_path / ".git" / "packed.bin"
    ignored_gradle = tmp_path / ".gradle" / "caches" / "artifact.bin"

    _write_file(old_big, 2048, 400)
    _write_file(old_small, 10, 400)
    _write_file(recent, 4096, 2)
    _write_file(ignored, 4096, 400)
    _write_file(ignored_gradle, 4096, 400)

    results, stats = scan_for_unused_files(
        ScanOptions(root=tmp_path, days_unused=365, min_size_bytes=1024, skip_system_locations=True)
    )

    assert [item.path for item in results] == [old_big]
    assert stats.matched_files == 1
    assert stats.scanned_files >= 3


def test_scan_skips_windows_old_and_uppercase_windows_by_default(tmp_path: Path) -> None:
    system_file = tmp_path / "Windows.old" / "WINDOWS" / "System32" / "msedge.dll"
    normal_file = tmp_path / "Users" / "admin" / "archive.bin"

    _write_file(system_file, 2048, 400)
    _write_file(normal_file, 2048, 400)

    results, _stats = scan_for_unused_files(
        ScanOptions(root=tmp_path, days_unused=365, min_size_bytes=1024, skip_system_locations=True)
    )

    assert [item.path for item in results] == [normal_file]


def test_scan_extension_filter(tmp_path: Path) -> None:
    old_zip = tmp_path / "archive.zip"
    old_iso = tmp_path / "image.iso"
    _write_file(old_zip, 2048, 400)
    _write_file(old_iso, 2048, 400)

    results, _stats = scan_for_unused_files(
        ScanOptions(root=tmp_path, days_unused=365, min_size_bytes=1, extension_filter=(".iso",))
    )

    assert [item.path for item in results] == [old_iso]


def test_scan_can_use_modified_time_when_access_time_is_recent(tmp_path: Path) -> None:
    old_modified_recent_access = tmp_path / "old-shortcut.url"
    old_modified_recent_access.write_text("[InternetShortcut]\nURL=https://example.com\n", encoding="utf-8")

    now = time.time()
    old = now - (800 * 24 * 60 * 60)
    os.utime(old_modified_recent_access, (now, old))

    modified_results, _stats = scan_for_unused_files(
        ScanOptions(root=tmp_path, days_unused=365, min_size_bytes=0, age_basis="modified")
    )
    activity_results, _stats = scan_for_unused_files(
        ScanOptions(root=tmp_path, days_unused=365, min_size_bytes=0, age_basis="activity")
    )

    assert [item.path for item in modified_results] == [old_modified_recent_access]
    assert activity_results == []


def test_scan_ghosts_protected_paths_and_extensions(tmp_path: Path) -> None:
    protected_dir_file = tmp_path / "projects" / "keep" / "old.bin"
    protected_extension_file = tmp_path / "downloads" / "design.psd"
    visible_file = tmp_path / "downloads" / "archive.bin"

    _write_file(protected_dir_file, 2048, 400)
    _write_file(protected_extension_file, 2048, 400)
    _write_file(visible_file, 2048, 400)

    results, stats = scan_for_unused_files(
        ScanOptions(
            root=tmp_path,
            days_unused=365,
            min_size_bytes=1,
            protected_paths=(tmp_path / "projects",),
            protected_extensions=(".psd",),
        )
    )

    assert [item.path for item in results] == [visible_file]
    assert stats.skipped_dirs >= 1
    assert stats.skipped_files >= 1


def test_scan_duplicate_files_matches_content_only(tmp_path: Path) -> None:
    first = tmp_path / "a" / "same.bin"
    second = tmp_path / "b" / "same-copy.bin"
    same_size_different_content = tmp_path / "c" / "different.bin"
    unique = tmp_path / "unique.bin"

    _write_bytes(first, b"abc", 20)
    _write_bytes(second, b"abc", 10)
    _write_bytes(same_size_different_content, b"abd", 30)
    _write_bytes(unique, b"abcdef", 30)

    results, stats = scan_for_duplicate_files(ScanOptions(root=tmp_path, min_size_bytes=1))

    assert {item.path for item in results} == {first, second}
    assert {item.duplicate_group for item in results} == {1}
    assert all(item.duplicate_hash for item in results)
    assert stats.duplicate_groups == 1
    assert stats.matched_files == 2
    assert stats.matched_size_bytes == 3


def test_duplicate_scan_ghosts_protected_extensions(tmp_path: Path) -> None:
    _write_bytes(tmp_path / "a.psd", b"same", 400)
    _write_bytes(tmp_path / "b.psd", b"same", 400)

    results, stats = scan_for_duplicate_files(ScanOptions(root=tmp_path, protected_extensions=(".psd",)))

    assert results == []
    assert stats.skipped_files == 2


def test_duplicate_scan_stops_at_candidate_limit(tmp_path: Path) -> None:
    for index in range(6):
        _write_bytes(tmp_path / f"copy-{index}.bin", b"same-content", 400)

    results, stats = scan_for_duplicate_files(ScanOptions(root=tmp_path, max_results=3))

    assert stats.hit_limit is True
    assert len(results) <= 3


def test_scan_forgotten_installers_finds_old_downloads_installers(tmp_path: Path) -> None:
    old_setup = tmp_path / "Downloads" / "setup.exe"
    old_msi = tmp_path / "Downloads" / "tool.msi"
    old_zip = tmp_path / "Downloads" / "driver-package.zip"
    old_iso = tmp_path / "Downloads" / "linux.iso"
    recent_setup = tmp_path / "Downloads" / "recent.exe"
    outside_downloads = tmp_path / "Desktop" / "setup.exe"
    normal_download = tmp_path / "Downloads" / "notes.pdf"

    _write_file(old_setup, 2048, 400)
    _write_file(old_msi, 2048, 500)
    _write_file(old_zip, 2048, 600)
    _write_file(old_iso, 2048, 700)
    _write_file(recent_setup, 2048, 2)
    _write_file(outside_downloads, 2048, 800)
    _write_file(normal_download, 2048, 800)

    results, stats = scan_for_forgotten_installers(ScanOptions(root=tmp_path, days_unused=365, min_size_bytes=1))

    assert {item.path for item in results} == {old_setup, old_msi, old_zip, old_iso}
    assert {item.item_type for item in results} == {"Installateur"}
    assert stats.matched_files == 4
    assert stats.matched_size_bytes == 8192


def test_scan_forgotten_installers_respects_filters_and_protections(tmp_path: Path) -> None:
    protected = tmp_path / "Downloads" / "keep.exe"
    skipped_extension = tmp_path / "Downloads" / "archive.zip"
    visible = tmp_path / "Downloads" / "image.iso"

    _write_file(protected, 2048, 400)
    _write_file(skipped_extension, 2048, 400)
    _write_file(visible, 2048, 400)

    results, stats = scan_for_forgotten_installers(
        ScanOptions(
            root=tmp_path,
            days_unused=365,
            min_size_bytes=1,
            extension_filter=(".iso",),
            protected_paths=(protected,),
        )
    )

    assert [item.path for item in results] == [visible]
    assert stats.skipped_files >= 1


def test_scan_uninstallers_finds_uninstall_exe_in_application_roots(tmp_path: Path) -> None:
    first = tmp_path / "Program Files" / "App One" / "uninstall.exe"
    second = tmp_path / "Program Files (x86)" / "App Two" / "UnInstall.EXE"
    user_app = tmp_path / "Users" / "admin" / "AppData" / "Local" / "App Three" / "uninstall.exe"
    windows_uninstaller = tmp_path / "Windows" / "System32" / "uninstall.exe"
    inno_uninstaller = tmp_path / "Program Files" / "App Four" / "unins000.exe"
    short_uninstaller = tmp_path / "Program Files" / "App Five" / "uninst.exe"
    named_uninstaller = tmp_path / "Program Files" / "App Six" / "uninstaller.exe"

    _write_file(first, 1024, 10)
    _write_file(second, 1024, 10)
    _write_file(user_app, 1024, 10)
    _write_file(windows_uninstaller, 1024, 10)
    _write_file(inno_uninstaller, 1024, 10)
    _write_file(short_uninstaller, 1024, 10)
    _write_file(named_uninstaller, 1024, 10)

    results, stats = scan_for_uninstallers(ScanOptions(root=tmp_path, skip_system_locations=True))

    assert {item.path for item in results} == {
        first,
        second,
        user_app,
        inno_uninstaller,
        short_uninstaller,
        named_uninstaller,
    }
    assert {item.item_type for item in results} == {"Désinstallateur"}
    assert {item.folder_hint for item in results} == {"App One", "App Two", "App Three", "App Four", "App Five", "App Six"}
    assert all(item.launch_command for item in results)
    assert stats.matched_files == 6
    assert stats.skipped_dirs >= 1


def test_scan_uninstallers_respects_protected_paths(tmp_path: Path) -> None:
    protected = tmp_path / "Program Files" / "Keep" / "uninstall.exe"
    visible = tmp_path / "Program Files" / "Visible" / "uninstall.exe"

    _write_file(protected, 1024, 10)
    _write_file(visible, 1024, 10)

    results, stats = scan_for_uninstallers(ScanOptions(root=tmp_path, protected_paths=(protected.parent,)))

    assert [item.path for item in results] == [visible]
    assert stats.skipped_dirs >= 1


def test_scan_large_folders_finds_cache_and_exports(tmp_path: Path) -> None:
    cache_file = tmp_path / "App" / "Cache" / "blob.bin"
    export_file = tmp_path / "Project" / "exports" / "video.mov"
    small_file = tmp_path / "small" / "tiny.txt"

    _write_file(cache_file, 4096, 3)
    _write_file(export_file, 2048, 30)
    _write_file(small_file, 10, 1)

    results, stats = scan_for_large_folders(ScanOptions(root=tmp_path, min_size_bytes=1024))

    by_path = {item.path: item for item in results}
    assert cache_file.parent in by_path
    assert export_file.parent in by_path
    assert small_file.parent not in by_path
    assert by_path[cache_file.parent].item_type == "Dossier"
    assert by_path[cache_file.parent].folder_hint == "Cache"
    assert by_path[export_file.parent].folder_hint == "Export"
    assert stats.matched_files >= 2


def test_scan_large_folders_respects_protected_paths(tmp_path: Path) -> None:
    protected_file = tmp_path / "keep" / "Cache" / "blob.bin"
    visible_file = tmp_path / "visible" / "Cache" / "blob.bin"

    _write_file(protected_file, 4096, 3)
    _write_file(visible_file, 4096, 3)

    results, stats = scan_for_large_folders(
        ScanOptions(root=tmp_path, min_size_bytes=1024, protected_paths=(tmp_path / "keep",))
    )

    paths = {item.path for item in results}
    assert protected_file.parent not in paths
    assert visible_file.parent in paths
    assert stats.skipped_dirs >= 1
