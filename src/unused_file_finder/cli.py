from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from .i18n import _
from .licensing import LicenseError, LicenseManager, LicenseStatus, normalize_base_url
from .profiles import AnalysisProfile, find_profile, format_extensions as format_profile_extensions, profile_names
from .protection import ProtectionError, ProtectionList
from .report import build_report_rows, write_csv_report, write_html_report
from .scanner import (
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


MODE_LABELS = {
    "unused": _("Fichiers inactifs"),
    "duplicates": _("Doublons exacts"),
    "folders": _("Gros dossiers"),
    "installers": _("Installateurs oubliés"),
    "uninstallers": _("Applications désinstallables"),
}


def run_cli(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.command == "profiles":
        return _list_profiles()
    if args.command == "license":
        return _run_license_command(args)
    if args.command == "scan":
        return _run_scan(args)

    parser.print_help()
    return 2


def print_cli_help() -> int:
    print(_build_parser().format_help(), end="")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="SafeSweep",
        description=_("Analyse les fichiers sans ouvrir l'interface graphique."),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("profiles", help=_("Lister les profils d'analyse disponibles."))

    license_parser = subparsers.add_parser("license", help=_("Verifier ou activer la licence SafeSweep."))
    _add_license_server_arg(license_parser)
    license_subparsers = license_parser.add_subparsers(dest="license_command", required=True)
    status = license_subparsers.add_parser("status", help=_("Verifier la licence enregistree."))
    _add_license_server_arg(status)
    check = license_subparsers.add_parser("check", help=_("Alias de status."))
    _add_license_server_arg(check)
    activate = license_subparsers.add_parser("activate", help=_("Activer cette machine avec une cle de licence."))
    _add_license_server_arg(activate)
    activate.add_argument("license_key", help=_("Cle de licence client. Elle ne sera pas affichee en clair."))
    deactivate = license_subparsers.add_parser("deactivate", help=_("Desactiver cette machine pour la licence locale."))
    _add_license_server_arg(deactivate)

    scan = subparsers.add_parser("scan", help=_("Lancer une analyse et exporter un rapport."))
    scan.add_argument("--profile", choices=profile_names(), help=_("Profil d'analyse à appliquer."))
    scan.add_argument("--root", help=_("Dossier à analyser. Remplace le dossier du profil."))
    scan.add_argument(
        "--mode",
        choices=tuple(MODE_LABELS),
        help=_("Type d'analyse. Remplace le mode du profil."),
    )
    scan.add_argument("--days", type=int, help=_("Ancienneté minimale en jours."))
    scan.add_argument("--min-size-mb", type=float, help=_("Taille minimale en Mo."))
    scan.add_argument("--extensions", help=_("Extensions à inclure, séparées par virgule, point-virgule ou espace."))
    scan.add_argument("--age-basis", choices=("modified", "accessed", "activity"), help=_("Date utilisée pour l'âge."))
    scan.add_argument("--max-results", type=int, default=50_000, help=_("Nombre maximal de résultats."))
    scan.add_argument("--csv", help=_("Chemin du rapport CSV à écrire."))
    scan.add_argument("--html", help=_("Chemin du rapport HTML à écrire."))
    scan.add_argument("--include-hidden", action="store_true", help=_("Inclure les fichiers cachés/système."))
    scan.add_argument("--include-system", action="store_true", help=_("Inclure les emplacements système."))
    scan.add_argument("--no-whitelist", action="store_true", help=_("Ignorer la liste blanche configurée."))
    scan.add_argument("--quiet", action="store_true", help=_("Afficher uniquement les erreurs."))
    return parser


def _add_license_server_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--server-url",
        default=argparse.SUPPRESS,
        help=_("URL du portail de licences. Peut aussi etre definie via SAFESWEEP_LICENSE_API_URL."),
    )


def _list_profiles() -> int:
    for name in profile_names():
        profile = find_profile(name)
        if not profile:
            continue
        extensions = format_profile_extensions(profile.extensions) or _("toutes")
        print(
            f"{_(profile.name)}: {profile.root} | mode={profile.scan_mode} | "
            f"{_('jours')}={profile.days_unused} | {_('taille_min')}={profile.min_size_mb:g} {_('Mo')} | "
            f"{_('extensions')}={extensions}"
        )
    return 0


def _run_scan(args: argparse.Namespace) -> int:
    license_status = _require_license_for_cli(args)
    if not license_status.can_use:
        print(f"{_('Licence requise')}: {license_status.reason}", file=sys.stderr)
        return 3

    try:
        profile = find_profile(args.profile) if args.profile else None
        options, mode = _scan_options_from_args(args, profile)
        scanner = _scanner_for_mode(mode)
        results, stats = scanner(options)
        rows = build_report_rows(
            results,
            {candidate.path for candidate in results},
            results_mode=mode,
            age_basis=options.age_basis,
        )

        if args.csv:
            _ensure_parent(args.csv)
            write_csv_report(args.csv, rows)
        if args.html:
            _ensure_parent(args.html)
            write_html_report(
                args.html,
                rows,
                title=_("Rapport SafeSweep"),
                source_folder=str(options.root),
                scan_label=MODE_LABELS[mode],
            )
    except (OSError, ValueError, ProtectionError) as exc:
        print(f"{_('Erreur')}: {exc}", file=sys.stderr)
        return 1

    if not args.quiet:
        _print_summary(mode, results_count=len(results), stats=stats, csv_path=args.csv, html_path=args.html)
    return 0


def _run_license_command(args: argparse.Namespace) -> int:
    manager = _license_manager(args)
    command = args.license_command

    if command in {"status", "check"}:
        status = manager.validate_saved_license()
        _print_license_status(status)
        return 0 if status.can_use else 1

    if command == "activate":
        status = manager.activate(args.license_key)
        _print_license_status(status)
        return 0 if status.can_use else 1

    if command == "deactivate":
        status = manager.deactivate()
        _print_license_status(status)
        return 0 if status.reason == "Licence desactivee sur cet appareil." or status.status == "missing" else 1

    print(_build_parser().format_help(), end="")
    return 2


def _require_license_for_cli(args: argparse.Namespace) -> LicenseStatus:
    manager = _license_manager(args)
    try:
        return manager.require_valid_license()
    except LicenseError:
        return manager.local_status()


def _license_manager(args: argparse.Namespace | None = None) -> LicenseManager:
    server_url = getattr(args, "server_url", None)
    return LicenseManager(api_base_url=normalize_base_url(server_url) if server_url else None)


def _print_license_status(status: LicenseStatus) -> None:
    state = _("active") if status.can_use else _("bloquee")
    print(f"{_('Licence')}: {state}")
    print(f"{_('Statut')}: {status.status}")
    print(f"{_('Raison')}: {status.reason}")
    if status.masked_license_key:
        print(f"{_('Cle')}: {status.masked_license_key}")
    if status.expires_at:
        print(f"{_('Expiration')}: {status.expires_at}")
    if status.remaining_activations is not None:
        print(f"{_('Activations restantes')}: {status.remaining_activations}")
    print(f"{_('Appareil')}: {status.device_name} ({status.device_id})")
    print(f"{_('Serveur')}: {status.server_url}")


def _scan_options_from_args(args: argparse.Namespace, profile: AnalysisProfile | None) -> tuple[ScanOptions, str]:
    if not args.root and not profile:
        raise ValueError("Indiquez --root ou --profile.")

    root = Path(args.root) if args.root else profile.root  # type: ignore[union-attr]
    mode = args.mode or (profile.scan_mode if profile else "unused")
    days = args.days if args.days is not None else (profile.days_unused if profile else 365)
    min_size_mb = args.min_size_mb if args.min_size_mb is not None else (profile.min_size_mb if profile else 0)
    age_basis = args.age_basis or (profile.age_basis if profile else "modified")
    extensions = _extensions_from_args(args, profile)

    if args.no_whitelist:
        protected_paths: tuple[Path | str, ...] = ()
        protected_extensions: tuple[str, ...] = ()
    else:
        settings = ProtectionList().load()
        protected_paths = settings.protected_paths
        protected_extensions = settings.protected_extensions

    return (
        ScanOptions(
            root=root,
            days_unused=days,
            min_size_bytes=int(float(min_size_mb) * 1024 * 1024),
            extension_filter=extensions,
            age_basis=age_basis,
            protected_paths=protected_paths,
            protected_extensions=protected_extensions,
            skip_hidden=False if args.include_hidden else (profile.skip_hidden if profile else True),
            skip_system_locations=False if args.include_system else (profile.skip_system_locations if profile else True),
            max_results=args.max_results,
        ),
        mode,
    )


def _extensions_from_args(args: argparse.Namespace, profile: AnalysisProfile | None) -> tuple[str, ...]:
    if args.extensions is not None:
        return normalize_extensions(args.extensions)
    if profile:
        return normalize_extensions(profile.extensions)
    return ()


def _scanner_for_mode(mode: str):
    if mode == "duplicates":
        return scan_for_duplicate_files
    if mode == "folders":
        return scan_for_large_folders
    if mode == "installers":
        return scan_for_forgotten_installers
    if mode == "uninstallers":
        return scan_for_uninstallers
    if mode == "unused":
        return scan_for_unused_files
    raise ValueError(f"Mode inconnu: {mode}")


def _ensure_parent(path_value: str | Path) -> None:
    parent = Path(path_value).expanduser().resolve(strict=False).parent
    parent.mkdir(parents=True, exist_ok=True)


def _print_summary(
    mode: str,
    *,
    results_count: int,
    stats: ScanStats,
    csv_path: str | None,
    html_path: str | None,
) -> None:
    print(
        f"{_('Analyse terminée')}: {MODE_LABELS[mode]} | {results_count} {_('résultat(s)')} | "
        f"{format_bytes(stats.matched_size_bytes)} | {stats.scanned_files} {_('fichier(s) analysé(s)')} | "
        f"{stats.denied_dirs} {_('dossier(s) refusé(s)')} | {stats.errors} {_('erreur(s)')}."
    )
    if stats.hit_limit:
        print(_("Limite de résultats atteinte."))
    if stats.cancelled:
        print(_("Analyse annulée."))
    if csv_path:
        print(f"CSV: {csv_path}")
    if html_path:
        print(f"HTML: {html_path}")
