from __future__ import annotations

import hashlib
import os
import re
import time
from collections import defaultdict
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable, Iterable


FILE_ATTRIBUTE_HIDDEN = 0x2
FILE_ATTRIBUTE_SYSTEM = 0x4
FILE_ATTRIBUTE_REPARSE_POINT = 0x400

DEFAULT_EXCLUDED_DIR_NAMES = frozenset(
    {
        "$Recycle.Bin",
        "System Volume Information",
        "Windows",
        "Windows.old",
        "System32",
        "SysWOW64",
        "WinSxS",
        "Program Files",
        "Program Files (x86)",
        "ProgramData",
        "AppData",
        ".git",
        ".svn",
        ".hg",
        ".android",
        ".cache",
        ".cargo",
        ".gradle",
        ".ivy2",
        ".m2",
        ".npm",
        ".nuget",
        ".pnpm-store",
        ".rustup",
        "Cache",
        "Caches",
        "Code Cache",
        "DawnCache",
        "GPUCache",
        "IndexedDB",
        "Service Worker",
        "blob_storage",
        "node_modules",
        ".venv",
        "venv",
        "__pycache__",
    }
)
DEFAULT_EXCLUDED_DIR_NAMES_NORMALIZED = frozenset(name.casefold() for name in DEFAULT_EXCLUDED_DIR_NAMES)
AGE_BASIS_VALUES = frozenset({"activity", "modified", "accessed"})
DOWNLOAD_DIR_NAMES_NORMALIZED = frozenset({"downloads", "telechargements", "téléchargements"})
FORGOTTEN_INSTALLER_EXTENSIONS = frozenset(
    {
        ".7z",
        ".appx",
        ".appxbundle",
        ".cab",
        ".exe",
        ".img",
        ".iso",
        ".msi",
        ".msix",
        ".msixbundle",
        ".msp",
        ".rar",
        ".zip",
    }
)
INSTALLER_BINARY_EXTENSIONS = frozenset({".appx", ".appxbundle", ".exe", ".msi", ".msix", ".msixbundle", ".msp"})
INSTALLER_ARCHIVE_EXTENSIONS = frozenset({".7z", ".cab", ".rar", ".zip"})
INSTALLER_IMAGE_EXTENSIONS = frozenset({".img", ".iso"})
UNINSTALLER_FILE_NAMES = frozenset({"uninstall.exe", "uninst.exe", "uninstaller.exe"})
UNINSTALLER_FILE_PATTERNS = (re.compile(r"unins\d{3}\.exe", re.IGNORECASE),)
UNINSTALLER_EXCLUDED_DIR_NAMES = frozenset(
    {
        "$recycle.bin",
        "system volume information",
        "windows",
        "windows.old",
        "system32",
        "syswow64",
        "winsxs",
        "boot",
        ".git",
        ".svn",
        ".hg",
        "__pycache__",
        "node_modules",
    }
)


@dataclass(frozen=True)
class ScanOptions:
    root: Path | str
    days_unused: int = 365
    min_size_bytes: int = 0
    extension_filter: tuple[str, ...] = ()
    age_basis: str = "modified"
    protected_paths: tuple[Path | str, ...] = ()
    protected_extensions: tuple[str, ...] = ()
    skip_hidden: bool = True
    skip_system_locations: bool = True
    max_results: int = 50_000


@dataclass(frozen=True)
class FileCandidate:
    path: Path
    size: int
    accessed_at: float
    modified_at: float
    created_at: float
    item_type: str = "Fichier"
    folder_file_count: int = 0
    folder_dir_count: int = 0
    folder_hint: str = ""
    display_name: str = ""
    launch_command: tuple[str, ...] = ()
    launch_cwd: str = ""
    source_hint: str = ""
    duplicate_group: int = 0
    duplicate_hash: str = ""

    @property
    def last_activity_at(self) -> float:
        return max(self.accessed_at, self.modified_at)

    @property
    def extension(self) -> str:
        return self.path.suffix.lower()


@dataclass
class ScanStats:
    scanned_files: int = 0
    hashed_files: int = 0
    matched_files: int = 0
    matched_size_bytes: int = 0
    duplicate_groups: int = 0
    skipped_dirs: int = 0
    skipped_files: int = 0
    denied_dirs: int = 0
    errors: int = 0
    hit_limit: bool = False
    cancelled: bool = False


ProgressCallback = Callable[[ScanStats, Path], None]
CancelCallback = Callable[[], bool]


def normalize_extensions(value: str | Iterable[str]) -> tuple[str, ...]:
    if isinstance(value, str):
        raw_parts = re.split(r"[\s,;]+", value.strip())
    else:
        raw_parts = list(value)

    normalized: list[str] = []
    seen: set[str] = set()
    for raw in raw_parts:
        item = str(raw).strip().lower()
        if not item:
            continue
        if not item.startswith("."):
            item = f".{item}"
        if item not in seen:
            normalized.append(item)
            seen.add(item)
    return tuple(normalized)


