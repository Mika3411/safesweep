from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


@dataclass(frozen=True)
class AnalysisProfile:
    name: str
    root: Path
    scan_mode: str
    days_unused: int
    min_size_mb: float
    extensions: tuple[str, ...] = ()
    age_basis: str = "modified"
    skip_hidden: bool = True
    skip_system_locations: bool = True
    description: str = ""


INSTALLER_EXTENSIONS = (".exe", ".msi", ".msp", ".msix", ".appx", ".zip", ".7z", ".rar", ".iso", ".img")
PHOTO_VIDEO_EXTENSIONS = (
    ".jpg",
    ".jpeg",
    ".png",
    ".heic",
    ".raw",
    ".tif",
    ".tiff",
    ".bmp",
    ".mp4",
    ".mov",
    ".mkv",
    ".avi",
    ".webm",
)
ARCHIVE_EXTENSIONS = (".zip", ".7z", ".rar", ".tar", ".gz", ".tgz", ".cab", ".iso", ".img")


def available_profiles(home: Path | None = None) -> tuple[AnalysisProfile, ...]:
    base = home or Path.home()
    return (
        AnalysisProfile(
            name="Nettoyage prudent",
            root=_documents_dir(base),
            scan_mode="unused",
            days_unused=365,
            min_size_mb=10,
            age_basis="modified",
            description="Analyse limitée aux documents, avec fichiers système et cachés ignorés.",
        ),
        AnalysisProfile(
            name="Bureau rapide",
            root=_desktop_dir(base),
            scan_mode="unused",
            days_unused=730,
            min_size_mb=0,
            age_basis="modified",
            description="Retrouve les vieux éléments du Bureau sans scanner tout le disque.",
        ),
        AnalysisProfile(
            name="Doublons exacts",
            root=_documents_dir(base),
            scan_mode="duplicates",
            days_unused=0,
            min_size_mb=1,
            age_basis="modified",
            description="Compare les fichiers par taille puis hash pour retrouver les copies identiques.",
        ),
        AnalysisProfile(
            name="Gros dossiers",
            root=base,
            scan_mode="folders",
            days_unused=0,
            min_size_mb=500,
            age_basis="activity",
            description="Mesure les dossiers volumineux pour repérer caches, exports et anciens projets.",
        ),
        AnalysisProfile(
            name="Téléchargements",
            root=_downloads_dir(base),
            scan_mode="installers",
            days_unused=90,
            min_size_mb=10,
            extensions=INSTALLER_EXTENSIONS,
            age_basis="modified",
            description="Cible les installateurs, ISO et archives oubliés dans les téléchargements.",
        ),
        AnalysisProfile(
            name="Applications désinstallables",
            root=_system_drive_root(base),
            scan_mode="uninstallers",
            days_unused=0,
            min_size_mb=0,
            age_basis="modified",
            skip_hidden=False,
            skip_system_locations=True,
            description="Recherche les applications désinstallables via le registre Windows et les fichiers uninstall/uninst.",
        ),
        AnalysisProfile(
            name="Photos/vidéos lourdes",
            root=_media_dir(base),
            scan_mode="unused",
            days_unused=180,
            min_size_mb=50,
            extensions=PHOTO_VIDEO_EXTENSIONS,
            age_basis="modified",
            description="Cherche les médias volumineux anciens dans Images/Vidéos ou le profil utilisateur.",
        ),
        AnalysisProfile(
            name="Archives anciennes",
            root=_downloads_dir(base),
            scan_mode="unused",
            days_unused=365,
            min_size_mb=20,
            extensions=ARCHIVE_EXTENSIONS,
            age_basis="modified",
            description="Cherche les anciennes archives et images disque souvent oubliées.",
        ),
    )


def profile_names(home: Path | None = None) -> tuple[str, ...]:
    return tuple(profile.name for profile in available_profiles(home))


def find_profile(name: str, home: Path | None = None) -> AnalysisProfile | None:
    return next((profile for profile in available_profiles(home) if profile.name == name), None)


def format_extensions(extensions: Sequence[str]) -> str:
    return ", ".join(extensions)


def format_min_size_mb(value: float) -> str:
    return f"{value:g}".replace(".", ",")


def _desktop_dir(home: Path) -> Path:
    return _first_existing(
        home,
        (
            home / "OneDrive" / "Bureau",
            home / "OneDrive" / "Desktop",
            home / "Bureau",
            home / "Desktop",
        ),
    )


def _downloads_dir(home: Path) -> Path:
    return _first_existing(
        home,
        (
            home / "Downloads",
            home / "Téléchargements",
            home / "Telechargements",
            home / "OneDrive" / "Téléchargements",
            home / "OneDrive" / "Downloads",
        ),
    )


def _documents_dir(home: Path) -> Path:
    return _first_existing(
        home,
        (
            home / "Documents",
            home / "OneDrive" / "Documents",
        ),
    )


def _media_dir(home: Path) -> Path:
    return _first_existing(
        home,
        (
            home / "Pictures",
            home / "Images",
            home / "OneDrive" / "Images",
            home / "OneDrive" / "Pictures",
            home / "Videos",
            home / "Vidéos",
            home / "Videos",
        ),
    )


def _system_drive_root(fallback: Path) -> Path:
    if os.name == "nt":
        drive = os.environ.get("SystemDrive", "C:")
        root = Path(f"{drive}\\")
        if root.exists():
            return root
    return fallback


def _first_existing(fallback: Path, candidates: Sequence[Path]) -> Path:
    return next((candidate for candidate in candidates if candidate.exists()), fallback)
