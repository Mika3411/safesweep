from __future__ import annotations

from pathlib import Path

from unused_file_finder import i18n


def test_translation_and_source_text_round_trip() -> None:
    original_language = i18n.current_language()
    try:
        i18n.set_language("en")

        assert i18n._("Nettoyage prudent") == "Careful cleanup"
        assert i18n.source_text("Careful cleanup") == "Nettoyage prudent"
        assert "English" in i18n.language_choices()
    finally:
        i18n.set_language(original_language)


def test_save_and_load_language_preference(tmp_path: Path) -> None:
    preferences_path = tmp_path / "preferences.json"

    i18n.save_language("es", preferences_path)

    assert i18n.load_language(preferences_path) == "es"