def format_bytes(size: int) -> str:
    value = float(size)
    for unit in ("o", "Ko", "Mo", "Go", "To"):
        if value < 1024 or unit == "To":
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} To"


def scan_for_unused_files(
    options: ScanOptions,
    progress_callback: ProgressCallback | None = None,
    should_cancel: CancelCallback | None = None,
) -> tuple[list[FileCandidate], ScanStats]:
    root = Path(options.root).expanduser()
    root = root.resolve(strict=False)

    if not root.exists():
        raise FileNotFoundError(f"Dossier introuvable: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Ce chemin n'est pas un dossier: {root}")
    if options.days_unused < 0:
        raise ValueError("Le nombre de jours doit etre positif.")
    if options.min_size_bytes < 0:
        raise ValueError("La taille minimale doit etre positive.")
    if options.age_basis not in AGE_BASIS_VALUES:
        raise ValueError("La date utilisee doit etre: activity, modified ou accessed.")

    cutoff = time.time() - (options.days_unused * 24 * 60 * 60)
    extension_filter = normalize_extensions(options.extension_filter)
    protected_paths = _normalize_protected_paths(options.protected_paths)
    protected_extensions = normalize_extensions(options.protected_extensions)
    system_roots = _known_system_roots() if options.skip_system_locations else ()

    stats = ScanStats()
    if _is_protected_path(root, protected_paths):
        stats.skipped_dirs = 1
        return [], stats

    candidates: list[FileCandidate] = []
    stack: list[Path] = [root]
    last_progress = time.monotonic()

    while stack:
        if should_cancel and should_cancel():
            stats.cancelled = True
            break

        current = stack.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    if should_cancel and should_cancel():
                        stats.cancelled = True
                        break

                    try:
                        if entry.is_dir(follow_symlinks=False):
                            directory = Path(entry.path)
                            if _should_skip_directory(entry, directory, options, system_roots, protected_paths):
                                stats.skipped_dirs += 1
                            else:
                                stack.append(directory)
                            continue

                        if not entry.is_file(follow_symlinks=False):
                            stats.skipped_files += 1
                            continue

                        stats.scanned_files += 1
                        file_path = Path(entry.path)
                        stat_result = entry.stat(follow_symlinks=False)
                        attributes = _file_attributes(stat_result)

                        if options.skip_hidden and _has_hidden_or_system_attribute(attributes):
                            stats.skipped_files += 1
                            continue
                        if _is_reparse_point(attributes):
                            stats.skipped_files += 1
                            continue
                        if _is_protected_path(file_path, protected_paths):
                            stats.skipped_files += 1
                            continue
                        if protected_extensions and file_path.suffix.lower() in protected_extensions:
                            stats.skipped_files += 1
                            continue
                        if extension_filter and file_path.suffix.lower() not in extension_filter:
                            continue
                        if stat_result.st_size < options.min_size_bytes:
                            continue

                        retained_time = _stat_age_timestamp(stat_result, options.age_basis)
                        if retained_time <= cutoff:
                            candidates.append(
                                FileCandidate(
                                    path=file_path,
                                    size=stat_result.st_size,
                                    accessed_at=stat_result.st_atime,
                                    modified_at=stat_result.st_mtime,
                                    created_at=stat_result.st_ctime,
                                )
                            )
                            stats.matched_files += 1
                            stats.matched_size_bytes += stat_result.st_size

                            if len(candidates) >= options.max_results:
                                stats.hit_limit = True
                                break

                    except PermissionError:
                        stats.errors += 1
                    except OSError:
                        stats.errors += 1

                    now = time.monotonic()
                    if progress_callback and (
                        stats.scanned_files % 250 == 0 or now - last_progress > 0.5
                    ):
                        progress_callback(stats, current)
                        last_progress = now

                if stats.cancelled or stats.hit_limit:
                    break
        except PermissionError:
            stats.denied_dirs += 1
        except OSError:
            stats.errors += 1

    candidates.sort(key=lambda item: (item.size, -_candidate_age_timestamp(item, options.age_basis)), reverse=True)
    if progress_callback:
        progress_callback(stats, root)
    return candidates, stats


