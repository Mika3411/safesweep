from __future__ import annotations

from pathlib import Path

from unused_file_finder.risk import assess_deletion_risk, recommend_action


def test_windows_file_is_critical() -> None:
    risk = assess_deletion_risk(Path(r"C:\Windows\System32\kernel32.dll"))

    assert risk.label == "Critique"
    assert risk.score == 3


def test_log_file_is_low_risk() -> None:
    risk = assess_deletion_risk(Path(r"C:\Users\admin\Downloads\install.log"))

    assert risk.label == "Faible"
    assert risk.score == 0


def test_appdata_config_is_high_risk() -> None:
    risk = assess_deletion_risk(Path(r"C:\Users\admin\AppData\Roaming\App\settings.json"))

    assert risk.label == "Élevé"
    assert risk.score == 2


def test_user_document_is_medium_risk() -> None:
    risk = assess_deletion_risk(Path(r"C:\Users\admin\Documents\report.pdf"))

    assert risk.label == "Moyen"
    assert risk.score == 1


def test_low_risk_file_is_recommended_as_deletable() -> None:
    recommendation = recommend_action(Path(r"C:\Users\admin\Downloads\install.log"))

    assert recommendation.label == "Supprimable"


def test_user_document_is_recommended_for_quarantine() -> None:
    recommendation = recommend_action(Path(r"C:\Users\admin\Documents\report.pdf"))

    assert recommendation.label == "Quarantaine"


def test_executable_is_recommended_to_keep() -> None:
    recommendation = recommend_action(Path(r"C:\Users\admin\Downloads\setup.exe"))

    assert recommendation.label == "Garder"


def test_windows_old_is_recommended_for_windows_cleanup() -> None:
    recommendation = recommend_action(Path(r"C:\Windows.old\Users\admin\old.txt"))

    assert recommendation.label == "Nettoyer via Windows"
