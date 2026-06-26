from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape

from .licensing import LicenseError, LicenseManager
from .protection import ProtectionList
from .report import build_report_rows, write_csv_report, write_html_report
from .scanner import (
    FileCandidate,
    ScanOptions,
    ScanStats,
    format_bytes,
    normalize_extensions,
    scan_for_duplicate_files,
    scan_for_forgotten_installers,
    scan_for_large_folders,
    scan_for_uninstallers,
    scan_for_unused_files,
)

logger = logging.getLogger(__name__)

APP_DATA_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "NettoyeurFichiers"
DEFAULT_CONFIG_PATH = APP_DATA_DIR / "planification.json"
DEFAULT_REPORT_DIR = APP_DATA_DIR / "Rapports planifies"
TASK_NAME = r"\SafeSweep - Scheduled Scan"

WEEKDAY_LABELS = {
    "Monday": "Lundi",
    "Tuesday": "Mardi",
    "Wednesday": "Mercredi",
    "Thursday": "Jeudi",
    "Friday": "Vendredi",
    "Saturday": "Samedi",
    "Sunday": "Dimanche",
}
WEEKDAY_BY_LABEL = {label: value for value, label in WEEKDAY_LABELS.items()}
MONTH_NAMES = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)


class SchedulerError(RuntimeError):
    pass


@dataclass(frozen=True)
class ScheduledScanConfig:
    root: Path
    scan_mode: str = "unused"
    days_unused: int = 365
    min_size_bytes: int = 0
    extension_filter: tuple[str, ...] = ()
    age_basis: str = "modified"
    skip_hidden: bool = True
    skip_system_locations: bool = True
    frequency: str = "weekly"
    weekday: str = "Monday"
    month_day: int = 1
    start_time: str = "09:00"
    report_dir: Path = field(default_factory=lambda: DEFAULT_REPORT_DIR)


@dataclass(frozen=True)
class ScheduledScanResult:
    config: ScheduledScanConfig
    results: tuple[FileCandidate, ...]
    stats: ScanStats
    html_report: Path
    csv_report: Path

    @property
    def total_size(self) -> int:
        return sum(candidate.size for candidate in self.results)


@dataclass(frozen=True)
class ScheduledTaskInfo:
    exists: bool
    raw_output: str = ""


def validate_config(config: ScheduledScanConfig) -> None:
    if config.scan_mode not in {"unused", "duplicates", "folders", "installers", "uninstallers"}:
        raise SchedulerError("Type d'analyse planifiée invalide.")
    if config.frequency not in {"weekly", "monthly"}:
        raise SchedulerError("La fréquence doit être hebdomadaire ou mensuelle.")
    if config.weekday not in WEEKDAY_LABELS:
        raise SchedulerError("Jour hebdomadaire invalide.")
    if config.month_day < 1 or config.month_day > 31:
        raise SchedulerError("Le jour mensuel doit être compris entre 1 et 31.")
    _validate_start_time(config.start_time)