def scan_for_duplicate_files(
    options: ScanOptions,
    progress_callback: ProgressCallback | None = None,
    should_cancel: CancelCallback | None = None,
) -> tuple[list[FileCandidate], ScanStats]:
    root = Path(options.root).expanduser()
    root = root.resolve(strict=False)

    if not root.exists():
        raise FileNotFoundError(f"Dossier introuvable: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Ce chemin n'est pas un dossier: {root}")
    if options.min_size_bytes < 0:
        raise ValueError("La taille minimale doit etre positive.")

    extension_filter = normalize_extensions(options.extension_filter)
    protected_paths = _normalize_protected_paths(options.protected_paths)
    protected_extensions = normalize_extensions(options.protected_extensions)
    system_roots = _known_system_roots() if options.skip_system_locations else ()

    stats = ScanStats()
    if _is_protected_path(root, protected_paths):
        stats.skipped_dirs = 1
        return [], stats

    by_size: dict[int, list[FileCandidate]] = defaultdict(list)
    candidate_count = 0
    stack: list[Path] = [root]
    last_progress = time.monotonic()

    while stack:
        if should_cancel and should_cancel():
            stats.cancelled = True
            break

        current = stack.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    if should_cancel and should_cancel():
                        stats.cancelled = True
                        break

                    try:
                        if entry.is_dir(follow_symlinks=False):
                            directory = Path(entry.path)
                            if _should_skip_directory(entry, directory, options, system_roots, protected_paths):
                                stats.skipped_dirs += 1
                            else:
                                stack.append(directory)
                            continue

                        if not entry.is_file(follow_symlinks=False):
                            stats.skipped_files += 1
                            continue

                        stats.scanned_files += 1
                        file_path = Path(entry.path)
                        stat_result = entry.stat(follow_symlinks=False)
                        attributes = _file_attributes(stat_result)

                        if options.skip_hidden and _has_hidden_or_system_attribute(attributes):
                            stats.skipped_files += 1
                            continue
                        if _is_reparse_point(attributes):
                            stats.skipped_files += 1
                            continue
                        if _is_protected_path(file_path, protected_paths):
                            stats.skipped_files += 1
                            continue
                        if protected_extensions and file_path.suffix.lower() in protected_extensions:
                            stats.skipped_files += 1
                            continue
                        if extension_filter and file_path.suffix.lower() not in extension_filter:
                            continue
                        if stat_result.st_size < options.min_size_bytes:
                            continue

                        by_size[stat_result.st_size].append(
                            FileCandidate(
                                path=file_path,
                                size=stat_result.st_size,
                                accessed_at=stat_result.st_atime,
                                modified_at=stat_result.st_mtime,
                                created_at=stat_result.st_ctime,
                            )
                        )
                        candidate_count += 1
                        if candidate_count >= options.max_results:
                            stats.hit_limit = True
                            break

                    except PermissionError:
                        stats.errors += 1
                    except OSError:
                        stats.errors += 1

                    now = time.monotonic()
                    if progress_callback and (
                        stats.scanned_files % 250 == 0 or now - last_progress > 0.5
                    ):
                        progress_callback(stats, current)
                        last_progress = now

                if stats.cancelled or stats.hit_limit:
                    break
        except PermissionError:
            stats.denied_dirs += 1
        except OSError:
            stats.errors += 1

    duplicate_groups: list[list[FileCandidate]] = []
    same_size_groups = [group for group in by_size.values() if len(group) > 1]

    for same_size_group in same_size_groups:
        if should_cancel and should_cancel():
            stats.cancelled = True
            break

        by_hash: dict[str, list[FileCandidate]] = defaultdict(list)
        for candidate in same_size_group:
            if should_cancel and should_cancel():
                stats.cancelled = True
                break

            try:
                digest = _sha256_file(candidate.path)
            except OSError:
                stats.errors += 1
                continue

            stats.hashed_files += 1
            by_hash[digest].append(replace(candidate, duplicate_hash=digest))

            now = time.monotonic()
            if progress_callback and (stats.hashed_files % 25 == 0 or now - last_progress > 0.5):
                progress_callback(stats, candidate.path.parent)
                last_progress = now

        for duplicates in by_hash.values():
            if len(duplicates) > 1:
                duplicate_groups.append(
                    sorted(duplicates, key=lambda item: (str(item.path.parent).lower(), item.path.name.lower()))
                )

    duplicate_groups.sort(key=lambda group: (-group[0].size, str(group[0].path).lower()))

    results: list[FileCandidate] = []
    for group_id, group in enumerate(duplicate_groups, start=1):
        if len(results) + len(group) > options.max_results:
            stats.hit_limit = True
            break
        stats.duplicate_groups += 1
        stats.matched_size_bytes += group[0].size * (len(group) - 1)
        results.extend(replace(candidate, duplicate_group=group_id) for candidate in group)

    stats.matched_files = len(results)
    if progress_callback:
        progress_callback(stats, root)
    return results, stats


