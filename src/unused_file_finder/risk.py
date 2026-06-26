from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RiskAssessment:
    score: int
    label: str
    reason: str


@dataclass(frozen=True)
class ActionRecommendation:
    rank: int
    label: str
    reason: str


LOW = RiskAssessment(0, "Faible", "Fichier temporaire, journal ou archive peu liée au fonctionnement système.")
MEDIUM = RiskAssessment(1, "Moyen", "Fichier utilisateur ou projet : vérifier le contenu avant suppression.")
HIGH = RiskAssessment(2, "Élevé", "Peut appartenir à une application, un cache actif, une configuration ou des données.")
CRITICAL = RiskAssessment(3, "Critique", "Fichier Windows, pilote, exécutable ou bibliothèque : ne pas supprimer directement.")

SUPPRIMABLE = ActionRecommendation(0, "Supprimable", "Faible risque : peut aller à la Corbeille après vérification rapide.")
QUARANTINE = ActionRecommendation(1, "Quarantaine", "À isoler d'abord pour tester quelques jours avant suppression.")
KEEP = ActionRecommendation(2, "Garder", "À conserver : suppression directe déconseillée.")
WINDOWS_CLEANUP = ActionRecommendation(
    3,
    "Nettoyer via Windows",
    "À supprimer avec l'outil de nettoyage Windows plutôt que fichier par fichier.",
)

LOW_RISK_EXTENSIONS = {
    ".bak",
    ".cache",
    ".chk",
    ".crdownload",
    ".dmp",
    ".etl",
    ".log",
    ".old",
    ".part",
    ".temp",
    ".tmp",
}

ARCHIVE_EXTENSIONS = {
    ".7z",
    ".cab",
    ".gz",
    ".rar",
    ".tar",
    ".tgz",
    ".zip",
}

USER_DATA_EXTENSIONS = {
    ".aac",
    ".avi",
    ".bmp",
    ".csv",
    ".doc",
    ".docx",
    ".flac",
    ".gif",
    ".heic",
    ".jpeg",
    ".jpg",
    ".m4a",
    ".mkv",
    ".mov",
    ".mp3",
    ".mp4",
    ".odp",
    ".ods",
    ".odt",
    ".pdf",
    ".png",
    ".ppt",
    ".pptx",
    ".psd",
    ".raw",
    ".rtf",
    ".svg",
    ".tif",
    ".tiff",
    ".txt",
    ".wav",
    ".webm",
    ".webp",
    ".xls",
    ".xlsx",
}

CRITICAL_EXTENSIONS = {
    ".bat",
    ".cmd",
    ".com",
    ".dll",
    ".drv",
    ".efi",
    ".exe",
    ".msi",
    ".msp",
    ".mui",
    ".ocx",
    ".ps1",
    ".scr",
    ".sys",
    ".vbs",
    ".wim",
}

HIGH_RISK_EXTENSIONS = {
    ".bin",
    ".cfg",
    ".config",
    ".dat",
    ".db",
    ".ini",
    ".json",
    ".lib",
    ".pak",
    ".pdb",
    ".sqlite",
    ".sqlite3",
    ".xml",
    ".yaml",
    ".yml",
}

CRITICAL_SEGMENTS = {
    "$recycle.bin",
    "boot",
    "drivers",
    "program files",
    "program files (x86)",
    "system volume information",
    "system32",
    "syswow64",
    "windows",
    "windows.old",
    "winsxs",
}

HIGH_RISK_SEGMENTS = {
    ".android",
    ".cargo",
    ".gradle",
    ".m2",
    ".npm",
    ".nuget",
    ".pnpm-store",
    ".rustup",
    "appdata",
    "cache",
    "caches",
    "code cache",
    "gpucache",
    "indexeddb",
    "node_modules",
    "programdata",
    "service worker",
    "venv",
}


def assess_deletion_risk(path_value: str | Path) -> RiskAssessment:
    path = Path(path_value)
    segments = {part.casefold() for part in path.parts}
    suffix = path.suffix.casefold()

    if segments & CRITICAL_SEGMENTS:
        return CRITICAL
    if _same_or_child(path, _system_root()) or _same_or_child(path, _program_files()):
        return CRITICAL
    if suffix in CRITICAL_EXTENSIONS:
        return CRITICAL
    if segments & HIGH_RISK_SEGMENTS:
        return HIGH
    if suffix in HIGH_RISK_EXTENSIONS:
        return HIGH
    if suffix in LOW_RISK_EXTENSIONS:
        return LOW
    if suffix in ARCHIVE_EXTENSIONS:
        return RiskAssessment(1, "Moyen", "Archive : souvent supprimable, mais peut contenir une sauvegarde importante.")
    if suffix in USER_DATA_EXTENSIONS:
        return MEDIUM

    return MEDIUM


def recommend_action(path_value: str | Path) -> ActionRecommendation:
    path = Path(path_value)
    segments = {part.casefold() for part in path.parts}
    risk = assess_deletion_risk(path)

    if "windows.old" in segments:
        return WINDOWS_CLEANUP
    if risk.score >= CRITICAL.score:
        return KEEP
    if risk.score >= MEDIUM.score:
        return QUARANTINE
    return SUPPRIMABLE


def _system_root() -> Path:
    return Path(os.environ.get("SystemRoot", r"C:\Windows"))


def _program_files() -> Path:
    return Path(os.environ.get("ProgramFiles", r"C:\Program Files"))


def _same_or_child(path: Path, parent: Path) -> bool:
    try:
        path_resolved = path.resolve(strict=False)
        parent_resolved = parent.resolve(strict=False)
        return os.path.commonpath([os.fspath(path_resolved), os.fspath(parent_resolved)]) == os.fspath(parent_resolved)
    except (OSError, ValueError):
        return False
