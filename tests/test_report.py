from __future__ import annotations

import csv
import time
from pathlib import Path

from unused_file_finder.report import build_html_report, build_report_rows, write_csv_report
from unused_file_finder.scanner import FileCandidate


def test_report_rows_include_risk_size_reason_and_recommendation() -> None:
    timestamp = time.time() - 100
    candidate = FileCandidate(
        path=Path(r"C:\Users\admin\Downloads\install.log"),
        size=1024,
        accessed_at=timestamp,
        modified_at=timestamp,
        created_at=timestamp,
    )

    rows = build_report_rows([candidate], {candidate.path})

    assert len(rows) == 1
    row = rows[0]
    assert row.selected is True
    assert row.risk_label == "Faible"
    assert "journal" in row.risk_reason
    assert row.action_label == "Supprimable"
    assert row.size_display == "1.0 Ko"


def test_csv_report_writes_clean_headers_and_reasons(tmp_path: Path) -> None:
    timestamp = time.time() - 100
    candidate = FileCandidate(
        path=Path(r"C:\Users\admin\Documents\report.pdf"),
        size=2048,
        accessed_at=timestamp,
        modified_at=timestamp,
        created_at=timestamp,
    )
    output = tmp_path / "rapport.csv"

    write_csv_report(output, build_report_rows([candidate]))

    with output.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle, delimiter=";"))

    assert "Raison risque" in rows[0]
    assert "Action recommandée" in rows[0]
    assert rows[1][2] == "Moyen"
    assert rows[1][5] == "Quarantaine"
    assert rows[1][11] == "2.0 Ko"


def test_html_report_is_readable_and_escapes_paths() -> None:
    timestamp = time.time() - 100
    candidate = FileCandidate(
        path=Path(r"C:\Users\admin\Downloads\old<script>.log"),
        size=1024,
        accessed_at=timestamp,
        modified_at=timestamp,
        created_at=timestamp,
    )

    html = build_html_report(build_report_rows([candidate]), title="Rapport test")

    assert "Rapport test" in html
    assert "Faible" in html
    assert "Supprimable" in html
    assert "1.0 Ko" in html
    assert "&lt;script&gt;" in html
    assert "old<script>.log" not in html


def test_report_rows_label_uninstallers_as_uninstall_action() -> None:
    timestamp = time.time() - 100
    candidate = FileCandidate(
        path=Path(r"C:\Program Files\Demo App\uninstall.exe"),
        size=4096,
        accessed_at=timestamp,
        modified_at=timestamp,
        created_at=timestamp,
        item_type="Désinstallateur",
        folder_hint="Demo App",
        source_hint="Fichier",
    )

    row = build_report_rows([candidate], results_mode="uninstallers")[0]

    assert row.name == "Demo App"
    assert row.group_label == "Fichier"
    assert row.risk_label == "Élevé"
    assert row.action_label == "Désinstaller"


def test_report_rows_use_registry_display_name_for_uninstallers() -> None:
    timestamp = time.time() - 100
    candidate = FileCandidate(
        path=Path("MsiExec.exe"),
        size=0,
        accessed_at=timestamp,
        modified_at=timestamp,
        created_at=timestamp,
        item_type="Désinstallateur",
        folder_hint="GUID",
        display_name="Demo App depuis registre",
        launch_command=("MsiExec.exe", "/X{00000000-0000-0000-0000-000000000000}"),
        source_hint="Registre",
    )

    row = build_report_rows([candidate], results_mode="uninstallers")[0]

    assert row.name == "Demo App depuis registre"
    assert row.group_label == "Registre"
    assert row.action_label == "Désinstaller"