def scan_for_forgotten_installers(
    options: ScanOptions,
    progress_callback: ProgressCallback | None = None,
    should_cancel: CancelCallback | None = None,
) -> tuple[list[FileCandidate], ScanStats]:
    root = Path(options.root).expanduser()
    root = root.resolve(strict=False)

    if not root.exists():
        raise FileNotFoundError(f"Dossier introuvable: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Ce chemin n'est pas un dossier: {root}")
    if options.days_unused < 0:
        raise ValueError("Le nombre de jours doit etre positif.")
    if options.min_size_bytes < 0:
        raise ValueError("La taille minimale doit etre positive.")
    if options.age_basis not in AGE_BASIS_VALUES:
        raise ValueError("La date utilisee doit etre: activity, modified ou accessed.")

    cutoff = time.time() - (options.days_unused * 24 * 60 * 60)
    extension_filter = normalize_extensions(options.extension_filter)
    protected_paths = _normalize_protected_paths(options.protected_paths)
    protected_extensions = normalize_extensions(options.protected_extensions)
    system_roots = _known_system_roots() if options.skip_system_locations else ()

    stats = ScanStats()
    if _is_protected_path(root, protected_paths):
        stats.skipped_dirs = 1
        return [], stats

    candidates: list[FileCandidate] = []
    stack: list[Path] = [root]
    last_progress = time.monotonic()

    while stack:
        if should_cancel and should_cancel():
            stats.cancelled = True
            break

        current = stack.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    if should_cancel and should_cancel():
                        stats.cancelled = True
                        break

                    try:
                        if entry.is_dir(follow_symlinks=False):
                            directory = Path(entry.path)
                            if _should_skip_directory(entry, directory, options, system_roots, protected_paths):
                                stats.skipped_dirs += 1
                            else:
                                stack.append(directory)
                            continue

                        if not entry.is_file(follow_symlinks=False):
                            stats.skipped_files += 1
                            continue

                        stats.scanned_files += 1
                        file_path = Path(entry.path)
                        stat_result = entry.stat(follow_symlinks=False)
                        attributes = _file_attributes(stat_result)
                        suffix = file_path.suffix.lower()

                        if options.skip_hidden and _has_hidden_or_system_attribute(attributes):
                            stats.skipped_files += 1
                            continue
                        if _is_reparse_point(attributes):
                            stats.skipped_files += 1
                            continue
                        if _is_protected_path(file_path, protected_paths):
                            stats.skipped_files += 1
                            continue
                        if protected_extensions and suffix in protected_extensions:
                            stats.skipped_files += 1
                            continue
                        if suffix not in FORGOTTEN_INSTALLER_EXTENSIONS:
                            continue
                        if extension_filter and suffix not in extension_filter:
                            continue
                        if stat_result.st_size < options.min_size_bytes:
                            continue
                        if not _is_downloads_path(file_path):
                            continue

                        retained_time = _stat_age_timestamp(stat_result, options.age_basis)
                        if retained_time <= cutoff:
                            candidates.append(
                                FileCandidate(
                                    path=file_path,
                                    size=stat_result.st_size,
                                    accessed_at=stat_result.st_atime,
                                    modified_at=stat_result.st_mtime,
                                    created_at=stat_result.st_ctime,
                                    item_type="Installateur",
                                    folder_hint=_installer_hint(file_path),
                                )
                            )
                            stats.matched_files += 1
                            stats.matched_size_bytes += stat_result.st_size

                            if len(candidates) >= options.max_results:
                                stats.hit_limit = True
                                break

                    except PermissionError:
                        stats.errors += 1
                    except OSError:
                        stats.errors += 1

                    now = time.monotonic()
                    if progress_callback and (
                        stats.scanned_files % 250 == 0 or now - last_progress > 0.5
                    ):
                        progress_callback(stats, current)
                        last_progress = now

                if stats.cancelled or stats.hit_limit:
                    break
        except PermissionError:
            stats.denied_dirs += 1
        except OSError:
            stats.errors += 1

    candidates.sort(key=lambda item: (item.size, -_candidate_age_timestamp(item, options.age_basis)), reverse=True)
    if progress_callback:
        progress_callback(stats, root)
    return candidates, stats


