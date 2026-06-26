from __future__ import annotations

import csv
import html
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Sequence

from .i18n import _, current_language
from .risk import ActionRecommendation, RiskAssessment, assess_deletion_risk, recommend_action
from .scanner import FileCandidate, format_bytes


UNINSTALLER_RISK = RiskAssessment(
    2,
    "Élevé",
    _("Désinstallateur détecté : lancer ce programme peut modifier ou retirer une application."),
)
UNINSTALLER_RECOMMENDATION = ActionRecommendation(
    1,
    "Désinstaller",
    _("Lancez le désinstallateur uniquement si vous reconnaissez l'application."),
)


@dataclass(frozen=True)
class ReportRow:
    selected: bool
    item_type: str
    risk_score: int
    risk_label: str
    risk_reason: str
    action_rank: int
    action_label: str
    action_reason: str
    group_label: str
    name: str
    folder: str
    size_bytes: int
    size_display: str
    folder_file_count: int | str
    folder_dir_count: int | str
    retained_at: str
    accessed_at: str
    modified_at: str
    duplicate_hash: str
    path: str


CSV_HEADERS = [
    "Sélectionné",
    "Type",
    "Risque",
    "Score risque",
    "Raison risque",
    "Action recommandée",
    "Rang action",
    "Raison action",
    "Groupe ou indice",
    "Nom",
    "Dossier",
    "Taille",
    "Taille octets",
    "Fichiers dans dossier",
    "Sous-dossiers",
    "Date retenue",
    "Dernier accès",
    "Modifié",
    "Hash doublon",
    "Chemin",
]


def build_report_rows(
    candidates: Sequence[FileCandidate],
    selected_paths: set[Path] | None = None,
    *,
    results_mode: str = "unused",
    age_basis: str = "modified",
) -> list[ReportRow]:
    selected = selected_paths or set()
    return [
        _build_report_row(candidate, candidate.path in selected, results_mode=results_mode, age_basis=age_basis)
        for candidate in candidates
    ]


def write_csv_report(path_value: str | Path, rows: Sequence[ReportRow]) -> None:
    with Path(path_value).open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow([_(header) for header in CSV_HEADERS])
        for row in rows:
            writer.writerow(
                [
                    _("oui") if row.selected else _("non"),
                    _(row.item_type),
                    _(row.risk_label),
                    row.risk_score,
                    _(row.risk_reason),
                    _(row.action_label),
                    row.action_rank,
                    _(row.action_reason),
                    _(row.group_label),
                    row.name,
                    row.folder,
                    row.size_display,
                    row.size_bytes,
                    row.folder_file_count,
                    row.folder_dir_count,
                    row.retained_at,
                    row.accessed_at,
                    row.modified_at,
                    row.duplicate_hash,
                    row.path,
                ]
            )


def write_html_report(
    path_value: str | Path,
    rows: Sequence[ReportRow],
    *,
    title: str = "Rapport d'analyse",
    source_folder: str = "",
    scan_label: str = "",
) -> None:
    Path(path_value).write_text(
        build_html_report(rows, title=title, source_folder=source_folder, scan_label=scan_label),
        encoding="utf-8",
    )


