from __future__ import annotations

import sys
from pathlib import Path

from . import __version__


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    language = _consume_language(args)
    if language:
        from .i18n import set_language

        set_language(language)

    if "--version" in args:
        print(__version__)
        return 0

    if "--self-test" in args:
        from .cli import run_cli
        from .gui import run_app
        from .profiles import profile_names
        from .protection import ProtectionList
        from .quarantine import QuarantineManager
        from .report import build_html_report
        from .risk import assess_deletion_risk, recommend_action
        from .scheduler import ScheduledScanConfig, build_task_xml, run_scheduled_scan
        from .scanner import (
            ScanOptions,
            format_bytes,
            normalize_extensions,
            scan_for_duplicate_files,
            scan_for_forgotten_installers,
            scan_for_large_folders,
            scan_for_uninstallers,
        )

        assert format_bytes(1024) == "1.0 Ko"
        assert normalize_extensions(".zip, iso;PDF") == (".zip", ".iso", ".pdf")
        assert ScanOptions(root=".").days_unused == 365
        assert callable(run_cli)
        assert callable(run_app)
        assert "Bureau rapide" in profile_names()
        assert ProtectionList is not None
        assert QuarantineManager is not None
        assert assess_deletion_risk("install.log").label == "Faible"
        assert recommend_action("install.log").label == "Supprimable"
        assert "Rapport" in build_html_report([], title="Rapport")
        assert "CalendarTrigger" in build_task_xml(ScheduledScanConfig(root="."), sys.executable, ("--scheduled-scan",))
        assert callable(run_scheduled_scan)
        assert callable(scan_for_duplicate_files)
        assert callable(scan_for_forgotten_installers)
        assert callable(scan_for_large_folders)
        assert callable(scan_for_uninstallers)
        return 0

    if "--scheduled-scan" in args:
        from .scheduler import DEFAULT_CONFIG_PATH, SchedulerError, notify_user, run_scheduled_scan

        config_path = _option_value(args, "--config") or str(DEFAULT_CONFIG_PATH)
        try:
            run_scheduled_scan(config_path, notify=True)
        except Exception as exc:  # noqa: BLE001 - scheduled task safety net
            message = str(exc)
            if not isinstance(exc, SchedulerError):
                message = f"Analyse planifiée interrompue : {exc}"
            notify_user("Analyse planifiée interrompue", message)
            return 1
        return 0

    if args or _is_cli_executable():
        from .cli import print_cli_help, run_cli

        return run_cli(args) if args else print_cli_help()

    from .gui import run_app

    run_app()
    return 0


def _option_value(args: list[str], option: str) -> str | None:
    try:
        index = args.index(option)
    except ValueError:
        return None
    if index + 1 >= len(args):
        return None
    return args[index + 1]


def _consume_language(args: list[str]) -> str | None:
    for index, value in enumerate(list(args)):
        if value in {"--lang", "--language"}:
            if index + 1 >= len(args):
                return None
            language = args[index + 1]
            del args[index : index + 2]
            return language
        if value.startswith("--lang="):
            del args[index]
            return value.split("=", 1)[1]
        if value.startswith("--language="):
            del args[index]
            return value.split("=", 1)[1]
    return None


def _is_cli_executable() -> bool:
    return Path(sys.executable).stem.casefold().endswith("-cli")


if __name__ == "__main__":
    raise SystemExit(main())