def scan_for_uninstallers(
    options: ScanOptions,
    progress_callback: ProgressCallback | None = None,
    should_cancel: CancelCallback | None = None,
) -> tuple[list[FileCandidate], ScanStats]:
    root = Path(options.root).expanduser()
    root = root.resolve(strict=False)

    if not root.exists():
        raise FileNotFoundError(f"Dossier introuvable: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Ce chemin n'est pas un dossier: {root}")

    protected_paths = _normalize_protected_paths(options.protected_paths)
    protected_extensions = normalize_extensions(options.protected_extensions)

    stats = ScanStats()
    if _is_protected_path(root, protected_paths):
        stats.skipped_dirs = 1
        return [], stats

    candidates: list[FileCandidate] = []
    seen: set[str] = set()
    for registry_candidate in _registry_uninstaller_candidates(root, protected_paths, options):
        key = _uninstaller_seen_key(registry_candidate)
        if key in seen:
            continue
        seen.add(key)
        candidates.append(registry_candidate)
        stats.matched_files += 1
        stats.matched_size_bytes += registry_candidate.size
        if len(candidates) >= options.max_results:
            stats.hit_limit = True
            break

    stack: list[Path] = [root]
    last_progress = time.monotonic()

    while stack and not stats.hit_limit:
        if should_cancel and should_cancel():
            stats.cancelled = True
            break

        current = stack.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    if should_cancel and should_cancel():
                        stats.cancelled = True
                        break

                    try:
                        entry_path = Path(entry.path)
                        if entry.is_dir(follow_symlinks=False):
                            if _should_skip_uninstaller_directory(entry, entry_path, options, protected_paths):
                                stats.skipped_dirs += 1
                            else:
                                stack.append(entry_path)
                            continue

                        if not entry.is_file(follow_symlinks=False):
                            stats.skipped_files += 1
                            continue

                        stats.scanned_files += 1
                        stat_result = entry.stat(follow_symlinks=False)
                        attributes = _file_attributes(stat_result)

                        if _is_reparse_point(attributes):
                            stats.skipped_files += 1
                            continue
                        if options.skip_hidden and _has_hidden_or_system_attribute(attributes):
                            stats.skipped_files += 1
                            continue
                        if _is_protected_path(entry_path, protected_paths):
                            stats.skipped_files += 1
                            continue
                        if protected_extensions and entry_path.suffix.lower() in protected_extensions:
                            stats.skipped_files += 1
                            continue
                        if not _is_uninstaller_file_name(entry.name):
                            continue

                        key = _path_seen_key(entry_path)
                        if key in seen:
                            continue
                        seen.add(key)
                        app_name = _uninstaller_app_name(entry_path)

                        candidates.append(
                            FileCandidate(
                                path=entry_path,
                                size=stat_result.st_size,
                                accessed_at=stat_result.st_atime,
                                modified_at=stat_result.st_mtime,
                                created_at=stat_result.st_ctime,
                                item_type="Désinstallateur",
                                folder_hint=app_name,
                                display_name=app_name,
                                launch_command=(str(entry_path),),
                                launch_cwd=str(entry_path.parent),
                                source_hint="Fichier",
                            )
                        )
                        stats.matched_files += 1
                        stats.matched_size_bytes += stat_result.st_size

                        if len(candidates) >= options.max_results:
                            stats.hit_limit = True
                            break

                    except PermissionError:
                        stats.errors += 1
                    except OSError:
                        stats.errors += 1

                    now = time.monotonic()
                    if progress_callback and (
                        stats.scanned_files % 250 == 0 or now - last_progress > 0.5
                    ):
                        progress_callback(stats, current)
                        last_progress = now

                if stats.cancelled or stats.hit_limit:
                    break
        except PermissionError:
            stats.denied_dirs += 1
        except OSError:
            stats.errors += 1

    candidates.sort(key=lambda item: (item.folder_hint.casefold(), str(item.path.parent).casefold()))
    if progress_callback:
        progress_callback(stats, root)
    return candidates, stats