def save_config(config: ScheduledScanConfig, path: str | Path = DEFAULT_CONFIG_PATH) -> Path:
    validate_config(config)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "root": str(config.root),
        "scan_mode": config.scan_mode,
        "days_unused": config.days_unused,
        "min_size_bytes": config.min_size_bytes,
        "extension_filter": list(config.extension_filter),
        "age_basis": config.age_basis,
        "skip_hidden": config.skip_hidden,
        "skip_system_locations": config.skip_system_locations,
        "frequency": config.frequency,
        "weekday": config.weekday,
        "month_day": config.month_day,
        "start_time": config.start_time,
        "report_dir": str(config.report_dir),
    }
    temp_path = target.with_suffix(".tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(target)
    return target


def load_config(path: str | Path = DEFAULT_CONFIG_PATH) -> ScheduledScanConfig:
    source = Path(path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SchedulerError(f"Impossible de lire la planification : {exc}") from exc

    config = ScheduledScanConfig(
        root=Path(payload["root"]),
        scan_mode=str(payload.get("scan_mode", "unused")),
        days_unused=int(payload.get("days_unused", 365)),
        min_size_bytes=int(payload.get("min_size_bytes", 0)),
        extension_filter=normalize_extensions(payload.get("extension_filter", ())),
        age_basis=str(payload.get("age_basis", "modified")),
        skip_hidden=bool(payload.get("skip_hidden", True)),
        skip_system_locations=bool(payload.get("skip_system_locations", True)),
        frequency=str(payload.get("frequency", "weekly")),
        weekday=str(payload.get("weekday", "Monday")),
        month_day=int(payload.get("month_day", 1)),
        start_time=str(payload.get("start_time", "09:00")),
        report_dir=Path(payload.get("report_dir", DEFAULT_REPORT_DIR)),
    )
    validate_config(config)
    return config


def remove_config(path: str | Path = DEFAULT_CONFIG_PATH) -> None:
    try:
        Path(path).unlink()
    except FileNotFoundError:
        return


def query_scheduled_task(task_name: str = TASK_NAME) -> ScheduledTaskInfo:
    completed = _run_schtasks(["/Query", "/TN", task_name, "/FO", "LIST", "/V"], check=False)
    return ScheduledTaskInfo(exists=completed.returncode == 0, raw_output=_completed_output(completed))


def create_scheduled_task(
    config: ScheduledScanConfig,
    command: str | Path,
    arguments: tuple[str, ...],
    *,
    config_path: str | Path = DEFAULT_CONFIG_PATH,
    task_name: str = TASK_NAME,
) -> Path:
    if os.name != "nt":
        raise SchedulerError("La planification automatique utilise le Planificateur de tâches Windows.")

    saved_config = save_config(config, config_path)
    xml = build_task_xml(config, command, arguments)
    with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False, encoding="utf-16") as handle:
        handle.write(xml)
        xml_path = Path(handle.name)

    try:
        _run_schtasks(["/Create", "/TN", task_name, "/XML", str(xml_path), "/F"])
    finally:
        try:
            xml_path.unlink()
        except OSError:
            logger.warning("Impossible de supprimer le XML temporaire de planification : %s", xml_path)
    return saved_config


def delete_scheduled_task(*, task_name: str = TASK_NAME, config_path: str | Path = DEFAULT_CONFIG_PATH) -> None:
    if os.name != "nt":
        raise SchedulerError("La planification automatique utilise le Planificateur de tâches Windows.")

    info = query_scheduled_task(task_name)
    if info.exists:
        _run_schtasks(["/Delete", "/TN", task_name, "/F"])
    remove_config(config_path)


def build_task_xml(config: ScheduledScanConfig, command: str | Path, arguments: tuple[str, ...]) -> str:
    validate_config(config)
    start_boundary = _start_boundary(config.start_time)
    trigger = _weekly_trigger(config, start_boundary) if config.frequency == "weekly" else _monthly_trigger(config, start_boundary)
    months = "".join(f"<{month} />" for month in MONTH_NAMES)
    argument_text = subprocess.list2cmdline(list(arguments))
    user_id = _current_user_id()
    user_xml = f"<UserId>{escape(user_id)}</UserId>" if user_id else ""

    if "{months}" in trigger:
        trigger = trigger.format(months=months)

    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>SafeSweep scheduled analysis. No automatic deletion.</Description>
  </RegistrationInfo>
  <Triggers>
    {trigger}
  </Triggers>
  <Principals>
    <Principal id="Author">
      {user_xml}
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings>
      <StopOnIdleEnd>false</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT4H</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{escape(os.fspath(command))}</Command>
      <Arguments>{escape(argument_text)}</Arguments>
    </Exec>
  </Actions>
</Task>
"""


def run_scheduled_scan(path: str | Path = DEFAULT_CONFIG_PATH, *, notify: bool = True) -> ScheduledScanResult:
    try:
        LicenseManager().require_valid_license()
    except LicenseError as exc:
        message = f"Licence SafeSweep requise : {exc}"
        if notify:
            notify_user("Analyse planifiee bloquee", message)
        raise SchedulerError(message) from exc

    config = load_config(path)
    protection = ProtectionList().load()
    options = ScanOptions(
        root=config.root,
        days_unused=config.days_unused,
        min_size_bytes=config.min_size_bytes,
        extension_filter=config.extension_filter,
        age_basis=config.age_basis,
        protected_paths=protection.protected_paths,
        protected_extensions=protection.protected_extensions,
        skip_hidden=config.skip_hidden,
        skip_system_locations=config.skip_system_locations,
    )
    scanner = _scanner_for_mode(config.scan_mode)
    results, stats = scanner(options)
    html_report, csv_report = _write_scheduled_reports(config, results)
    result = ScheduledScanResult(
        config=config,
        results=tuple(results),
        stats=stats,
        html_report=html_report,
        csv_report=csv_report,
    )
    if notify:
        notify_user("Analyse planifiée terminée", _success_message(result))
    return result


def notify_user(title: str, message: str, *, timeout_seconds: int = 12) -> bool:
    if os.name != "nt":
        return False

    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    script_path = APP_DATA_DIR / "notification.vbs"
    script = (
        'Set shell = CreateObject("WScript.Shell")\n'
        f"shell.Popup {_vbs_string(message)}, {timeout_seconds}, {_vbs_string(title)}, 64\n"
    )
    try:
        script_path.write_text(script, encoding="utf-16")
        subprocess.Popen(
            ["wscript.exe", str(script_path)],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError:
        logger.exception("Impossible d'afficher la notification planifiée")
        return False
    return True


def current_app_action() -> tuple[str, tuple[str, ...]]:
    if getattr(sys, "frozen", False):
        return sys.executable, ()
    app_script = Path(__file__).resolve().parents[1] / "app.py"
    return sys.executable, (str(app_script),)


def scan_mode_label(scan_mode: str) -> str:
    if scan_mode == "duplicates":
        return "Doublons exacts"
    if scan_mode == "folders":
        return "Gros dossiers"
    if scan_mode == "installers":
        return "Installateurs oubliés"
    if scan_mode == "uninstallers":
        return "Désinstallateurs"
    return "Fichiers inactifs"


def _write_scheduled_reports(config: ScheduledScanConfig, results: list[FileCandidate]) -> tuple[Path, Path]:
    config.report_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    stem = f"analyse-planifiee-{timestamp}"
    html_report = config.report_dir / f"{stem}.html"
    csv_report = config.report_dir / f"{stem}.csv"
    rows = build_report_rows(results, set(), results_mode=config.scan_mode, age_basis=config.age_basis)
    write_html_report(
        html_report,
        rows,
        title="Analyse planifiée - SafeSweep",
        source_folder=str(config.root),
        scan_label=scan_mode_label(config.scan_mode),
    )
    write_csv_report(csv_report, rows)
    return html_report, csv_report


def _success_message(result: ScheduledScanResult) -> str:
    return (
        f"{scan_mode_label(result.config.scan_mode)} : {len(result.results)} élément(s), "
        f"{format_bytes(result.total_size)} potentiel.\n"
        f"Rapport : {result.html_report}"
    )


def _scanner_for_mode(scan_mode: str):
    if scan_mode == "duplicates":
        return scan_for_duplicate_files
    if scan_mode == "folders":
        return scan_for_large_folders
    if scan_mode == "installers":
        return scan_for_forgotten_installers
    if scan_mode == "uninstallers":
        return scan_for_uninstallers
    return scan_for_unused_files


def _weekly_trigger(config: ScheduledScanConfig, start_boundary: str) -> str:
    return f"""<CalendarTrigger>
      <StartBoundary>{escape(start_boundary)}</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByWeek>
        <DaysOfWeek>
          <{config.weekday} />
        </DaysOfWeek>
        <WeeksInterval>1</WeeksInterval>
      </ScheduleByWeek>
    </CalendarTrigger>"""


def _monthly_trigger(config: ScheduledScanConfig, start_boundary: str) -> str:
    return f"""<CalendarTrigger>
      <StartBoundary>{escape(start_boundary)}</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByMonth>
        <DaysOfMonth>
          <Day>{config.month_day}</Day>
        </DaysOfMonth>
        <Months>
          {{months}}
        </Months>
      </ScheduleByMonth>
    </CalendarTrigger>"""


def _start_boundary(start_time: str) -> str:
    _validate_start_time(start_time)
    return f"{datetime.now().date().isoformat()}T{start_time}:00"


def _validate_start_time(start_time: str) -> None:
    parts = start_time.split(":")
    if len(parts) != 2:
        raise SchedulerError("L'heure doit être au format HH:MM.")
    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except ValueError as exc:
        raise SchedulerError("L'heure doit être au format HH:MM.") from exc
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        raise SchedulerError("L'heure doit être comprise entre 00:00 et 23:59.")


def _current_user_id() -> str:
    domain = os.environ.get("USERDOMAIN", "").strip()
    username = os.environ.get("USERNAME", "").strip()
    if domain and username:
        return f"{domain}\\{username}"
    return username


def _run_schtasks(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        ["schtasks.exe", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if check and completed.returncode != 0:
        raise SchedulerError(_completed_output(completed) or "Erreur du Planificateur de tâches Windows.")
    return completed


def _completed_output(completed: subprocess.CompletedProcess[str]) -> str:
    return "\n".join(part for part in (completed.stdout.strip(), completed.stderr.strip()) if part)


def _vbs_escape(value: object) -> str:
    return str(value).replace('"', '""')


def _vbs_string(value: object) -> str:
    lines = str(value).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return " & vbCrLf & ".join(f'"{_vbs_escape(line)}"' for line in lines)
