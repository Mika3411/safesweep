from __future__ import annotations

from pathlib import Path

from unused_file_finder.profiles import available_profiles, find_profile, format_extensions, format_min_size_mb, profile_names


def test_profile_names_include_accessible_presets(tmp_path: Path) -> None:
    names = profile_names(tmp_path)

    assert "Bureau rapide" in names
    assert "Téléchargements" in names
    assert "Applications désinstallables" in names
    assert "Photos/vidéos lourdes" in names
    assert "Archives anciennes" in names
    assert "Nettoyage prudent" in names


def test_profiles_prefer_existing_localized_windows_folders(tmp_path: Path) -> None:
    desktop = tmp_path / "OneDrive" / "Bureau"
    downloads = tmp_path / "Téléchargements"
    desktop.mkdir(parents=True)
    downloads.mkdir()

    by_name = {profile.name: profile for profile in available_profiles(tmp_path)}

    assert by_name["Bureau rapide"].root == desktop
    assert by_name["Téléchargements"].root == downloads


def test_downloads_profile_targets_forgotten_installers(tmp_path: Path) -> None:
    profile = find_profile("Téléchargements", tmp_path)

    assert profile is not None
    assert profile.scan_mode == "installers"
    assert profile.days_unused == 90
    assert ".exe" in profile.extensions
    assert ".iso" in profile.extensions
    assert profile.skip_system_locations is True


def test_applications_profile_targets_uninstallers(tmp_path: Path) -> None:
    profile = find_profile("Applications désinstallables", tmp_path)

    assert profile is not None
    assert profile.scan_mode == "uninstallers"
    assert profile.days_unused == 0
    assert profile.min_size_mb == 0
    assert profile.skip_hidden is False
    assert profile.skip_system_locations is True


def test_profile_formatting_matches_gui_fields() -> None:
    assert format_extensions((".zip", ".iso")) == ".zip, .iso"
    assert format_min_size_mb(10) == "10"
    assert format_min_size_mb(0.5) == "0,5"