def scan_for_large_folders(
    options: ScanOptions,
    progress_callback: ProgressCallback | None = None,
    should_cancel: CancelCallback | None = None,
) -> tuple[list[FileCandidate], ScanStats]:
    root = Path(options.root).expanduser()
    root = root.resolve(strict=False)

    if not root.exists():
        raise FileNotFoundError(f"Dossier introuvable: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Ce chemin n'est pas un dossier: {root}")
    if options.min_size_bytes < 0:
        raise ValueError("La taille minimale doit etre positive.")

    protected_paths = _normalize_protected_paths(options.protected_paths)
    protected_extensions = normalize_extensions(options.protected_extensions)
    system_roots = _known_system_roots() if options.skip_system_locations else ()
    cutoff = time.time() - (options.days_unused * 24 * 60 * 60)

    stats = ScanStats()
    if _is_protected_path(root, protected_paths):
        stats.skipped_dirs = 1
        return [], stats

    folder_sizes: dict[Path, int] = defaultdict(int)
    folder_file_counts: dict[Path, int] = defaultdict(int)
    folder_dir_counts: dict[Path, int] = defaultdict(int)
    folder_accessed: dict[Path, float] = defaultdict(float)
    folder_modified: dict[Path, float] = defaultdict(float)
    folder_created: dict[Path, float] = defaultdict(float)
    folder_parents: dict[Path, Path | None] = {root: None}

    stack: list[tuple[Path, bool]] = [(root, False)]
    last_progress = time.monotonic()

    while stack:
        if should_cancel and should_cancel():
            stats.cancelled = True
            break

        current, visited = stack.pop()
        if visited:
            parent = folder_parents.get(current)
            if parent is not None:
                folder_sizes[parent] += folder_sizes[current]
                folder_file_counts[parent] += folder_file_counts[current]
                folder_dir_counts[parent] += folder_dir_counts[current] + 1
                folder_accessed[parent] = max(folder_accessed[parent], folder_accessed[current])
                folder_modified[parent] = max(folder_modified[parent], folder_modified[current])
                created = folder_created[current]
                if created and (not folder_created[parent] or created < folder_created[parent]):
                    folder_created[parent] = created
            continue

        stack.append((current, True))
        try:
            current_stat = current.stat()
            folder_accessed[current] = max(folder_accessed[current], current_stat.st_atime)
            folder_modified[current] = max(folder_modified[current], current_stat.st_mtime)
            folder_created[current] = current_stat.st_ctime
        except OSError:
            stats.errors += 1

        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    if should_cancel and should_cancel():
                        stats.cancelled = True
                        break

                    try:
                        entry_path = Path(entry.path)
                        if entry.is_dir(follow_symlinks=False):
                            if _should_skip_folder_size_directory(entry, entry_path, options, system_roots, protected_paths):
                                stats.skipped_dirs += 1
                                continue
                            folder_parents[entry_path] = current
                            stack.append((entry_path, False))
                            continue

                        if not entry.is_file(follow_symlinks=False):
                            stats.skipped_files += 1
                            continue

                        stats.scanned_files += 1
                        stat_result = entry.stat(follow_symlinks=False)
                        attributes = _file_attributes(stat_result)
                        if options.skip_hidden and _has_hidden_or_system_attribute(attributes):
                            stats.skipped_files += 1
                            continue
                        if _is_reparse_point(attributes):
                            stats.skipped_files += 1
                            continue
                        if _is_protected_path(entry_path, protected_paths):
                            stats.skipped_files += 1
                            continue
                        if protected_extensions and entry_path.suffix.lower() in protected_extensions:
                            stats.skipped_files += 1
                            continue

                        folder_sizes[current] += stat_result.st_size
                        folder_file_counts[current] += 1
                        folder_accessed[current] = max(folder_accessed[current], stat_result.st_atime)
                        folder_modified[current] = max(folder_modified[current], stat_result.st_mtime)
                        if not folder_created[current] or stat_result.st_ctime < folder_created[current]:
                            folder_created[current] = stat_result.st_ctime
                    except PermissionError:
                        stats.errors += 1
                    except OSError:
                        stats.errors += 1

                    now = time.monotonic()
                    if progress_callback and (
                        stats.scanned_files % 250 == 0 or now - last_progress > 0.5
                    ):
                        progress_callback(stats, current)
                        last_progress = now

                if stats.cancelled:
                    break
        except PermissionError:
            stats.denied_dirs += 1
        except OSError:
            stats.errors += 1

    candidates: list[FileCandidate] = []
    for folder, total_size in folder_sizes.items():
        if folder == root:
            continue
        if total_size < options.min_size_bytes:
            continue

        retained_time = max(folder_accessed[folder], folder_modified[folder])
        hint = _folder_hint(folder, retained_time <= cutoff)
        candidates.append(
            FileCandidate(
                path=folder,
                size=total_size,
                accessed_at=folder_accessed[folder],
                modified_at=folder_modified[folder],
                created_at=folder_created[folder] or folder_modified[folder] or folder_accessed[folder],
                item_type="Dossier",
                folder_file_count=folder_file_counts[folder],
                folder_dir_count=folder_dir_counts[folder],
                folder_hint=hint,
            )
        )

    candidates.sort(key=lambda item: (item.size, item.folder_file_count, str(item.path).lower()), reverse=True)
    if len(candidates) > options.max_results:
        candidates = candidates[: options.max_results]
        stats.hit_limit = True

    stats.matched_files = len(candidates)
    stats.matched_size_bytes = sum(item.size for item in candidates)
    if progress_callback:
        progress_callback(stats, root)
    return candidates, stats


def _should_skip_directory(
    entry: os.DirEntry[str],
    directory: Path,
    options: ScanOptions,
    system_roots: tuple[Path, ...],
    protected_paths: tuple[Path, ...],
) -> bool:
    try:
        stat_result = entry.stat(follow_symlinks=False)
    except OSError:
        return True

    attributes = _file_attributes(stat_result)
    if _is_reparse_point(attributes):
        return True
    if _is_protected_path(directory, protected_paths):
        return True
    if options.skip_hidden and _has_hidden_or_system_attribute(attributes):
        return True
    if options.skip_system_locations and directory.name.casefold() in DEFAULT_EXCLUDED_DIR_NAMES_NORMALIZED:
        return True
    if options.skip_system_locations and any(_same_or_child(directory, root) for root in system_roots):
        return True
    return False


def _should_skip_folder_size_directory(
    entry: os.DirEntry[str],
    directory: Path,
    options: ScanOptions,
    system_roots: tuple[Path, ...],
    protected_paths: tuple[Path, ...],
) -> bool:
    try:
        stat_result = entry.stat(follow_symlinks=False)
    except OSError:
        return True

    attributes = _file_attributes(stat_result)
    if _is_reparse_point(attributes):
        return True
    if _is_protected_path(directory, protected_paths):
        return True
    if options.skip_hidden and _has_hidden_or_system_attribute(attributes):
        return True
    if options.skip_system_locations and directory.name.casefold() in {
        "$recycle.bin",
        "system volume information",
        "windows",
        "system32",
        "syswow64",
        "winsxs",
        "program files",
        "program files (x86)",
        "programdata",
    }:
        return True
    if options.skip_system_locations and any(_same_or_child(directory, root) for root in system_roots):
        return True
    return False