def build_html_report(
    rows: Sequence[ReportRow],
    *,
    title: str = "Rapport d'analyse",
    source_folder: str = "",
    scan_label: str = "",
) -> str:
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    total_size = sum(row.size_bytes for row in rows)
    selected_count = sum(1 for row in rows if row.selected)
    risk_counts = Counter(row.risk_label for row in rows)
    action_counts = Counter(row.action_label for row in rows)

    risk_items = "".join(
        f"<span class=\"pill risk-{_risk_class(str(_(label)))}\">{_e(_(label))}: {count}</span>"
        for label, count in sorted(risk_counts.items())
    )
    action_items = "".join(
        f"<span class=\"pill action\">{_e(_(label))}: {count}</span>" for label, count in sorted(action_counts.items())
    )
    table_rows = "\n".join(_html_table_row(row) for row in rows)

    source_html = f"<p><strong>{_e(_('Dossier analysé'))}</strong> {_e(source_folder)}</p>" if source_folder else ""
    scan_type_label = _("Type d'analyse")
    scan_html = f"<p><strong>{_e(scan_type_label)}</strong> {_e(scan_label)}</p>" if scan_label else ""

    return f"""<!doctype html>
<html lang="{_e(current_language())}">
<head>
  <meta charset="utf-8">
  <title>{_e(title)}</title>
  <style>
    :root {{
      color-scheme: light;
      --text: #17202a;
      --muted: #5d6d7e;
      --line: #d8dee9;
      --header: #f4f7fb;
      --low: #176a31;
      --medium: #7a6500;
      --high: #9a4f00;
      --critical: #9f1d1d;
    }}
    body {{
      margin: 28px;
      color: var(--text);
      font: 14px/1.45 "Segoe UI", Arial, sans-serif;
      background: #ffffff;
    }}
    h1 {{ margin: 0 0 6px; font-size: 24px; }}
    .meta {{ margin-bottom: 18px; color: var(--muted); }}
    .summary {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 10px;
      margin: 18px 0;
    }}
    .metric {{
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px 12px;
      background: var(--header);
    }}
    .metric strong {{ display: block; font-size: 18px; }}
    .pills {{ display: flex; flex-wrap: wrap; gap: 8px; margin: 12px 0 18px; }}
    .pill {{
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 5px 9px;
      background: #fff;
      font-weight: 600;
    }}
    .risk-faible, .risk-low, .risk-bajo {{ color: var(--low); }}
    .risk-moyen, .risk-medium, .risk-medio {{ color: var(--medium); }}
    .risk-eleve, .risk-high, .risk-alto {{ color: var(--high); }}
    .risk-critique, .risk-critical, .risk-critico {{ color: var(--critical); }}
    table {{
      width: 100%;
      border-collapse: collapse;
      table-layout: fixed;
    }}
    th, td {{
      border-bottom: 1px solid var(--line);
      padding: 7px 8px;
      vertical-align: top;
      word-break: break-word;
    }}
    th {{
      position: sticky;
      top: 0;
      text-align: left;
      background: var(--header);
      z-index: 1;
    }}
    .num {{ text-align: right; white-space: nowrap; }}
    .selected {{ width: 52px; text-align: center; }}
    .risk {{ width: 86px; font-weight: 700; }}
    .size {{ width: 96px; }}
    .action {{ width: 138px; font-weight: 700; }}
    .reason {{ width: 260px; color: #2f3f4f; }}
    .path {{ color: var(--muted); font-size: 12px; }}
    @media print {{
      body {{ margin: 14mm; }}
      th {{ position: static; }}
      .summary {{ grid-template-columns: repeat(2, 1fr); }}
    }}
  </style>
</head>
<body>
  <h1>{_e(title)}</h1>
  <div class="meta">
    <p><strong>{_e(_('Généré le'))}</strong> {_e(generated_at)}</p>
    {source_html}
    {scan_html}
  </div>
  <section class="summary" aria-label="{_e(_('Résumé'))}">
    <div class="metric"><span>{_e(_('Éléments'))}</span><strong>{len(rows)}</strong></div>
    <div class="metric"><span>{_e(_('Sélectionnés'))}</span><strong>{selected_count}</strong></div>
    <div class="metric"><span>{_e(_('Taille totale'))}</span><strong>{_e(format_bytes(total_size))}</strong></div>
  </section>
  <h2>{_e(_('Risques'))}</h2>
  <div class="pills">{risk_items or f'<span class="pill">{_e(_("Aucun"))}</span>'}</div>
  <h2>{_e(_('Actions recommandées'))}</h2>
  <div class="pills">{action_items or f'<span class="pill">{_e(_("Aucune"))}</span>'}</div>
  <table>
    <thead>
      <tr>
        <th class="selected">Sel.</th>
        <th>{_e(_('Nom'))}</th>
        <th class="risk">{_e(_('Risque'))}</th>
        <th class="size num">{_e(_('Taille'))}</th>
        <th class="action">{_e(_('Action recommandée'))}</th>
        <th class="reason">{_e(_('Raison'))}</th>
        <th>{_e(_('Chemin'))}</th>
      </tr>
    </thead>
    <tbody>
      {table_rows}
    </tbody>
  </table>
</body>
</html>
"""