def _should_skip_uninstaller_directory(
    entry: os.DirEntry[str],
    directory: Path,
    options: ScanOptions,
    protected_paths: tuple[Path, ...],
) -> bool:
    try:
        stat_result = entry.stat(follow_symlinks=False)
    except OSError:
        return True

    attributes = _file_attributes(stat_result)
    if _is_reparse_point(attributes):
        return True
    if _is_protected_path(directory, protected_paths):
        return True
    if options.skip_system_locations and directory.name.casefold() in UNINSTALLER_EXCLUDED_DIR_NAMES:
        return True
    return False


def _registry_uninstaller_candidates(
    root: Path,
    protected_paths: tuple[Path, ...],
    options: ScanOptions,
) -> list[FileCandidate]:
    if os.name != "nt":
        return []

    try:
        import winreg
    except ImportError:
        return []

    registry_roots = (
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
    )
    candidates: list[FileCandidate] = []

    for hive, subkey in registry_roots:
        try:
            with winreg.OpenKey(hive, subkey) as uninstall_key:
                count, _, _ = winreg.QueryInfoKey(uninstall_key)
                for index in range(count):
                    try:
                        app_key_name = winreg.EnumKey(uninstall_key, index)
                        with winreg.OpenKey(uninstall_key, app_key_name) as app_key:
                            candidate = _registry_uninstaller_candidate(
                                app_key,
                                app_key_name,
                                root,
                                protected_paths,
                                options,
                            )
                            if candidate:
                                candidates.append(candidate)
                    except OSError:
                        continue
        except OSError:
            continue

    return candidates


def _registry_uninstaller_candidate(
    app_key: object,
    app_key_name: str,
    root: Path,
    protected_paths: tuple[Path, ...],
    options: ScanOptions,
) -> FileCandidate | None:
    display_name = _registry_value(app_key, "DisplayName")
    uninstall_string = _registry_value(app_key, "UninstallString")
    if not display_name or not uninstall_string:
        return None
    if _registry_int_value(app_key, "SystemComponent") == 1:
        return None

    command = _split_windows_command(uninstall_string)
    if not command:
        return None

    exe_path = _command_executable_path(command[0])
    if exe_path and _is_protected_path(exe_path, protected_paths):
        return None
    if exe_path and not _registry_candidate_in_scope(root, exe_path):
        return None
    if not exe_path and not _is_drive_root(root):
        return None

    size = _registry_int_value(app_key, "EstimatedSize") * 1024
    if exe_path and exe_path.exists():
        try:
            stat_result = exe_path.stat()
        except OSError:
            stat_result = None
        if stat_result:
            size = size or stat_result.st_size
            accessed_at = stat_result.st_atime
            modified_at = stat_result.st_mtime
            created_at = stat_result.st_ctime
        else:
            accessed_at = modified_at = created_at = time.time()
    else:
        accessed_at = modified_at = created_at = time.time()

    cwd = str(exe_path.parent) if exe_path and exe_path.parent != Path(".") else ""
    return FileCandidate(
        path=exe_path or Path(command[0]),
        size=size,
        accessed_at=accessed_at,
        modified_at=modified_at,
        created_at=created_at,
        item_type="Désinstallateur",
        folder_hint=str(display_name),
        display_name=str(display_name),
        launch_command=command,
        launch_cwd=cwd,
        source_hint=f"Registre: {app_key_name}",
    )


def _registry_value(app_key: object, name: str) -> object:
    try:
        import winreg

        value, _kind = winreg.QueryValueEx(app_key, name)
        return value
    except (OSError, ImportError):
        return ""


def _registry_int_value(app_key: object, name: str) -> int:
    value = _registry_value(app_key, name)
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _registry_candidate_in_scope(root: Path, exe_path: Path) -> bool:
    return _is_drive_root(root) or _same_or_child(exe_path, root)


def _is_drive_root(path: Path) -> bool:
    resolved = path.resolve(strict=False)
    return bool(resolved.drive) and resolved.parent == resolved


def _split_windows_command(command: object) -> tuple[str, ...]:
    text = str(command).strip()
    if not text:
        return ()
    if os.name == "nt":
        try:
            import ctypes

            command_line_to_argv = ctypes.windll.shell32.CommandLineToArgvW
            command_line_to_argv.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_int)]
            command_line_to_argv.restype = ctypes.POINTER(ctypes.c_wchar_p)
            argc = ctypes.c_int()
            argv = command_line_to_argv(text, ctypes.byref(argc))
            if not argv:
                return ()
            try:
                return tuple(argv[index] for index in range(argc.value))
            finally:
                ctypes.windll.kernel32.LocalFree(argv)
        except (AttributeError, OSError, ValueError):
            pass

    import shlex

    try:
        parts = shlex.split(text, posix=False)
    except ValueError:
        return (text,)
    return tuple(part.strip('"') for part in parts if part)


def _command_executable_path(command_head: str) -> Path | None:
    if not command_head:
        return None
    expanded = os.path.expandvars(command_head.strip().strip('"'))
    path = Path(expanded)
    if path.is_absolute() or path.parent != Path("."):
        return path.resolve(strict=False)
    return None


def _is_uninstaller_file_name(name: str) -> bool:
    normalized = name.casefold()
    if normalized in UNINSTALLER_FILE_NAMES:
        return True
    return any(pattern.fullmatch(normalized) for pattern in UNINSTALLER_FILE_PATTERNS)


def _uninstaller_seen_key(candidate: FileCandidate) -> str:
    if candidate.path and candidate.path.is_absolute():
        return _path_seen_key(candidate.path)
    if candidate.launch_command:
        return os.path.normcase(" ".join(candidate.launch_command))
    return os.path.normcase(candidate.display_name or str(candidate.path))


def _path_seen_key(path: Path) -> str:
    return os.path.normcase(os.fspath(path.resolve(strict=False)))


def _folder_hint(path: Path, is_old: bool) -> str:
    names = {part.casefold() for part in path.parts}
    folder_name = path.name.casefold()

    if names & {"cache", "caches", "code cache", "gpucache", "dawncache", "indexeddb", "service worker"}:
        return "Cache"
    if names & {"node_modules", ".gradle", ".m2", ".npm", ".nuget", ".pnpm-store", ".cargo", ".rustup", "venv", ".venv"}:
        return "Dépendances"
    if names & {"build", "dist", "out", "output", "export", "exports", "release", "releases"}:
        return "Export"
    if any(marker in folder_name for marker in ("backup", "archive", "ancien", "old")):
        return "Ancien projet"
    if is_old:
        return "Ancien"
    return "Gros dossier"


def _uninstaller_app_name(path: Path) -> str:
    parent = path.parent
    if parent.name:
        return parent.name
    return path.stem


def _is_downloads_path(path: Path) -> bool:
    return any(part.casefold() in DOWNLOAD_DIR_NAMES_NORMALIZED for part in path.parts)


def _installer_hint(path: Path) -> str:
    suffix = path.suffix.casefold()
    name = path.stem.casefold()

    if suffix in INSTALLER_IMAGE_EXTENSIONS:
        return "Image disque"
    if suffix in INSTALLER_ARCHIVE_EXTENSIONS:
        if any(marker in name for marker in ("setup", "install", "installer", "driver", "update")):
            return "Archive d'installation"
        return "Archive"
    if suffix in INSTALLER_BINARY_EXTENSIONS:
        if any(marker in name for marker in ("driver", "pilote")):
            return "Pilote"
        if any(marker in name for marker in ("update", "upgrade", "maj")):
            return "Mise à jour"
        return "Installateur"
    return "Installateur"


def _known_system_roots() -> tuple[Path, ...]:
    candidates = [
        os.environ.get("SystemRoot"),
        os.environ.get("ProgramFiles"),
        os.environ.get("ProgramFiles(x86)"),
        os.environ.get("ProgramData"),
    ]
    roots: list[Path] = []
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate).resolve(strict=False)
        if path not in roots:
            roots.append(path)
    return tuple(roots)


def _file_attributes(stat_result: os.stat_result) -> int:
    return int(getattr(stat_result, "st_file_attributes", 0) or 0)


def _has_hidden_or_system_attribute(attributes: int) -> bool:
    return bool(attributes & (FILE_ATTRIBUTE_HIDDEN | FILE_ATTRIBUTE_SYSTEM))


def _is_reparse_point(attributes: int) -> bool:
    return bool(attributes & FILE_ATTRIBUTE_REPARSE_POINT)


def _same_or_child(path: Path, parent: Path) -> bool:
    try:
        path_resolved = path.resolve(strict=False)
        parent_resolved = parent.resolve(strict=False)
        return os.path.commonpath([os.fspath(path_resolved), os.fspath(parent_resolved)]) == os.fspath(parent_resolved)
    except (OSError, ValueError):
        return False


def _normalize_protected_paths(paths: Iterable[Path | str]) -> tuple[Path, ...]:
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


def _is_protected_path(path: Path, protected_paths: tuple[Path, ...]) -> bool:
    return any(_same_or_child(path, protected_path) for protected_path in protected_paths)


def _stat_age_timestamp(stat_result: os.stat_result, age_basis: str) -> float:
    if age_basis == "accessed":
        return stat_result.st_atime
    if age_basis == "activity":
        return max(stat_result.st_atime, stat_result.st_mtime)
    return stat_result.st_mtime


def _candidate_age_timestamp(candidate: FileCandidate, age_basis: str) -> float:
    if age_basis == "accessed":
        return candidate.accessed_at
    if age_basis == "activity":
        return candidate.last_activity_at
    return candidate.modified_at


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