def _build_report_row(candidate: FileCandidate, selected: bool, *, results_mode: str, age_basis: str) -> ReportRow:
    risk = _candidate_risk(candidate)
    action = _candidate_recommendation(candidate)
    return ReportRow(
        selected=selected,
        item_type=candidate.item_type,
        risk_score=risk.score,
        risk_label=risk.label,
        risk_reason=risk.reason,
        action_rank=action.rank,
        action_label=action.label,
        action_reason=action.reason,
        group_label=_candidate_group_label(candidate),
        name=_candidate_display_name(candidate),
        folder=str(candidate.path.parent),
        size_bytes=candidate.size,
        size_display=format_bytes(candidate.size),
        folder_file_count=candidate.folder_file_count if candidate.item_type == "Dossier" else "",
        folder_dir_count=candidate.folder_dir_count if candidate.item_type == "Dossier" else "",
        retained_at=_format_datetime(_candidate_retained_at(candidate, results_mode, age_basis)),
        accessed_at=_format_datetime(candidate.accessed_at),
        modified_at=_format_datetime(candidate.modified_at),
        duplicate_hash=candidate.duplicate_hash,
        path=str(candidate.path),
    )


def _html_table_row(row: ReportRow) -> str:
    risk_label = _(row.risk_label)
    action_label = _(row.action_label)
    item_type = _(row.item_type)
    group_label = _(row.group_label)
    risk_class = _risk_class(str(risk_label))
    reason = f"{_(row.risk_reason)} {_(row.action_reason)}".strip()
    return f"""<tr>
        <td class="selected">{'✓' if row.selected else ''}</td>
        <td>{_e(row.name)}<br><span class="path">{_e(item_type)} {_e(group_label)}</span></td>
        <td class="risk risk-{risk_class}">{_e(risk_label)}</td>
        <td class="size num">{_e(row.size_display)}</td>
        <td class="action">{_e(action_label)}</td>
        <td class="reason">{_e(reason)}</td>
        <td>{_e(row.path)}<br><span class="path">{_e(_('Date retenue'))} : {_e(row.retained_at)}</span></td>
      </tr>"""


def _candidate_group_label(candidate: FileCandidate) -> str:
    if candidate.item_type == "Désinstallateur":
        return _uninstaller_source_label(candidate)
    if candidate.folder_hint:
        return candidate.folder_hint
    return str(candidate.duplicate_group) if candidate.duplicate_group else ""


def _candidate_display_name(candidate: FileCandidate) -> str:
    if candidate.item_type == "Désinstallateur":
        return candidate.display_name or candidate.folder_hint or candidate.path.parent.name or candidate.path.name
    return candidate.path.name


def _candidate_risk(candidate: FileCandidate) -> RiskAssessment:
    if candidate.item_type == "Désinstallateur":
        return UNINSTALLER_RISK
    return assess_deletion_risk(candidate.path)


def _candidate_recommendation(candidate: FileCandidate) -> ActionRecommendation:
    if candidate.item_type == "Désinstallateur":
        return UNINSTALLER_RECOMMENDATION
    return recommend_action(candidate.path)


def _uninstaller_source_label(candidate: FileCandidate) -> str:
    source = candidate.source_hint.strip()
    if not source:
        return "Fichier"
    if source.casefold().startswith("registre"):
        return "Registre"
    return source


def _candidate_retained_at(candidate: FileCandidate, results_mode: str, age_basis: str) -> float:
    if results_mode == "duplicates":
        return candidate.last_activity_at
    if age_basis == "accessed":
        return candidate.accessed_at
    if age_basis == "activity":
        return candidate.last_activity_at
    return candidate.modified_at


def _format_datetime(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M")


def _risk_class(label: str) -> str:
    return (
        label.casefold()
        .replace("é", "e")
        .replace("è", "e")
        .replace("ê", "e")
        .replace("à", "a")
        .replace("í", "i")
        .replace("ó", "o")
        .replace(" ", "-")
    )


def _e(value: object) -> str:
    return html.escape(str(value), quote=True)
