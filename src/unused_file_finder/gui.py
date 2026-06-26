from __future__ import annotations

import logging
import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from collections import Counter, defaultdict
from datetime import datetime
from importlib import resources
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Callable

from . import __version__
from .i18n import (
    _,
    current_language,
    install_tkinter_i18n,
    language_choices,
    language_code_from_label,
    language_label,
    save_language,
    source_text,
    translate_sequence,
)
from .licensing import LicenseManager, LicenseStatus
from .profiles import find_profile, format_extensions as format_profile_extensions, format_min_size_mb, profile_names
from .protection import ProtectionError, ProtectionList, normalize_extensions as normalize_protection_extensions
from .quarantine import QuarantineError, QuarantineManager, QuarantineRecord, QuarantineSettings
from .recycle import RecycleError, move_to_recycle_bin
from .report import build_report_rows, write_csv_report, write_html_report
from .risk import ActionRecommendation, RiskAssessment, assess_deletion_risk, recommend_action
from .scheduler import (
    DEFAULT_CONFIG_PATH,
    DEFAULT_REPORT_DIR,
    SchedulerError,
    ScheduledScanConfig,
    WEEKDAY_BY_LABEL,
    WEEKDAY_LABELS,
    create_scheduled_task,
    current_app_action,
    delete_scheduled_task,
    load_config,
    query_scheduled_task,
    scan_mode_label,
)
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

install_tkinter_i18n(tk, ttk, messagebox, filedialog, simpledialog)

AGE_BASIS_LABELS = {
    "modified": _("Modification seule"),
    "accessed": _("Dernier accès seul"),
    "activity": _("Accès ou modification"),
}
AGE_BASIS_BY_LABEL = {label: value for value, label in AGE_BASIS_LABELS.items()}
SCAN_MODE_LABELS = {
    "unused": _("Fichiers inactifs"),
    "duplicates": _("Doublons exacts"),
    "folders": _("Gros dossiers"),
    "installers": _("Installateurs"),
    "uninstallers": _("Désinstallateurs"),
}
SCAN_MODE_BY_LABEL = {label: value for value, label in SCAN_MODE_LABELS.items()}
APP_NAME = "SafeSweep"
APP_ID = "Codex.SafeSweep.1"
BRAND_ICON_PNG = "nettoyeur-fichiers.png"
BRAND_ICON_ICO = "nettoyeur-fichiers.ico"
APP_BACKGROUND = "#f4f7fb"
APP_SURFACE = "#ffffff"
APP_BORDER = "#d6e1eb"
APP_TEXT = "#203040"
APP_MUTED = "#607083"
APP_BRAND = "#0f6b7a"
APP_BRAND_DARK = "#0a5360"
APP_DANGER = "#a33a2a"
APP_DANGER_DARK = "#842d21"
APP_SUCCESS = "#176a31"
APP_WARNING = "#8a6500"
LOG_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "NettoyeurFichiers"
LOG_FILE = LOG_DIR / "app.log"
MAX_TEXT_PREVIEW_BYTES = 512 * 1024
MAX_IMAGE_PREVIEW_SIZE = (900, 650)
TEXT_PREVIEW_EXTENSIONS = {
    ".bat",
    ".cfg",
    ".cmd",
    ".config",
    ".csv",
    ".ini",
    ".json",
    ".log",
    ".md",
    ".ps1",
    ".py",
    ".rtf",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}
IMAGE_PREVIEW_EXTENSIONS = {
    ".bmp",
    ".gif",
    ".heic",
    ".jpeg",
    ".jpg",
    ".png",
    ".tif",
    ".tiff",
    ".webp",
}
FORGOTTEN_INSTALLER_BINARY_EXTENSIONS = {
    ".appx",
    ".appxbundle",
    ".exe",
    ".msi",
    ".msix",
    ".msixbundle",
    ".msp",
}
FORGOTTEN_INSTALLER_RISK = RiskAssessment(
    2,
    "Élevé",
    _("Installateur ancien trouvé dans Téléchargements : vérifiez qu'il n'est plus nécessaire avant suppression."),
)
FORGOTTEN_INSTALLER_RECOMMENDATION = ActionRecommendation(
    1,
    "Quarantaine",
    _("À isoler d'abord si vous avez un doute ; sinon la Corbeille reste restaurable tant qu'elle n'est pas vidée."),
)
UNINSTALLER_RISK = RiskAssessment(
    2,
    "Élevé",
    _("Désinstallateur détecté : lancer ce programme peut modifier ou retirer une application."),
)
UNINSTALLER_RECOMMENDATION = ActionRecommendation(
    1,
    "Désinstaller",
    _("Lancez le désinstallateur depuis le clic droit uniquement si vous reconnaissez l'application."),
)

logger = logging.getLogger(__name__)


class UnusedFileFinderApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"{APP_NAME} {__version__}")
        self.geometry("1180x720")
        self.minsize(940, 600)

        self.window_icon_image: tk.PhotoImage | None = None
        self.brand_icon_image: tk.PhotoImage | None = None
        self.ui_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.cancel_event = threading.Event()
        self.scan_thread: threading.Thread | None = None
        self.delete_thread: threading.Thread | None = None
        self.quarantine_thread: threading.Thread | None = None
        self.quarantine_manager = QuarantineManager()
        self.protection_list = ProtectionList()
        self.results: list[FileCandidate] = []
        self.filtered_results: list[FileCandidate] = []
        self.results_mode = "unused"
        self.current_scan_mode = "unused"
        self.item_to_result: dict[str, FileCandidate] = {}
        self.action_buttons: dict[str, ttk.Button] = {}
        self.action_button_refresh_pending = False
        self.dashboard_window: tk.Toplevel | None = None
        self.activation_window: tk.Toplevel | None = None
        self.activation_status_var: tk.StringVar | None = None
        self.license_manager = LicenseManager()
        self.license_status: LicenseStatus = self.license_manager.local_status()
        self.license_busy = False
        self.pending_uninstall_keys: set[str] = set()
        self.checked_paths: set[Path] = set()

        default_profile = find_profile("Nettoyage prudent")
        default_folder = default_profile.root if default_profile else Path.home() / "Documents"
        if not default_folder.exists():
            default_folder = Path.home()

        self.language_var = tk.StringVar(value=language_label(current_language()))
        self.profile_var = tk.StringVar(value=_(default_profile.name) if default_profile else "")
        self.folder_var = tk.StringVar(value=str(default_folder))
        self.days_var = tk.IntVar(value=default_profile.days_unused if default_profile else 365)
        self.min_size_var = tk.StringVar(value=format_min_size_mb(default_profile.min_size_mb) if default_profile else "0")
        self.extensions_var = tk.StringVar(
            value=format_profile_extensions(default_profile.extensions) if default_profile else ""
        )
        self.age_basis_var = tk.StringVar(
            value=AGE_BASIS_LABELS.get(default_profile.age_basis, AGE_BASIS_LABELS["modified"])
            if default_profile
            else AGE_BASIS_LABELS["modified"]
        )
        self.scan_mode_var = tk.StringVar(value=default_profile.scan_mode if default_profile else "unused")
        self.scan_mode_label_var = tk.StringVar(
            value=SCAN_MODE_LABELS.get(self.scan_mode_var.get(), SCAN_MODE_LABELS["unused"])
        )
        self.skip_hidden_var = tk.BooleanVar(value=default_profile.skip_hidden if default_profile else True)
        self.skip_system_var = tk.BooleanVar(value=default_profile.skip_system_locations if default_profile else True)
        self.status_var = tk.StringVar(value="Choisissez un dossier, puis lancez l'analyse.")
        self.license_status_var = tk.StringVar(value=self._license_status_text())
        self.total_var = tk.StringVar(value="0 fichier - 0 o")
        self.note_var = tk.StringVar(value="Signal utilisé : dernière modification seulement.")
        self.filter_text_var = tk.StringVar(value="")
        self.filter_risk_var = tk.StringVar(value=_("Tous"))
        self.filter_recommendation_var = tk.StringVar(value=_("Toutes"))
        self.filter_extension_var = tk.StringVar(value="")
        self.filter_folder_var = tk.StringVar(value="")
        self.filter_min_size_var = tk.StringVar(value="")
        self.filter_max_size_var = tk.StringVar(value="")
        self.filter_group_var = tk.StringVar(value="")
        self.mode_buttons: list[ttk.Radiobutton] = []
        self.results_age_basis = "modified"

        self._apply_branding()
        self._configure_style()
        self._build_ui()
        self._update_license_ui()
        self.after(0, self._maximize_on_startup)
        self.after(250, self._check_license_on_startup)
        self.after(700, self._open_startup_dashboard_if_licensed)
        self.after(120, self._poll_queue)
        self.after(2600, self._prompt_expired_quarantine)

    def _apply_branding(self) -> None:
        self._set_windows_app_id()
        asset_dir = resources.files(__package__) / "assets"

        try:
            with resources.as_file(asset_dir / BRAND_ICON_PNG) as icon_path:
                self.window_icon_image = tk.PhotoImage(file=str(icon_path))
                self.iconphoto(True, self.window_icon_image)
                self.brand_icon_image = self.window_icon_image.subsample(8, 8)
        except (FileNotFoundError, ModuleNotFoundError, tk.TclError, ValueError):
            self.window_icon_image = None
            self.brand_icon_image = None

        if os.name != "nt":
            return

        try:
            with resources.as_file(asset_dir / BRAND_ICON_ICO) as icon_path:
                self.iconbitmap(default=str(icon_path))
        except (FileNotFoundError, ModuleNotFoundError, tk.TclError, ValueError):
            pass

    @staticmethod
    def _set_windows_app_id() -> None:
        if os.name != "nt":
            return
        try:
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
        except (AttributeError, OSError):
            pass

    def _configure_style(self) -> None:
        style = ttk.Style(self)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        elif "vista" in style.theme_names():
            style.theme_use("vista")

        self.configure(bg=APP_BACKGROUND)
        self.option_add("*Font", ("Segoe UI", 9))

        style.configure(".", font=("Segoe UI", 9), foreground=APP_TEXT)
        style.configure("TFrame", background=APP_BACKGROUND)
        style.configure("Toolbar.TFrame", background=APP_SURFACE, padding=(8, 6))
        style.configure("Surface.TFrame", background=APP_SURFACE)
        style.configure("StatusBar.TFrame", background="#e9f0f6", padding=(8, 4))

        style.configure("TLabel", background=APP_BACKGROUND, foreground=APP_TEXT)
        style.configure("Surface.TLabel", background=APP_SURFACE, foreground=APP_TEXT)
        style.configure("Muted.Surface.TLabel", background=APP_SURFACE, foreground=APP_MUTED)
        style.configure("Brand.TLabel", background=APP_SURFACE, foreground=APP_BRAND_DARK, font=("Segoe UI", 12, "bold"))
        style.configure("Status.TLabel", foreground=APP_MUTED, background=APP_BACKGROUND)
        style.configure("StatusBar.TLabel", foreground=APP_MUTED, background="#e9f0f6")

        style.configure("Section.TLabelframe", background=APP_SURFACE, bordercolor=APP_BORDER, relief=tk.SOLID)
        style.configure(
            "Section.TLabelframe.Label",
            background=APP_SURFACE,
            foreground=APP_BRAND_DARK,
            font=("Segoe UI", 9, "bold"),
        )

        style.configure("TButton", padding=(8, 3), relief=tk.FLAT)
        style.map(
            "TButton",
            background=[("active", "#e8eef5"), ("disabled", "#edf2f7")],
            foreground=[("disabled", "#9aa8b6")],
        )
        style.configure("Accent.TButton", background=APP_BRAND, foreground="#ffffff", padding=(12, 4))
        style.map(
            "Accent.TButton",
            background=[("active", APP_BRAND_DARK), ("disabled", "#a7bcc4")],
            foreground=[("disabled", "#eef4f6")],
        )
        style.configure("Secondary.TButton", background="#edf3f8", foreground=APP_TEXT)
        style.configure("Danger.TButton", background=APP_DANGER, foreground="#ffffff")
        style.map(
            "Danger.TButton",
            background=[("active", APP_DANGER_DARK), ("disabled", "#d6a49b")],
            foreground=[("disabled", "#f8eeee")],
        )
        style.configure("Toolbar.TMenubutton", background="#edf3f8", foreground=APP_TEXT, padding=(8, 3))
        style.map("Toolbar.TMenubutton", background=[("active", "#dfeaf3"), ("disabled", "#edf2f7")])

        style.configure("TEntry", padding=(4, 2), fieldbackground="#ffffff")
        style.configure("TCombobox", padding=(4, 2), fieldbackground="#ffffff")
        style.configure("TSpinbox", padding=(4, 2), fieldbackground="#ffffff")
        style.configure("TCheckbutton", background=APP_SURFACE, foreground=APP_TEXT)
        style.configure("TRadiobutton", background=APP_SURFACE, foreground=APP_TEXT)
        style.configure("Horizontal.TProgressbar", troughcolor="#dce7ef", background=APP_BRAND, thickness=5)

        style.configure(
            "Treeview",
            background=APP_SURFACE,
            fieldbackground=APP_SURFACE,
            foreground=APP_TEXT,
            borderwidth=0,
            rowheight=24,
            font=("Segoe UI", 9),
        )
        style.configure(
            "Treeview.Heading",
            background="#e9f0f6",
            foreground=APP_TEXT,
            relief=tk.FLAT,
            padding=(6, 4),
            font=("Segoe UI", 9, "bold"),
        )
        style.map(
            "Treeview",
            background=[("selected", "#d4ecf3")],
            foreground=[("selected", APP_TEXT)],
        )

    def _maximize_on_startup(self) -> None:
        try:
            self.state("zoomed")
        except tk.TclError:
            try:
                self.attributes("-zoomed", True)
            except tk.TclError:
                pass

    def _check_license_on_startup(self) -> None:
        self._update_license_ui()
        if self.license_status.can_use:
            self._validate_license_async(show_message=False)
            return
        self._open_activation_window(startup=True)

    def _open_startup_dashboard_if_licensed(self) -> None:
        if self.license_status.can_use:
            self._open_startup_dashboard()

    def _license_status_text(self) -> str:
        if self.license_status.can_use:
            suffix = f" - expire le {self.license_status.expires_at}" if self.license_status.expires_at else ""
            return f"Licence active{suffix}"
        return f"Licence requise - {self.license_status.reason}"

    def _license_allows_use(self) -> bool:
        return self.license_status.can_use

    def _update_license_ui(self) -> None:
        self.license_status_var.set(self._license_status_text())
        if hasattr(self, "scan_button"):
            scanning = self.scan_thread is not None and self.scan_thread.is_alive()
            self.scan_button.configure(state=tk.NORMAL if self.license_status.can_use and not scanning else tk.DISABLED)
        if hasattr(self, "schedule_button"):
            self.schedule_button.configure(state=tk.NORMAL if self.license_status.can_use else tk.DISABLED)
        if not self.license_status.can_use:
            self.status_var.set(f"Licence requise : {self.license_status.reason}")
        self._update_action_state()
        self._schedule_action_button_refresh()

    def _ensure_license_for_action(self, *, parent: tk.Misc | None = None) -> bool:
        if self.license_status.can_use:
            return True
        messagebox.showwarning(
            "Licence requise",
            f"{self.license_status.reason}\n\nActivez SafeSweep pour lancer les analyses et les actions principales.",
            parent=parent or self,
        )
        self._open_activation_window(startup=False)
        return False

    def _open_activation_window(self, *, startup: bool = False) -> None:
        if self.activation_window and self.activation_window.winfo_exists():
            self._bring_dashboard_to_front(self.activation_window)
            return

        window = tk.Toplevel(self)
        self.activation_window = window
        window.title("Activation SafeSweep")
        window.geometry("560x350")
        window.minsize(500, 320)
        window.transient(self)
        window.columnconfigure(0, weight=1)

        def close_window() -> None:
            self.activation_window = None
            self.activation_status_var = None
            window.destroy()

        window.protocol("WM_DELETE_WINDOW", close_window)

        content = ttk.Frame(window, padding=16)
        content.grid(row=0, column=0, sticky="nsew")
        content.columnconfigure(1, weight=1)

        title = "Activation requise" if startup and not self.license_status.can_use else "Licence SafeSweep"
        ttk.Label(content, text=title, font=("Segoe UI", 12, "bold")).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(
            content,
            text=(
                "Entrez votre cle de licence client. SafeSweep enverra uniquement la cle, cet identifiant appareil local "
                "et le nom de l'ordinateur au portail de licences."
            ),
            wraplength=500,
            justify=tk.LEFT,
        ).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 14))

        license_key_var = tk.StringVar()
        server_url_var = tk.StringVar(value=self.license_status.server_url)
        self.activation_status_var = tk.StringVar(value=self._license_status_text())

        ttk.Label(content, text="Cle").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=(0, 8))
        key_entry = ttk.Entry(content, textvariable=license_key_var, width=38)
        key_entry.grid(row=2, column=1, sticky="ew", pady=(0, 8))

        ttk.Label(content, text="Serveur").grid(row=3, column=0, sticky="w", padx=(0, 8), pady=(0, 8))
        ttk.Entry(content, textvariable=server_url_var).grid(row=3, column=1, sticky="ew", pady=(0, 8))

        ttk.Label(content, text="Appareil").grid(row=4, column=0, sticky="w", padx=(0, 8), pady=(0, 8))
        ttk.Label(
            content,
            text=f"{self.license_status.device_name} - {self.license_status.device_id}",
            wraplength=420,
        ).grid(row=4, column=1, sticky="w", pady=(0, 8))

        ttk.Label(
            content,
            textvariable=self.activation_status_var,
            style="Status.TLabel",
            wraplength=500,
        ).grid(row=5, column=0, columnspan=2, sticky="ew", pady=(8, 12))

        buttons = ttk.Frame(content)
        buttons.grid(row=6, column=0, columnspan=2, sticky="e")

        def activate() -> None:
            self._activate_license_async(license_key_var.get(), server_url_var.get())

        def validate_current() -> None:
            self._validate_license_async(server_url=server_url_var.get(), show_message=True)

        ttk.Button(buttons, text="Verifier", command=validate_current).pack(side=tk.LEFT)
        ttk.Button(buttons, text="Activer", command=activate, style="Accent.TButton").pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(buttons, text="Fermer", command=close_window).pack(side=tk.LEFT, padx=(8, 0))

        self._center_child_window(window)
        key_entry.focus_set()

    def _activate_license_async(self, license_key: str, server_url: str) -> None:
        if self.license_busy:
            return
        self.license_busy = True
        if self.activation_status_var:
            self.activation_status_var.set("Activation en cours...")
        self.license_status_var.set("Licence : activation en cours...")

        def worker() -> None:
            try:
                manager = LicenseManager(api_base_url=server_url.strip() or None)
                status = manager.activate(license_key)
                self.ui_queue.put(("license_result", (status, "activate", True)))
            except Exception as exc:  # noqa: BLE001 - surfaced to the user
                logger.exception("Erreur activation licence")
                self.ui_queue.put(("license_error", str(exc)))

        threading.Thread(target=worker, name="safesweep-license-activate", daemon=True).start()

    def _validate_license_async(self, *, server_url: str | None = None, show_message: bool) -> None:
        if self.license_busy:
            return
        self.license_busy = True
        if self.activation_status_var:
            self.activation_status_var.set("Verification de la licence...")

        def worker() -> None:
            try:
                manager = LicenseManager(api_base_url=server_url.strip() if server_url else None)
                status = manager.validate_saved_license()
                self.ui_queue.put(("license_result", (status, "validate", show_message)))
            except Exception as exc:  # noqa: BLE001 - surfaced to the user
                logger.exception("Erreur verification licence")
                self.ui_queue.put(("license_error", str(exc)))

        threading.Thread(target=worker, name="safesweep-license-validate", daemon=True).start()

    def _finish_license_result(self, status: LicenseStatus, action: str, show_message: bool) -> None:
        self.license_busy = False
        self.license_status = status
        self._update_license_ui()
        if self.activation_status_var:
            self.activation_status_var.set(self._license_status_text())

        if status.can_use:
            if show_message:
                messagebox.showinfo("Licence SafeSweep", "Licence activee sur cet appareil.", parent=self)
            if self.activation_window and self.activation_window.winfo_exists():
                self.activation_window.destroy()
                self.activation_window = None
                self.activation_status_var = None
            return

        if show_message or action == "activate" or status.source == "server":
            messagebox.showwarning("Licence SafeSweep", status.reason, parent=self)
        if action == "validate" and status.source == "server":
            self._open_activation_window(startup=True)

    def _finish_license_error(self, message: str) -> None:
        self.license_busy = False
        if self.activation_status_var:
            self.activation_status_var.set(f"Erreur licence : {message}")
        self.license_status_var.set(f"Licence : erreur - {message}")
        messagebox.showerror("Licence SafeSweep", message, parent=self)

    def _open_startup_dashboard(self) -> None:
        if self.dashboard_window and self.dashboard_window.winfo_exists():
            self._bring_dashboard_to_front(self.dashboard_window)
            return

        metrics = self._dashboard_metrics()
        window = tk.Toplevel(self)
        self.dashboard_window = window
        window.title("Tableau de bord")
        window.geometry("980x740")
        window.minsize(840, 660)
        window.transient(self)
        window.configure(bg="#eef3f8")
        window.columnconfigure(0, weight=1)
        window.rowconfigure(3, weight=1)

        def close_dashboard() -> None:
            self.dashboard_window = None
            window.destroy()

        window.protocol("WM_DELETE_WINDOW", close_dashboard)

        header = tk.Frame(window, bg="#0f5263", padx=22, pady=18)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        tk.Label(
            header,
            text="Tableau de bord",
            bg="#0f5263",
            fg="#ffffff",
            font=("Segoe UI", 22, "bold"),
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            header,
            text="Choisissez un nettoyage, surveillez la quarantaine et lancez les actions courantes.",
            bg="#0f5263",
            fg="#c9edf3",
            font=("Segoe UI", 10),
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))
        tk.Button(
            header,
            text="Fermer",
            command=close_dashboard,
            bg="#ffffff",
            fg="#0f5263",
            activebackground="#e2f3f6",
            activeforeground="#0f5263",
            relief=tk.FLAT,
            padx=14,
            pady=6,
            cursor="hand2",
        ).grid(row=0, column=1, rowspan=2, sticky="e")

        stats = tk.Frame(window, bg="#eef3f8", padx=18, pady=14)
        stats.grid(row=1, column=0, sticky="ew")
        for index in range(4):
            stats.columnconfigure(index, weight=1, uniform="stats")

        self._dashboard_metric_card(stats, 0, "Quarantaine", metrics["quarantine"], "#176a31")
        self._dashboard_metric_card(stats, 1, "Expirés", metrics["expired"], "#9f1d1d")
        self._dashboard_metric_card(stats, 2, "Liste blanche", metrics["protected"], "#6b5c00")
        self._dashboard_metric_card(stats, 3, "Planification", metrics["schedule"], "#22577a")

        dashboard_folder_var = tk.StringVar(value=self.folder_var.get())
        folder_bar = tk.Frame(window, bg="#dfe8f0", padx=18, pady=10)
        folder_bar.grid(row=2, column=0, sticky="ew")
        folder_bar.columnconfigure(1, weight=1)
        tk.Label(
            folder_bar,
            text="Dossier à analyser",
            bg="#dfe8f0",
            fg="#263746",
            font=("Segoe UI", 9, "bold"),
        ).grid(row=0, column=0, sticky="w", padx=(0, 10))
        tk.Entry(
            folder_bar,
            textvariable=dashboard_folder_var,
            relief=tk.SOLID,
            highlightthickness=0,
        ).grid(row=0, column=1, sticky="ew", padx=(0, 8))
        tk.Button(
            folder_bar,
            text="Parcourir",
            command=lambda: self._dashboard_choose_folder(dashboard_folder_var, window),
            bg="#ffffff",
            fg="#263746",
            activebackground="#f4f7fb",
            relief=tk.FLAT,
            padx=12,
            pady=5,
            cursor="hand2",
        ).grid(row=0, column=2, padx=(0, 8))
        tk.Button(
            folder_bar,
            text="Bureau",
            command=lambda: self._dashboard_choose_desktop(dashboard_folder_var),
            bg="#ffffff",
            fg="#263746",
            activebackground="#f4f7fb",
            relief=tk.FLAT,
            padx=12,
            pady=5,
            cursor="hand2",
        ).grid(row=0, column=3)

        body = tk.Frame(window, bg="#eef3f8", padx=18)
        body.grid(row=3, column=0, sticky="nsew", pady=(0, 14))
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(0, weight=1)

        quick = tk.LabelFrame(
            body,
            text="Analyses rapides",
            bg="#eef3f8",
            fg="#263746",
            font=("Segoe UI", 10, "bold"),
            padx=12,
            pady=12,
        )
        quick.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        quick.columnconfigure(0, weight=1)
        quick.columnconfigure(1, weight=1)

        tiles = (
            ("Nettoyage prudent", "Documents anciens et fichiers sûrs", "#176a31"),
            ("Doublons exacts", "Copies identiques par hash SHA-256", "#7b2cbf"),
            ("Gros dossiers", "Caches, exports et projets volumineux", "#5f6c37"),
            ("Téléchargements", "Installateurs, archives et ISO oubliés", "#0f6b8a"),
            ("Applications désinstallables", "Registre Windows et désinstallateurs", "#8a4b0f"),
            ("Archives anciennes", "ZIP, ISO et sauvegardes anciennes", "#6b5c00"),
        )
        for index, (profile_name, subtitle, color) in enumerate(tiles):
            self._dashboard_profile_tile(
                quick,
                row=index // 2,
                column=index % 2,
                profile_name=profile_name,
                subtitle=subtitle,
                color=color,
                dashboard=window,
                folder_var=dashboard_folder_var,
            )

        side = tk.LabelFrame(
            body,
            text="Actions",
            bg="#eef3f8",
            fg="#263746",
            font=("Segoe UI", 10, "bold"),
            padx=12,
            pady=12,
        )
        side.grid(row=0, column=1, sticky="nsew")
        side.columnconfigure(0, weight=1)

        self._dashboard_action_button(side, 0, "Gérer la quarantaine", "#9f1d1d", self._open_quarantine_window)
        self._dashboard_action_button(side, 1, "Historique des actions", "#425466", self._open_action_history_window)
        self._dashboard_action_button(side, 2, "Liste blanche", "#6b5c00", self._open_protection_window)
        self._dashboard_action_button(side, 3, "Planification", "#22577a", self._open_schedule_window)

        footer = tk.Frame(window, bg="#dfe8f0", padx=18, pady=10)
        footer.grid(row=4, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)
        tk.Label(
            footer,
            text=f"{_('Profil courant')} : {self.profile_var.get() or _('personnalisé')}",
            bg="#dfe8f0",
            fg="#425466",
            font=("Segoe UI", 9),
        ).grid(row=0, column=0, sticky="w")
        tk.Button(
            footer,
            text="Ouvrir sans lancer",
            command=close_dashboard,
            bg="#ffffff",
            fg="#263746",
            activebackground="#f4f7fb",
            relief=tk.FLAT,
            padx=12,
            pady=5,
            cursor="hand2",
        ).grid(row=0, column=1, sticky="e")

        window.update_idletasks()
        self._center_child_window(window)
        self._bring_dashboard_to_front(window)

    def _bring_dashboard_to_front(self, window: tk.Toplevel) -> None:
        try:
            window.deiconify()
            window.lift(self)
            window.attributes("-topmost", True)
            window.focus_force()
            self.after(900, lambda: self._release_dashboard_topmost(window))
        except tk.TclError:
            pass

    @staticmethod
    def _release_dashboard_topmost(window: tk.Toplevel) -> None:
        try:
            if window.winfo_exists():
                window.attributes("-topmost", False)
        except tk.TclError:
            pass

    def _dashboard_metrics(self) -> dict[str, str]:
        quarantine = "0"
        expired = "0"
        protected = "0"
        schedule = "Inactive"

        try:
            records = self.quarantine_manager.list_records()
            settings = self.quarantine_manager.load_settings()
            now = datetime.now().timestamp()
            quarantine = str(len(records))
            expired = str(sum(1 for record in records if self.quarantine_manager.expires_at(record, settings) <= now))
        except QuarantineError:
            quarantine = "?"
            expired = "?"

        try:
            protection = self.protection_list.load()
            protected = str(len(protection.protected_paths) + len(protection.protected_extensions))
        except ProtectionError:
            protected = "?"

        try:
            config = self._load_schedule_config()
            info = query_scheduled_task()
            schedule = "Active" if info.exists else ("Config" if config else "Inactive")
        except (SchedulerError, OSError):
            schedule = "?"

        return {
            "quarantine": quarantine,
            "expired": expired,
            "protected": protected,
            "schedule": schedule,
        }

    @staticmethod
    def _dashboard_metric_card(parent: tk.Widget, column: int, title: str, value: str, color: str) -> None:
        card = tk.Frame(parent, bg="#ffffff", highlightbackground="#d5e0ea", highlightthickness=1, padx=12, pady=10)
        card.grid(row=0, column=column, sticky="ew", padx=5)
        tk.Frame(card, bg=color, width=5, height=44).grid(row=0, column=0, rowspan=2, sticky="ns", padx=(0, 10))
        tk.Label(card, text=title, bg="#ffffff", fg="#5d6d7e", font=("Segoe UI", 9)).grid(row=0, column=1, sticky="w")
        tk.Label(card, text=value, bg="#ffffff", fg=color, font=("Segoe UI", 20, "bold")).grid(row=1, column=1, sticky="w")

    def _dashboard_profile_tile(
        self,
        parent: tk.Widget,
        *,
        row: int,
        column: int,
        profile_name: str,
        subtitle: str,
        color: str,
        dashboard: tk.Toplevel,
        folder_var: tk.StringVar,
    ) -> None:
        tile = tk.Frame(parent, bg=color, padx=12, pady=12)
        tile.grid(row=row, column=column, sticky="nsew", padx=6, pady=6)
        parent.rowconfigure(row, weight=1)
        tile.columnconfigure(0, weight=1)
        tk.Label(tile, text=profile_name, bg=color, fg="#ffffff", font=("Segoe UI", 12, "bold")).grid(
            row=0,
            column=0,
            sticky="w",
        )
        tk.Label(tile, text=subtitle, bg=color, fg="#eef7f9", font=("Segoe UI", 9), wraplength=220).grid(
            row=1,
            column=0,
            sticky="w",
            pady=(5, 10),
        )
        tk.Button(
            tile,
            text="Analyser",
            command=lambda: self._dashboard_start_profile(profile_name, dashboard, folder_var),
            bg="#ffffff",
            fg=color,
            activebackground="#f4f7fb",
            activeforeground=color,
            relief=tk.FLAT,
            padx=12,
            pady=5,
            cursor="hand2",
        ).grid(row=2, column=0, sticky="e")

    def _dashboard_action_button(self, parent: tk.Widget, row: int, text: str, color: str, command: Callable[[], None]) -> None:
        def wrapped() -> None:
            command()

        button = tk.Button(
            parent,
            text=text,
            command=wrapped,
            bg=color,
            fg="#ffffff",
            activebackground=color,
            activeforeground="#ffffff",
            relief=tk.FLAT,
            padx=12,
            pady=10,
            anchor="w",
            cursor="hand2",
        )
        button.grid(row=row, column=0, sticky="ew", pady=6)

    def _dashboard_choose_folder(self, folder_var: tk.StringVar, parent: tk.Toplevel) -> None:
        initial_dir = folder_var.get().strip() or self.folder_var.get().strip() or str(Path.home())
        selected = filedialog.askdirectory(parent=parent, initialdir=initial_dir)
        if selected:
            folder_var.set(selected)

    @staticmethod
    def _dashboard_choose_desktop(folder_var: tk.StringVar) -> None:
        for candidate in (
            Path.home() / "OneDrive" / "Bureau",
            Path.home() / "OneDrive" / "Desktop",
            Path.home() / "Desktop",
        ):
            if candidate.exists():
                folder_var.set(str(candidate))
                return
        folder_var.set(str(Path.home()))

    def _dashboard_start_profile(self, profile_name: str, dashboard: tk.Toplevel, folder_var: tk.StringVar) -> None:
        if not self._ensure_license_for_action(parent=dashboard):
            return

        folder_text = folder_var.get().strip()
        if not folder_text:
            messagebox.showinfo("Dossier manquant", "Choisissez un dossier à analyser.", parent=dashboard)
            return

        folder_path = Path(os.path.expandvars(folder_text)).expanduser()
        if not folder_path.exists() or not folder_path.is_dir():
            messagebox.showerror("Dossier introuvable", f"Ce dossier n'existe pas : {folder_text}", parent=dashboard)
            return

        self.profile_var.set(profile_name)
        self._apply_selected_profile()
        self.folder_var.set(str(folder_path.resolve(strict=False)))
        try:
            dashboard.destroy()
        except tk.TclError:
            pass
        self.dashboard_window = None
        self.after(80, self._start_scan)

    def _center_child_window(self, window: tk.Toplevel) -> None:
        try:
            self.update_idletasks()
            width = window.winfo_width()
            height = window.winfo_height()
            parent_x = self.winfo_rootx()
            parent_y = self.winfo_rooty()
            parent_width = self.winfo_width()
            parent_height = self.winfo_height()
            x = parent_x + max(0, (parent_width - width) // 2)
            y = parent_y + max(0, (parent_height - height) // 2)
            window.geometry(f"+{x}+{y}")
        except tk.TclError:
            pass

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        controls = ttk.Frame(self, style="Toolbar.TFrame", padding=(8, 6), relief=tk.SOLID, borderwidth=1)
        controls.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
        controls.columnconfigure(1, weight=1)

        brand_label = ttk.Label(
            controls,
            text=APP_NAME,
            image=self.brand_icon_image,
            compound=tk.LEFT,
            style="Brand.TLabel",
        )
        brand_label.grid(row=0, column=0, sticky="w", padx=(0, 14), pady=(0, 5))

        actions = ttk.Frame(controls, style="Surface.TFrame")
        actions.grid(row=0, column=1, sticky="w", pady=(0, 5))

        self.cancel_button = ttk.Button(
            actions,
            text="Annuler",
            command=self._cancel_scan,
            state=tk.DISABLED,
            style="Secondary.TButton",
        )
        self.cancel_button.pack(side=tk.LEFT)

        self.selection_menu_button = ttk.Menubutton(
            actions,
            text="Sélection",
            state=tk.DISABLED,
            style="Toolbar.TMenubutton",
        )
        self.selection_menu = tk.Menu(self.selection_menu_button, tearoff=False)
        self.selection_menu.add_command(label="Tout cocher", command=self._check_all)
        self.selection_menu.add_command(label="Tout décocher", command=self._uncheck_all)
        self.selection_menu.add_command(label="Inverser", command=self._invert_checks)
        self.selection_menu.add_command(label="Cocher sélection", command=self._check_selected_rows)
        self.selection_menu.add_command(label="Décocher sélection", command=self._uncheck_selected_rows)
        self.selection_menu.add_separator()
        self.selection_menu.add_command(label="Cocher doublons sauf plus récent", command=self._check_duplicate_copies)
        self.selection_menu_button.configure(menu=self.selection_menu)
        self.selection_menu_button.pack(side=tk.LEFT, padx=(8, 0))

        self.results_menu_button = ttk.Menubutton(
            actions,
            text="Résultats",
            state=tk.DISABLED,
            style="Toolbar.TMenubutton",
        )
        self.results_menu = tk.Menu(self.results_menu_button, tearoff=False)
        self.results_menu.add_command(label="Trier par risque", command=lambda: self._sort_tree("risk", False))
        self.results_menu.add_command(label="Exporter CSV", command=self._export_csv)
        self.results_menu.add_command(label="Exporter HTML", command=self._export_html)
        self.results_menu.add_separator()
        self.results_menu.add_command(label="Aperçu rapide", command=self._preview_current)
        self.results_menu.add_command(label="Ouvrir l'emplacement", command=self._open_location)
        self.results_menu_button.configure(menu=self.results_menu)
        self.results_menu_button.pack(side=tk.LEFT, padx=(8, 0))

        self.actions_menu_button = ttk.Menubutton(
            actions,
            text="Actions",
            state=tk.DISABLED,
            style="Toolbar.TMenubutton",
        )
        self.actions_menu = tk.Menu(self.actions_menu_button, tearoff=False)
        self.actions_menu.add_command(label="Rapport de simulation...", command=self._simulation_checked)
        self.actions_menu.add_separator()
        self.actions_menu.add_command(label="Mettre en quarantaine...", command=self._quarantine_checked)
        self.actions_menu.add_command(label="Envoyer à la Corbeille...", command=self._delete_checked)
        self.actions_menu_button.configure(menu=self.actions_menu)
        self.actions_menu_button.pack(side=tk.LEFT, padx=(8, 0))

        self.quarantine_menu_button = ttk.Menubutton(actions, text="Quarantaine", style="Toolbar.TMenubutton")
        self.quarantine_menu = tk.Menu(self.quarantine_menu_button, tearoff=False)
        self.quarantine_menu.add_command(label="Gérer la quarantaine", command=self._open_quarantine_window)
        self.quarantine_menu.add_command(label="Historique des actions", command=self._open_action_history_window)
        self.quarantine_menu_button.configure(menu=self.quarantine_menu)
        self.quarantine_menu_button.pack(side=tk.LEFT, padx=(8, 0))

        self.protection_button = ttk.Button(
            actions,
            text="Liste blanche",
            command=self._open_protection_window,
            style="Secondary.TButton",
        )
        self.protection_button.pack(side=tk.LEFT, padx=(8, 0))

        self.schedule_button = ttk.Button(
            actions,
            text="Planification",
            command=self._open_schedule_window,
            style="Secondary.TButton",
        )
        self.schedule_button.pack(side=tk.LEFT, padx=(8, 0))

        self.dashboard_button = ttk.Button(
            actions,
            text="Tableau de bord",
            command=self._open_startup_dashboard,
            style="Secondary.TButton",
        )
        self.dashboard_button.pack(side=tk.LEFT, padx=(8, 0))

        profile_frame = ttk.Frame(controls, style="Surface.TFrame")
        profile_frame.grid(row=0, column=2, columnspan=3, sticky="e", pady=(0, 5))
        ttk.Label(profile_frame, text="Profil", style="Surface.TLabel").pack(side=tk.LEFT, padx=(0, 6))
        self.profile_combo = ttk.Combobox(
            profile_frame,
            textvariable=self.profile_var,
            values=tuple(_(name) for name in profile_names()),
            state="readonly",
            width=24,
        )
        self.profile_combo.pack(side=tk.LEFT)
        self.profile_combo.bind("<<ComboboxSelected>>", lambda _event: self._apply_selected_profile())
        ttk.Label(profile_frame, text="Langue", style="Surface.TLabel").pack(side=tk.LEFT, padx=(14, 6))
        self.language_combo = ttk.Combobox(
            profile_frame,
            textvariable=self.language_var,
            values=language_choices(),
            state="readonly",
            width=12,
        )
        self.language_combo.pack(side=tk.LEFT)
        self.language_combo.bind("<<ComboboxSelected>>", lambda _event: self._on_language_selected())
        ttk.Label(profile_frame, text=f"Version {__version__}", style="Muted.Surface.TLabel").pack(
            side=tk.LEFT,
            padx=(14, 0),
        )
        ttk.Label(profile_frame, textvariable=self.license_status_var, style="Muted.Surface.TLabel").pack(
            side=tk.LEFT,
            padx=(14, 0),
        )
        ttk.Button(
            profile_frame,
            text="Licence",
            command=lambda: self._open_activation_window(startup=False),
            style="Secondary.TButton",
        ).pack(side=tk.LEFT, padx=(8, 0))

        ttk.Label(controls, text="Dossier", style="Surface.TLabel").grid(row=1, column=0, sticky="w", padx=(0, 8))
        folder_entry = ttk.Entry(controls, textvariable=self.folder_var)
        folder_entry.grid(row=1, column=1, sticky="ew", padx=(0, 8), pady=(0, 4))
        ttk.Button(controls, text="Parcourir", command=self._choose_folder, style="Secondary.TButton").grid(
            row=1,
            column=2,
            padx=(0, 6),
            pady=(0, 4),
        )
        ttk.Button(controls, text="Bureau", command=self._choose_desktop, style="Secondary.TButton").grid(
            row=1,
            column=3,
            padx=(0, 6),
            pady=(0, 4),
        )
        self.scan_button = ttk.Button(controls, text="Analyser", command=self._start_scan, style="Accent.TButton")
        self.scan_button.grid(row=1, column=4, pady=(0, 4))

        settings = ttk.Frame(controls, style="Surface.TFrame")
        settings.grid(row=2, column=0, columnspan=5, sticky="ew", pady=(2, 0))
        settings.columnconfigure(17, weight=1)
        self.mode_buttons.clear()

        ttk.Label(settings, text="Mode", style="Surface.TLabel").grid(row=0, column=0, sticky="w")
        self.scan_mode_combo = ttk.Combobox(
            settings,
            textvariable=self.scan_mode_label_var,
            values=tuple(SCAN_MODE_BY_LABEL.keys()),
            state="readonly",
            width=18,
        )
        self.scan_mode_combo.grid(row=0, column=1, sticky="w", padx=(6, 14))
        self.scan_mode_combo.bind("<<ComboboxSelected>>", lambda _event: self._on_scan_mode_label_changed())

        self.days_label = ttk.Label(settings, text="Inactif", style="Surface.TLabel")
        self.days_label.grid(row=0, column=2, sticky="w")
        self.days_spinbox = ttk.Spinbox(settings, from_=0, to=3650, textvariable=self.days_var, width=7)
        self.days_spinbox.grid(row=0, column=3, padx=(5, 4))
        self.days_unit_label = ttk.Label(settings, text="jours", style="Surface.TLabel")
        self.days_unit_label.grid(row=0, column=4, sticky="w", padx=(0, 12))

        ttk.Label(settings, text="Taille", style="Surface.TLabel").grid(row=0, column=5, sticky="w")
        ttk.Entry(settings, textvariable=self.min_size_var, width=7).grid(row=0, column=6, padx=(5, 4))
        ttk.Label(settings, text="Mo", style="Surface.TLabel").grid(row=0, column=7, sticky="w", padx=(0, 12))

        ttk.Label(settings, text="Ext.", style="Surface.TLabel").grid(row=0, column=8, sticky="w")
        ttk.Entry(settings, textvariable=self.extensions_var, width=14).grid(row=0, column=9, padx=(5, 12))

        self.age_basis_label = ttk.Label(settings, text="Date", style="Surface.TLabel")
        self.age_basis_label.grid(row=0, column=10, sticky="w")
        self.age_basis_combo = ttk.Combobox(
            settings,
            textvariable=self.age_basis_var,
            values=list(AGE_BASIS_BY_LABEL.keys()),
            state="readonly",
            width=17,
        )
        self.age_basis_combo.grid(row=0, column=11, sticky="w", padx=(5, 12))
        self.age_basis_combo.bind("<<ComboboxSelected>>", lambda _event: self._update_note())

        ttk.Checkbutton(settings, text="Caches/système", variable=self.skip_system_var).grid(
            row=0, column=12, sticky="w", padx=(0, 10)
        )
        ttk.Checkbutton(settings, text="Fichiers cachés", variable=self.skip_hidden_var).grid(
            row=0, column=13, sticky="w", padx=(0, 10)
        )

        note = ttk.Label(
            controls,
            textvariable=self.note_var,
            style="Muted.Surface.TLabel",
            wraplength=1200,
        )
        note.grid(row=3, column=0, columnspan=4, sticky="w", pady=(4, 0))

        self.progress = ttk.Progressbar(controls, mode="indeterminate", style="Horizontal.TProgressbar")
        self.progress.grid(row=3, column=4, sticky="ew", pady=(5, 0))

        filters = ttk.Frame(controls, style="Surface.TFrame")
        filters.grid(row=4, column=0, columnspan=5, sticky="ew", pady=(5, 0))
        filters.columnconfigure(1, weight=2)
        filters.columnconfigure(5, weight=1)

        ttk.Label(filters, text="Mot-clé", style="Surface.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Entry(filters, textvariable=self.filter_text_var, width=28).grid(
            row=0, column=1, sticky="ew", padx=(5, 10)
        )

        ttk.Label(filters, text="Risque", style="Surface.TLabel").grid(row=0, column=2, sticky="w")
        risk_combo = ttk.Combobox(
            filters,
            textvariable=self.filter_risk_var,
            values=translate_sequence(("Tous", "Faible", "Moyen", "Élevé", "Critique")),
            state="readonly",
            width=10,
        )
        risk_combo.grid(row=0, column=3, sticky="w", padx=(5, 10))

        ttk.Label(filters, text="Action", style="Surface.TLabel").grid(row=0, column=4, sticky="w")
        recommendation_combo = ttk.Combobox(
            filters,
            textvariable=self.filter_recommendation_var,
            values=translate_sequence(
                ("Toutes", "Supprimable", "Quarantaine", "Désinstaller", "Garder", "Nettoyer via Windows")
            ),
            state="readonly",
            width=19,
        )
        recommendation_combo.grid(row=0, column=5, sticky="ew", padx=(5, 10))

        ttk.Label(filters, text="Ext.", style="Surface.TLabel").grid(row=0, column=6, sticky="w")
        ttk.Entry(filters, textvariable=self.filter_extension_var, width=12).grid(
            row=0, column=7, sticky="w", padx=(5, 10)
        )
        ttk.Button(filters, text="Réinitialiser", command=self._reset_filters, style="Secondary.TButton").grid(
            row=0,
            column=8,
            sticky="e",
        )

        ttk.Label(filters, text="Dossier", style="Surface.TLabel").grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Entry(filters, textvariable=self.filter_folder_var, width=28).grid(
            row=1, column=1, sticky="ew", padx=(5, 10), pady=(4, 0)
        )

        ttk.Label(filters, text="Taille", style="Surface.TLabel").grid(row=1, column=2, sticky="w", pady=(4, 0))
        ttk.Entry(filters, textvariable=self.filter_min_size_var, width=8).grid(
            row=1, column=3, sticky="w", padx=(5, 4), pady=(4, 0)
        )
        ttk.Label(filters, text="à", style="Surface.TLabel").grid(row=1, column=4, sticky="w", pady=(4, 0))
        ttk.Entry(filters, textvariable=self.filter_max_size_var, width=8).grid(
            row=1, column=5, sticky="w", padx=(5, 10), pady=(4, 0)
        )

        ttk.Label(filters, text="Groupe/Indice", style="Surface.TLabel").grid(
            row=1,
            column=6,
            sticky="w",
            pady=(4, 0),
        )
        ttk.Entry(filters, textvariable=self.filter_group_var, width=12).grid(
            row=1, column=7, sticky="w", padx=(5, 10), pady=(4, 0)
        )

        table_frame = ttk.Frame(self, style="Surface.TFrame", padding=(0, 0), relief=tk.SOLID, borderwidth=1)
        table_frame.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 4))
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)

        columns = (
            "checked",
            "type",
            "risk",
            "recommendation",
            "group",
            "name",
            "folder",
            "size",
            "last_activity",
            "accessed",
            "modified",
            "path",
        )
        displayed_columns = tuple(column for column in columns if column != "folder")
        self.tree = ttk.Treeview(
            table_frame,
            columns=columns,
            displaycolumns=displayed_columns,
            show="headings",
            selectmode="extended",
        )
        self.tree.heading("checked", text="✓", command=lambda: self._sort_tree("checked", False))
        self.tree.heading("type", text="Type", command=lambda: self._sort_tree("type", False))
        self.tree.heading("risk", text="Risque", command=lambda: self._sort_tree("risk", False))
        self.tree.heading("recommendation", text="Action", command=lambda: self._sort_tree("recommendation", False))
        self.tree.heading("group", text="Groupe/Indice", command=lambda: self._sort_tree("group", False))
        self.tree.heading("name", text="Nom", command=lambda: self._sort_tree("name", False))
        self.tree.heading("folder", text="Dossier", command=lambda: self._sort_tree("folder", False))
        self.tree.heading("size", text="Taille", command=lambda: self._sort_tree("size", True))
        self.tree.heading("last_activity", text="Date retenue", command=lambda: self._sort_tree("last_activity", False))
        self.tree.heading("accessed", text="Dernier accès", command=lambda: self._sort_tree("accessed", False))
        self.tree.heading("modified", text="Modifié", command=lambda: self._sort_tree("modified", False))
        self.tree.heading("path", text="Chemin", command=lambda: self._sort_tree("path", False))

        self.tree.column("checked", width=34, minwidth=34, anchor=tk.CENTER, stretch=False)
        self.tree.column("type", width=92, minwidth=82, anchor=tk.CENTER, stretch=False)
        self.tree.column("risk", width=76, minwidth=70, anchor=tk.CENTER, stretch=False)
        self.tree.column("recommendation", width=122, minwidth=112, anchor=tk.CENTER, stretch=False)
        self.tree.column("group", width=105, minwidth=76, anchor=tk.CENTER, stretch=False)
        self.tree.column("name", width=180, minwidth=130, stretch=False)
        self.tree.column("folder", width=220, minwidth=160, stretch=False)
        self.tree.column("size", width=86, minwidth=76, anchor=tk.E, stretch=False)
        self.tree.column("last_activity", width=132, minwidth=118, stretch=False)
        self.tree.column("accessed", width=132, minwidth=118, stretch=False)
        self.tree.column("modified", width=132, minwidth=118, stretch=False)
        self.tree.column("path", width=390, minwidth=180, stretch=True)

        def yview(*args: object) -> None:
            self.tree.yview(*args)
            self._schedule_action_button_refresh()

        def xview(*args: object) -> None:
            self.tree.xview(*args)
            self._schedule_action_button_refresh()

        y_scroll = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=yview)
        x_scroll = ttk.Scrollbar(table_frame, orient=tk.HORIZONTAL, command=xview)

        def yscroll_set(first: str, last: str) -> None:
            y_scroll.set(first, last)
            self._schedule_action_button_refresh()

        def xscroll_set(first: object, last: object) -> None:
            x_scroll.set(first, last)
            try:
                first_value = float(first)
                last_value = float(last)
            except (TypeError, ValueError):
                first_value = 0.0
                last_value = 1.0
            if first_value <= 0.0 and last_value >= 1.0:
                x_scroll.grid_remove()
            else:
                x_scroll.grid(row=1, column=0, sticky="ew")
            self._schedule_action_button_refresh()

        def on_tree_configure(_event: tk.Event) -> None:
            first, last = self.tree.xview()
            xscroll_set(first, last)

        self.tree.configure(yscrollcommand=yscroll_set, xscrollcommand=xscroll_set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        self.tree.tag_configure("risk_0", foreground="#176a31")
        self.tree.tag_configure("risk_1", foreground="#6b5c00")
        self.tree.tag_configure("risk_2", foreground="#9a4f00")
        self.tree.tag_configure("risk_3", foreground="#9f1d1d")
        self.tree.tag_configure("row_even", background=APP_SURFACE)
        self.tree.tag_configure("row_odd", background="#f8fbfd")

        self.tree.bind("<Button-1>", self._toggle_check_at_event)
        self.tree.bind("<Double-1>", self._toggle_row_at_event)
        self.tree.bind("<space>", lambda _event: self._toggle_selected_rows())
        self.tree.bind("<Button-3>", self._show_context_menu)
        self.tree.bind("<Control-Button-1>", self._show_context_menu)
        self.tree.bind("<Configure>", on_tree_configure, add="+")
        self.tree.bind("<MouseWheel>", lambda _event: self._schedule_action_button_refresh(), add="+")
        self.after_idle(lambda: xscroll_set(*self.tree.xview()))

        footer = ttk.Frame(self, style="StatusBar.TFrame")
        footer.grid(row=2, column=0, sticky="ew", padx=8, pady=(0, 8))
        footer.columnconfigure(0, weight=1)
        ttk.Label(footer, textvariable=self.status_var, style="StatusBar.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(footer, textvariable=self.total_var, style="StatusBar.TLabel").grid(row=0, column=1, sticky="e")
        self._bind_filter_traces()

    def _bind_filter_traces(self) -> None:
        for variable in (
            self.filter_text_var,
            self.filter_risk_var,
            self.filter_recommendation_var,
            self.filter_extension_var,
            self.filter_folder_var,
            self.filter_min_size_var,
            self.filter_max_size_var,
            self.filter_group_var,
        ):
            variable.trace_add("write", lambda *_args: self._apply_filters())

    def _reset_filters(self) -> None:
        self.filter_text_var.set("")
        self.filter_risk_var.set(_("Tous"))
        self.filter_recommendation_var.set(_("Toutes"))
        self.filter_extension_var.set("")
        self.filter_folder_var.set("")
        self.filter_min_size_var.set("")
        self.filter_max_size_var.set("")
        self.filter_group_var.set("")
        self._apply_filters()

    def _apply_filters(self) -> None:
        if not hasattr(self, "tree"):
            return

        min_size, max_size, size_error = self._filter_size_bounds()
        if size_error:
            self.filtered_results = []
            self._populate_tree([])
            self.total_var.set(f"0/{len(self.results)} résultat(s) - filtre taille invalide")
            self.status_var.set(size_error)
            self._update_action_state()
            return

        self.filtered_results = [
            candidate for candidate in self.results if self._candidate_matches_filters(candidate, min_size, max_size)
        ]
        self._populate_tree(self.filtered_results)
        self._refresh_total()
        self._update_action_state()

        if not self.results:
            return
        if self._has_active_filters():
            self.status_var.set(
                f"Filtre appliqué : {len(self.filtered_results)} résultat(s) visible(s) sur {len(self.results)}."
            )
        else:
            self.status_var.set(f"Filtres réinitialisés : {len(self.filtered_results)} résultat(s) visible(s).")

    def _candidate_matches_filters(
        self,
        candidate: FileCandidate,
        min_size: int | None,
        max_size: int | None,
    ) -> bool:
        path_text = str(candidate.path).casefold()
        name_text = self._candidate_display_name(candidate).casefold()
        text_filter = self.filter_text_var.get().strip().casefold()
        if text_filter and text_filter not in path_text and text_filter not in name_text:
            return False

        risk_filter = str(source_text(self.filter_risk_var.get()))
        if risk_filter != "Tous" and self._candidate_risk(candidate).label != risk_filter:
            return False

        recommendation_filter = str(source_text(self.filter_recommendation_var.get()))
        if recommendation_filter != "Toutes" and self._candidate_recommendation(candidate).label != recommendation_filter:
            return False

        extension_filter = normalize_extensions(self.filter_extension_var.get())
        if extension_filter and candidate.path.suffix.casefold() not in extension_filter:
            return False

        folder_filter = self.filter_folder_var.get().strip().casefold()
        if folder_filter:
            folder_text = str(candidate.path.parent).casefold()
            candidate_folder_text = str(candidate.path).casefold() if candidate.item_type == "Dossier" else folder_text
            if folder_filter not in folder_text and folder_filter not in candidate_folder_text:
                return False

        if min_size is not None and candidate.size < min_size:
            return False
        if max_size is not None and candidate.size > max_size:
            return False

        group_filter = self.filter_group_var.get().strip().casefold()
        if group_filter and group_filter not in self._candidate_group_label(candidate).casefold():
            return False

        return True

    def _filter_size_bounds(self) -> tuple[int | None, int | None, str | None]:
        min_size, min_error = self._filter_size_bytes(self.filter_min_size_var.get(), "Taille min.")
        max_size, max_error = self._filter_size_bytes(self.filter_max_size_var.get(), "Taille max.")
        if min_error:
            return None, None, min_error
        if max_error:
            return None, None, max_error
        if min_size is not None and max_size is not None and min_size > max_size:
            return None, None, "Le filtre de taille minimale doit être inférieur ou égal à la taille maximale."
        return min_size, max_size, None

    @staticmethod
    def _filter_size_bytes(value: str, label: str) -> tuple[int | None, str | None]:
        cleaned = value.strip().replace(",", ".")
        if not cleaned:
            return None, None
        try:
            amount = float(cleaned)
        except ValueError:
            return None, f"{label} : entrez un nombre en Mo."
        if amount < 0:
            return None, f"{label} : la taille doit être positive."
        return int(amount * 1024 * 1024), None

    def _has_active_filters(self) -> bool:
        return any(
            (
                self.filter_text_var.get().strip(),
                source_text(self.filter_risk_var.get()) != "Tous",
                source_text(self.filter_recommendation_var.get()) != "Toutes",
                self.filter_extension_var.get().strip(),
                self.filter_folder_var.get().strip(),
                self.filter_min_size_var.get().strip(),
                self.filter_max_size_var.get().strip(),
                self.filter_group_var.get().strip(),
            )
        )

    def _visible_results(self) -> list[FileCandidate]:
        if not self.results:
            return []
        if self.filtered_results or self._has_active_filters():
            return self.filtered_results
        return self.results

    def _visible_checked_paths(self) -> set[Path]:
        return {candidate.path for candidate in self._visible_results() if candidate.path in self.checked_paths}

    def _choose_folder(self) -> None:
        selected = filedialog.askdirectory(initialdir=self.folder_var.get() or str(Path.home()))
        if selected:
            self.folder_var.set(selected)

    def _choose_desktop(self) -> None:
        for candidate in (
            Path.home() / "OneDrive" / "Bureau",
            Path.home() / "OneDrive" / "Desktop",
            Path.home() / "Desktop",
        ):
            if candidate.exists():
                self.folder_var.set(str(candidate))
                return
        self.folder_var.set(str(Path.home()))

    def _on_language_selected(self) -> None:
        language = language_code_from_label(self.language_var.get())
        if language == current_language():
            return
        save_language(language)
        self.status_var.set("Langue enregistrée. Redémarrez SafeSweep pour tout afficher dans cette langue.")
        messagebox.showinfo(
            "Redémarrage nécessaire",
            "La langue sera appliquée au prochain démarrage de SafeSweep.",
            parent=self,
        )

    def _apply_selected_profile(self) -> None:
        profile = find_profile(str(source_text(self.profile_var.get())))
        if not profile:
            return

        self.profile_var.set(_(profile.name))
        self.folder_var.set(str(profile.root))
        self.scan_mode_var.set(profile.scan_mode)
        self.scan_mode_label_var.set(SCAN_MODE_LABELS.get(profile.scan_mode, SCAN_MODE_LABELS["unused"]))
        self.days_var.set(profile.days_unused)
        self.min_size_var.set(format_min_size_mb(profile.min_size_mb))
        self.extensions_var.set(format_profile_extensions(profile.extensions))
        self.age_basis_var.set(AGE_BASIS_LABELS.get(profile.age_basis, AGE_BASIS_LABELS["modified"]))
        self.skip_hidden_var.set(profile.skip_hidden)
        self.skip_system_var.set(profile.skip_system_locations)
        self._on_mode_changed()
        self.status_var.set(f"{_('Profil appliqué')} : {_(profile.name)}. {_(profile.description)}")

    def _on_scan_mode_label_changed(self) -> None:
        self.scan_mode_var.set(SCAN_MODE_BY_LABEL.get(self.scan_mode_label_var.get(), "unused"))
        self._on_mode_changed()

    def _on_mode_changed(self) -> None:
        mode = self.scan_mode_var.get()
        self.scan_mode_label_var.set(SCAN_MODE_LABELS.get(mode, SCAN_MODE_LABELS["unused"]))
        duplicate_mode = mode == "duplicates"
        folder_mode = mode == "folders"
        installer_mode = mode == "installers"
        uninstaller_mode = mode == "uninstallers"
        if duplicate_mode:
            self.scan_button.configure(text="Analyser doublons")
        elif folder_mode:
            self.scan_button.configure(text="Analyser dossiers")
        elif installer_mode:
            self.scan_button.configure(text="Analyser installateurs")
        elif uninstaller_mode:
            self.scan_button.configure(text="Rechercher désinstallateurs")
        else:
            self.scan_button.configure(text="Analyser")
        state = tk.DISABLED if duplicate_mode or uninstaller_mode else tk.NORMAL
        self.days_label.configure(state=state)
        self.days_spinbox.configure(state=state)
        self.days_unit_label.configure(state=state)
        self.age_basis_label.configure(state=state)
        self.age_basis_combo.configure(state="disabled" if duplicate_mode else "readonly")
        self._update_note()

        if not (self.scan_thread and self.scan_thread.is_alive()):
            self.results = []
            self.filtered_results = []
            self.checked_paths.clear()
            self._clear_tree()
            self.total_var.set("0 fichier - 0 o")
            self.status_var.set("Choisissez un dossier, puis lancez l'analyse.")
            self._update_action_state()

    def _update_note(self) -> None:
        if self.scan_mode_var.get() == "duplicates":
            self.note_var.set("Doublons exacts : comparaison par taille puis hash SHA-256 du contenu.")
            return
        if self.scan_mode_var.get() == "folders":
            self.note_var.set("Gros dossiers : taille cumulée des sous-dossiers, caches, exports, dépendances et anciens projets.")
            return
        if self.scan_mode_var.get() == "installers":
            self.note_var.set("Installateurs oubliés : vieux .exe, .msi, .zip, .iso et archives dans Downloads/Téléchargements.")
            return
        if self.scan_mode_var.get() == "uninstallers":
            self.note_var.set("Désinstallateurs : registre Windows et fichiers uninstall/uninst/unins*. Clic droit sur un résultat pour désinstaller.")
            return

        basis = self._age_basis()
        if basis == "modified":
            self.note_var.set("Signal utilisé : dernière modification seulement. Recommandé pour retrouver les vieux fichiers du Bureau.")
        elif basis == "accessed":
            self.note_var.set("Signal utilisé : dernier accès seulement. Attention : Windows/OneDrive peut le mettre à jour automatiquement.")
        else:
            self.note_var.set("Signal utilisé : accès ou modification, le plus récent des deux. Très prudent mais peut masquer de vieux fichiers.")

    def _start_scan(self) -> None:
        if not self._ensure_license_for_action(parent=self):
            return

        if self.scan_thread and self.scan_thread.is_alive():
            return

        try:
            options = self._read_options()
        except ValueError as exc:
            messagebox.showerror("Paramètres invalides", str(exc), parent=self)
            return

        mode = self.scan_mode_var.get()
        self.current_scan_mode = mode
        self.results_mode = mode
        self.results_age_basis = self._age_basis()
        self.cancel_event.clear()
        self.results = []
        self.filtered_results = []
        self.item_to_result.clear()
        self.checked_paths.clear()
        self._clear_tree()
        self._set_scanning_state(True)
        if mode == "duplicates":
            self.status_var.set("Analyse des doublons en cours...")
        elif mode == "folders":
            self.status_var.set("Analyse des gros dossiers en cours...")
        elif mode == "installers":
            self.status_var.set("Recherche d'installateurs oubliés en cours...")
        elif mode == "uninstallers":
            self.status_var.set("Recherche de désinstallateurs en cours...")
        else:
            self.status_var.set("Analyse en cours...")
        self.total_var.set("0 fichier - 0 o")
        self.progress.start(12)

        def worker() -> None:
            try:
                logger.info("Début analyse mode=%s root=%s", mode, options.root)
                if mode == "duplicates":
                    scanner = scan_for_duplicate_files
                elif mode == "folders":
                    scanner = scan_for_large_folders
                elif mode == "installers":
                    scanner = scan_for_forgotten_installers
                elif mode == "uninstallers":
                    scanner = scan_for_uninstallers
                else:
                    scanner = scan_for_unused_files
                results, stats = scanner(
                    options,
                    progress_callback=lambda stats, current: self.ui_queue.put(("scan_progress", (stats, current, mode))),
                    should_cancel=self.cancel_event.is_set,
                )
                logger.info(
                    "Fin analyse mode=%s scanned=%s matched=%s errors=%s hit_limit=%s cancelled=%s",
                    mode,
                    stats.scanned_files,
                    stats.matched_files,
                    stats.errors,
                    stats.hit_limit,
                    stats.cancelled,
                )
                self.ui_queue.put(("scan_done", (results, stats, mode)))
            except Exception as exc:  # noqa: BLE001 - surfaced to the user
                logger.exception("Erreur pendant l'analyse")
                self.ui_queue.put(("scan_error", str(exc)))

        self.scan_thread = threading.Thread(target=worker, name="unused-file-scan", daemon=True)
        self.scan_thread.start()

    def _read_options(self) -> ScanOptions:
        folder = self.folder_var.get().strip()
        if not folder:
            raise ValueError("Choisissez un dossier à analyser.")

        try:
            days = int(self.days_var.get())
        except (tk.TclError, ValueError) as exc:
            raise ValueError("Le nombre de jours doit être un entier.") from exc

        try:
            min_size_mb = float(self.min_size_var.get().replace(",", "."))
        except ValueError as exc:
            raise ValueError("La taille minimale doit être un nombre.") from exc

        protection_settings = self._protection_settings()
        return ScanOptions(
            root=Path(folder),
            days_unused=days,
            min_size_bytes=int(min_size_mb * 1024 * 1024),
            extension_filter=normalize_extensions(self.extensions_var.get()),
            age_basis=self._age_basis(),
            protected_paths=protection_settings.protected_paths,
            protected_extensions=protection_settings.protected_extensions,
            skip_hidden=self.skip_hidden_var.get(),
            skip_system_locations=self.skip_system_var.get(),
        )

    def _age_basis(self) -> str:
        return AGE_BASIS_BY_LABEL.get(self.age_basis_var.get(), "modified")

    def _protection_settings(self):
        try:
            return self.protection_list.load()
        except ProtectionError as exc:
            raise ValueError(str(exc)) from exc

    def _cancel_scan(self) -> None:
        self.cancel_event.set()
        self.status_var.set("Annulation demandée...")

    def _poll_queue(self) -> None:
        try:
            while True:
                event, payload = self.ui_queue.get_nowait()
                if event == "scan_progress":
                    stats, current, mode = payload  # type: ignore[misc]
                    self._show_progress(stats, current, mode)
                elif event == "scan_done":
                    results, stats, mode = payload  # type: ignore[misc]
                    self._finish_scan(results, stats, mode)
                elif event == "scan_error":
                    self._finish_with_error(str(payload))
                elif event == "delete_done":
                    self._finish_delete(payload)  # type: ignore[arg-type]
                elif event == "delete_error":
                    self._finish_delete_error(str(payload))
                elif event == "quarantine_done":
                    self._finish_quarantine(payload)  # type: ignore[arg-type]
                elif event == "quarantine_error":
                    self._finish_quarantine_error(str(payload))
                elif event == "license_result":
                    status, action, show_message = payload  # type: ignore[misc]
                    self._finish_license_result(status, action, show_message)
                elif event == "license_error":
                    self._finish_license_error(str(payload))
                elif event == "uninstall_verified_removed":
                    self._finish_uninstall_verified_removed(payload)  # type: ignore[arg-type]
                elif event == "uninstall_still_present":
                    self._finish_uninstall_still_present(payload)  # type: ignore[arg-type]
                elif event == "uninstall_verify_error":
                    self._finish_uninstall_verify_error(payload)  # type: ignore[arg-type]
        except queue.Empty:
            pass
        except Exception:
            self.report_callback_exception(*sys.exc_info())
        finally:
            try:
                self.after(120, self._poll_queue)
            except tk.TclError:
                pass

    def report_callback_exception(self, exc: type[BaseException], value: BaseException, tb: object) -> None:
        logger.error("Erreur interface non gérée", exc_info=(exc, value, tb))
        self.status_var.set("Erreur interface. Consultez le journal.")
        try:
            messagebox.showerror(
                "Erreur interface",
                f"{value}\n\nJournal : {LOG_FILE}",
                parent=self,
            )
        except tk.TclError:
            pass

    def _show_progress(self, stats: ScanStats, current: Path, mode: str) -> None:
        if mode == "duplicates":
            self.status_var.set(
                f"{stats.scanned_files} fichiers analysés, {stats.hashed_files} comparés - {current}"
            )
            self.total_var.set(
                f"{stats.duplicate_groups} groupe(s), {stats.matched_files} fichier(s) - "
                f"récupérable ~ {format_bytes(stats.matched_size_bytes)}"
            )
            return

        if mode == "folders":
            self.status_var.set(f"{stats.scanned_files} fichiers mesurés, {stats.matched_files} gros dossiers - {current}")
            self.total_var.set(f"{stats.matched_files} dossier(s) - {format_bytes(stats.matched_size_bytes)}")
            return

        if mode == "installers":
            self.status_var.set(
                f"{stats.scanned_files} fichiers analysés, {stats.matched_files} installateur(s) oublié(s) - {current}"
            )
            self.total_var.set(f"{stats.matched_files} fichier(s) - {format_bytes(stats.matched_size_bytes)}")
            return

        if mode == "uninstallers":
            self.status_var.set(
                f"{stats.scanned_files} fichiers inspectés, {stats.matched_files} désinstallateur(s) - {current}"
            )
            self.total_var.set(f"{stats.matched_files} application(s)")
            return

        self.status_var.set(f"{stats.scanned_files} fichiers analysés, {stats.matched_files} candidats - {current}")
        self.total_var.set(f"{stats.matched_files} fichier(s) - {format_bytes(stats.matched_size_bytes)}")

    def _finish_scan(self, results: list[FileCandidate], stats: ScanStats, mode: str) -> None:
        self.progress.stop()
        self._set_scanning_state(False)
        self.results = results
        self.results_mode = mode
        self._apply_filters()

        prefix = "Analyse annulée" if stats.cancelled else "Analyse terminée"
        suffix = " Limite de résultats atteinte." if stats.hit_limit else ""
        if mode == "duplicates":
            self.status_var.set(
                f"{prefix} : {stats.scanned_files} fichiers analysés, {stats.hashed_files} comparés, "
                f"{stats.duplicate_groups} groupe(s) de doublons, {stats.denied_dirs} dossiers refusés, "
                f"{stats.errors} erreur(s).{suffix}"
            )
        elif mode == "folders":
            self.status_var.set(
                f"{prefix} : {stats.scanned_files} fichiers mesurés, {stats.matched_files} gros dossier(s), "
                f"{stats.denied_dirs} dossiers refusés, {stats.errors} erreur(s).{suffix}"
            )
        elif mode == "installers":
            self.status_var.set(
                f"{prefix} : {stats.scanned_files} fichiers analysés, {stats.matched_files} installateur(s) oublié(s), "
                f"{stats.denied_dirs} dossiers refusés, {stats.errors} erreur(s).{suffix}"
            )
        elif mode == "uninstallers":
            self.status_var.set(
                f"{prefix} : {stats.scanned_files} fichiers inspectés, {stats.matched_files} désinstallateur(s), "
                f"{stats.denied_dirs} dossiers refusés, {stats.errors} erreur(s).{suffix}"
            )
        else:
            self.status_var.set(
                f"{prefix} : {stats.scanned_files} fichiers analysés, {stats.denied_dirs} dossiers refusés, "
                f"{stats.errors} erreur(s).{suffix}"
            )
        self._refresh_total()
        self._update_action_state()

    def _finish_with_error(self, message: str) -> None:
        self.progress.stop()
        self._set_scanning_state(False)
        self.status_var.set("Analyse interrompue.")
        messagebox.showerror("Erreur d'analyse", message, parent=self)
        self._update_action_state()

    def _populate_tree(self, results: list[FileCandidate]) -> None:
        self._clear_tree()
        for row_index, candidate in enumerate(results):
            risk = self._candidate_risk(candidate)
            recommendation = self._candidate_recommendation(candidate)
            item_id = self.tree.insert(
                "",
                tk.END,
                tags=(f"risk_{risk.score}", "row_odd" if row_index % 2 else "row_even"),
                values=(
                    "✓" if candidate.path in self.checked_paths else "",
                    _(candidate.item_type),
                    _(risk.label),
                    _(recommendation.label),
                    _(self._candidate_group_label(candidate)),
                    self._candidate_display_name(candidate),
                    str(candidate.path.parent),
                    format_bytes(candidate.size),
                    _format_datetime(self._candidate_retained_at(candidate)),
                    _format_datetime(candidate.accessed_at),
                    _format_datetime(candidate.modified_at),
                    str(candidate.path),
                ),
            )
            self.item_to_result[item_id] = candidate
        self._schedule_action_button_refresh()

    def _clear_tree(self) -> None:
        self._clear_action_buttons()
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.item_to_result.clear()

    def _clear_action_buttons(self) -> None:
        for button in self.action_buttons.values():
            try:
                button.destroy()
            except tk.TclError:
                pass
        self.action_buttons.clear()

    def _schedule_action_button_refresh(self) -> None:
        if self.action_button_refresh_pending:
            return
        self.action_button_refresh_pending = True
        try:
            self.after_idle(self._refresh_action_buttons)
        except tk.TclError:
            self.action_button_refresh_pending = False

    def _refresh_action_buttons(self) -> None:
        self.action_button_refresh_pending = False
        if not hasattr(self, "tree"):
            return

        visible_buttons: set[str] = set()
        for item_id in self.tree.get_children(""):
            candidate = self.item_to_result.get(item_id)
            if not candidate:
                continue

            bbox = self.tree.bbox(item_id, "recommendation")
            if not bbox:
                continue

            x, y, width, height = bbox
            if width < 40 or height < 18:
                continue

            license_ok = self._license_allows_use()
            if self._is_uninstaller_candidate(candidate):
                pending = self._uninstall_tracking_key(candidate) in self.pending_uninstall_keys
                text = "Vérification..." if pending else "Désinstaller"
                state = tk.DISABLED if pending or not license_ok else tk.NORMAL
                command = lambda item=item_id: self._uninstall_from_action_button(item)
                style = "TButton"
            elif self.results_mode == "uninstallers":
                continue
            else:
                delete_pending = self.delete_thread is not None and self.delete_thread.is_alive()
                text = "En cours..." if delete_pending else "Supprimer"
                state = tk.DISABLED if delete_pending or not license_ok else tk.NORMAL
                command = lambda item=item_id: self._delete_from_action_button(item)
                style = "Danger.TButton"

            button = self.action_buttons.get(item_id)
            if button is None:
                button = ttk.Button(
                    self.tree,
                )
                self.action_buttons[item_id] = button

            button.configure(
                command=command,
                style=style,
                text=text,
                state=state,
            )
            button.place(x=x + 4, y=y + 2, width=max(96, width - 8), height=max(22, height - 4))
            visible_buttons.add(item_id)

        for item_id, button in list(self.action_buttons.items()):
            if item_id not in visible_buttons:
                try:
                    button.destroy()
                except tk.TclError:
                    pass
                del self.action_buttons[item_id]

    def _uninstall_from_action_button(self, item_id: str) -> None:
        candidate = self.item_to_result.get(item_id)
        if not candidate:
            return
        self.tree.selection_set(item_id)
        self.tree.focus(item_id)
        self._uninstall_candidate(candidate)

    def _delete_from_action_button(self, item_id: str) -> None:
        candidate = self.item_to_result.get(item_id)
        if not candidate:
            return
        self.tree.selection_set(item_id)
        self.tree.focus(item_id)
        self._delete_candidates([candidate], "Sélectionnez au moins un fichier.")

    @staticmethod
    def _candidate_group_label(candidate: FileCandidate) -> str:
        if candidate.item_type == "Désinstallateur":
            return _uninstaller_source_label(candidate)
        if candidate.folder_hint:
            return candidate.folder_hint
        return str(candidate.duplicate_group) if candidate.duplicate_group else ""

    @staticmethod
    def _candidate_display_name(candidate: FileCandidate) -> str:
        if candidate.item_type == "Désinstallateur":
            return candidate.display_name or candidate.folder_hint or candidate.path.parent.name or candidate.path.name
        return candidate.path.name

    @staticmethod
    def _candidate_risk(candidate: FileCandidate) -> RiskAssessment:
        if candidate.item_type == "Désinstallateur":
            return UNINSTALLER_RISK
        if (
            candidate.item_type == "Installateur"
            and candidate.path.suffix.casefold() in FORGOTTEN_INSTALLER_BINARY_EXTENSIONS
        ):
            return FORGOTTEN_INSTALLER_RISK
        return assess_deletion_risk(candidate.path)

    @staticmethod
    def _candidate_recommendation(candidate: FileCandidate) -> ActionRecommendation:
        if candidate.item_type == "Désinstallateur":
            return UNINSTALLER_RECOMMENDATION
        recommendation = recommend_action(candidate.path)
        if candidate.item_type == "Installateur" and recommendation.label == "Garder":
            return FORGOTTEN_INSTALLER_RECOMMENDATION
        return recommendation

    @staticmethod
    def _set_menu_entry_state(menu: tk.Menu, label: str, enabled: bool) -> None:
        menu.entryconfigure(label, state=tk.NORMAL if enabled else tk.DISABLED)

    def _set_scanning_state(self, scanning: bool) -> None:
        self.scan_button.configure(state=tk.DISABLED if scanning or not self._license_allows_use() else tk.NORMAL)
        self.cancel_button.configure(state=tk.NORMAL if scanning else tk.DISABLED)
        self.profile_combo.configure(state=tk.DISABLED if scanning else "readonly")
        if hasattr(self, "scan_mode_combo"):
            self.scan_mode_combo.configure(state=tk.DISABLED if scanning else "readonly")
        for button in self.mode_buttons:
            button.configure(state=tk.DISABLED if scanning else tk.NORMAL)

        if scanning:
            for menu_button in (
                self.selection_menu_button,
                self.results_menu_button,
                self.actions_menu_button,
                self.quarantine_menu_button,
                self.protection_button,
                self.schedule_button,
            ):
                menu_button.configure(state=tk.DISABLED)
            return

        self.quarantine_menu_button.configure(state=tk.NORMAL)
        self.protection_button.configure(state=tk.NORMAL)
        self.schedule_button.configure(state=tk.NORMAL if self._license_allows_use() else tk.DISABLED)
        self._update_action_state()

    def _update_action_state(self) -> None:
        visible_results = self._visible_results()
        has_results = bool(visible_results)
        has_checked = bool(self._visible_checked_paths())
        license_ok = self._license_allows_use()
        can_act_on_checked = license_ok and has_results and has_checked
        can_modify_checked = can_act_on_checked and self.results_mode != "uninstallers"

        self.selection_menu_button.configure(state=tk.NORMAL if has_results else tk.DISABLED)
        self.results_menu_button.configure(state=tk.NORMAL if has_results else tk.DISABLED)
        self.actions_menu_button.configure(state=tk.NORMAL if can_act_on_checked else tk.DISABLED)

        self._set_menu_entry_state(self.selection_menu, "Tout cocher", has_results)
        self._set_menu_entry_state(self.selection_menu, "Tout décocher", has_results)
        self._set_menu_entry_state(self.selection_menu, "Inverser", has_results)
        self._set_menu_entry_state(self.selection_menu, "Cocher sélection", has_results)
        self._set_menu_entry_state(self.selection_menu, "Décocher sélection", has_results)
        self._set_menu_entry_state(
            self.selection_menu,
            "Cocher doublons sauf plus récent",
            has_results and self.results_mode == "duplicates",
        )

        self._set_menu_entry_state(self.results_menu, "Trier par risque", has_results)
        self._set_menu_entry_state(self.results_menu, "Exporter CSV", has_results)
        self._set_menu_entry_state(self.results_menu, "Exporter HTML", has_results)
        self._set_menu_entry_state(self.results_menu, "Aperçu rapide", has_results)
        self._set_menu_entry_state(self.results_menu, "Ouvrir l'emplacement", has_results)

        self._set_menu_entry_state(self.actions_menu, "Rapport de simulation...", can_act_on_checked)
        self._set_menu_entry_state(self.actions_menu, "Mettre en quarantaine...", can_modify_checked)
        self._set_menu_entry_state(self.actions_menu, "Envoyer à la Corbeille...", can_modify_checked)

    def _toggle_row_at_event(self, event: tk.Event) -> None:
        if self.tree.identify_column(event.x) == "#1":
            return
        item_id = self.tree.identify_row(event.y)
        if item_id:
            self._toggle_item(item_id)

    def _toggle_check_at_event(self, event: tk.Event) -> str | None:
        if self.tree.identify_region(event.x, event.y) != "cell":
            return None
        if self.tree.identify_column(event.x) != "#1":
            return None

        item_id = self.tree.identify_row(event.y)
        if not item_id:
            return None

        self.tree.focus(item_id)
        if not (event.state & 0x0005):
            self.tree.selection_set(item_id)
        self._toggle_item(item_id)
        return "break"

    def _toggle_selected_rows(self) -> None:
        for item_id in self.tree.selection():
            self._toggle_item(item_id)

    def _check_selected_rows(self) -> None:
        for item_id in self.tree.selection():
            candidate = self.item_to_result.get(item_id)
            if candidate:
                self.checked_paths.add(candidate.path)
        self._sync_tree_checks()
        self._update_action_state()

    def _uncheck_selected_rows(self) -> None:
        for item_id in self.tree.selection():
            candidate = self.item_to_result.get(item_id)
            if candidate:
                self.checked_paths.discard(candidate.path)
        self._sync_tree_checks()
        self._update_action_state()

    def _show_context_menu(self, event: tk.Event) -> str | None:
        item_id = self.tree.identify_row(event.y)
        if not item_id:
            return None

        if item_id not in self.tree.selection():
            self.tree.selection_set(item_id)
        self.tree.focus(item_id)

        candidates = self._context_candidates()
        if not candidates:
            return None

        target_label = "cet élément" if len(candidates) == 1 else f"ces {len(candidates)} éléments"
        menu = tk.Menu(self, tearoff=False)
        menu.add_command(label="Aperçu rapide", command=self._preview_context)
        menu.add_command(label="Ouvrir l'emplacement", command=self._open_context_location)
        menu.add_command(
            label="Copier le chemin" if len(candidates) == 1 else "Copier les chemins",
            command=self._copy_context_paths,
        )
        uninstaller = self._context_uninstaller_candidate()
        if uninstaller:
            pending = self._uninstall_tracking_key(uninstaller) in self.pending_uninstall_keys
            menu.add_command(
                label="Vérification en cours..." if pending else "Désinstaller...",
                state=tk.DISABLED if pending or not self._license_allows_use() else tk.NORMAL,
                command=lambda item=uninstaller: self._uninstall_candidate(item),
            )
        menu.add_command(label="Rapport de simulation...", command=self._simulation_context)
        menu.add_separator()
        menu.add_command(label=f"Cocher {target_label}", command=self._check_context_rows)
        menu.add_command(label=f"Décocher {target_label}", command=self._uncheck_context_rows)
        menu.add_command(label="Inverser le cochage", command=self._toggle_context_rows)
        menu.add_separator()
        if self.results_mode != "uninstallers":
            action_state = tk.NORMAL if self._license_allows_use() else tk.DISABLED
            menu.add_command(label="Mettre en quarantaine...", state=action_state, command=self._quarantine_context)
            menu.add_command(label="Envoyer à la Corbeille...", state=action_state, command=self._delete_context)
            menu.add_separator()
        menu.add_command(label="Protéger ce dossier", command=self._protect_context_parent)
        menu.add_command(label="Protéger cette extension", command=self._protect_context_extension)
        menu.add_separator()
        menu.add_command(label="Gérer la quarantaine", command=self._open_quarantine_window)
        menu.add_command(label="Gérer la liste blanche", command=self._open_protection_window)

        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"

    def _context_candidates(self) -> list[FileCandidate]:
        candidates: list[FileCandidate] = []
        for item_id in self.tree.selection():
            candidate = self.item_to_result.get(item_id)
            if candidate:
                candidates.append(candidate)
        return candidates

    def _context_uninstaller_candidate(self) -> FileCandidate | None:
        focused = self.item_to_result.get(self.tree.focus())
        if focused and self._is_uninstaller_candidate(focused):
            return focused
        candidates = self._context_candidates()
        if len(candidates) == 1 and self._is_uninstaller_candidate(candidates[0]):
            return candidates[0]
        return None

    @staticmethod
    def _is_uninstaller_candidate(candidate: FileCandidate) -> bool:
        return candidate.item_type == "Désinstallateur" and bool(candidate.launch_command or candidate.path.name)

    @staticmethod
    def _uninstall_tracking_key(candidate: FileCandidate) -> str:
        if candidate.source_hint:
            return f"{candidate.source_hint}|{candidate.display_name}|{' '.join(candidate.launch_command)}".casefold()
        if candidate.path:
            return os.path.normcase(os.fspath(candidate.path.resolve(strict=False)))
        return f"{candidate.display_name}|{' '.join(candidate.launch_command)}".casefold()

    def _check_context_rows(self) -> None:
        for candidate in self._context_candidates():
            self.checked_paths.add(candidate.path)
        self._sync_tree_checks()
        self._update_action_state()

    def _uncheck_context_rows(self) -> None:
        for candidate in self._context_candidates():
            self.checked_paths.discard(candidate.path)
        self._sync_tree_checks()
        self._update_action_state()

    def _toggle_context_rows(self) -> None:
        for item_id in self.tree.selection():
            self._toggle_item(item_id)

    def _toggle_item(self, item_id: str) -> None:
        candidate = self.item_to_result.get(item_id)
        if not candidate:
            return
        if candidate.path in self.checked_paths:
            self.checked_paths.remove(candidate.path)
            self.tree.set(item_id, "checked", "")
        else:
            self.checked_paths.add(candidate.path)
            self.tree.set(item_id, "checked", "✓")
        self._update_action_state()

    def _check_all(self) -> None:
        self.checked_paths.update(candidate.path for candidate in self._visible_results())
        self._sync_tree_checks()
        self._update_action_state()

    def _uncheck_all(self) -> None:
        for candidate in self._visible_results():
            self.checked_paths.discard(candidate.path)
        self._sync_tree_checks()
        self._update_action_state()

    def _invert_checks(self) -> None:
        visible_paths = {candidate.path for candidate in self._visible_results()}
        self.checked_paths = (self.checked_paths - visible_paths) | (visible_paths - self.checked_paths)
        self._sync_tree_checks()
        self._update_action_state()

    def _check_duplicate_copies(self) -> None:
        if self.results_mode != "duplicates":
            return

        checked: set[Path] = set()
        for group in self._duplicate_groups(self._visible_results()).values():
            keep = max(
                group,
                key=lambda item: (item.last_activity_at, item.modified_at, item.created_at, str(item.path).lower()),
            )
            checked.update(item.path for item in group if item.path != keep.path)

        visible_paths = {candidate.path for candidate in self._visible_results()}
        self.checked_paths = (self.checked_paths - visible_paths) | checked
        self._sync_tree_checks()
        self.status_var.set(
            f"{len(self._visible_checked_paths())} doublon(s) visible(s) coché(s), "
            "en gardant le plus récent de chaque groupe visible."
        )
        self._update_action_state()

    def _sync_tree_checks(self) -> None:
        for item_id, candidate in self.item_to_result.items():
            self.tree.set(item_id, "checked", "✓" if candidate.path in self.checked_paths else "")

    def _duplicate_groups(self, results: list[FileCandidate] | None = None) -> dict[int, list[FileCandidate]]:
        groups: dict[int, list[FileCandidate]] = {}
        source = self.results if results is None else results
        for candidate in source:
            if candidate.duplicate_group:
                groups.setdefault(candidate.duplicate_group, []).append(candidate)
        return {group_id: group for group_id, group in groups.items() if len(group) > 1}

    def _candidate_retained_at(self, candidate: FileCandidate) -> float:
        if self.results_mode == "duplicates":
            return candidate.last_activity_at
        if self.results_age_basis == "accessed":
            return candidate.accessed_at
        if self.results_age_basis == "activity":
            return candidate.last_activity_at
        return candidate.modified_at

    def _refresh_total(self) -> None:
        visible_results = self._visible_results()
        total_count = len(self.results)
        filtered = self._has_active_filters()
        count_prefix = f"{len(visible_results)}/{total_count}" if filtered else str(len(visible_results))

        if self.results_mode == "duplicates":
            groups = self._duplicate_groups(visible_results)
            reclaimable = sum(group[0].size * (len(group) - 1) for group in groups.values())
            self.total_var.set(
                f"{len(groups)} groupe(s), {count_prefix} fichier(s) - récupérable ~ {format_bytes(reclaimable)}"
            )
            return
        if self.results_mode == "folders":
            self.total_var.set(
                f"{count_prefix} dossier(s) - {format_bytes(sum(item.size for item in visible_results))}"
            )
            return
        if self.results_mode == "uninstallers":
            self.total_var.set(f"{count_prefix} application(s)")
            return

        self.total_var.set(f"{count_prefix} fichier(s) - {format_bytes(sum(item.size for item in visible_results))}")

    def _export_csv(self) -> None:
        visible_results = self._visible_results()
        if not visible_results:
            return
        filename = filedialog.asksaveasfilename(
            parent=self,
            title="Exporter les résultats",
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv"), ("Tous les fichiers", "*.*")],
        )
        if not filename:
            return
        try:
            write_csv_report(filename, self._report_rows(visible_results))
        except OSError as exc:
            messagebox.showerror("Export CSV", f"Impossible d'écrire le rapport : {exc}", parent=self)
            return
        self.status_var.set(f"CSV exporté : {filename}")

    def _export_html(self) -> None:
        visible_results = self._visible_results()
        if not visible_results:
            return
        filename = filedialog.asksaveasfilename(
            parent=self,
            title="Exporter le rapport HTML",
            defaultextension=".html",
            filetypes=[("HTML", "*.html"), ("Tous les fichiers", "*.*")],
        )
        if not filename:
            return
        try:
            write_html_report(
                filename,
                self._report_rows(visible_results),
                title="Rapport SafeSweep",
                source_folder=self.folder_var.get(),
                scan_label=self._scan_mode_label(),
            )
        except OSError as exc:
            messagebox.showerror("Export HTML", f"Impossible d'écrire le rapport : {exc}", parent=self)
            return
        self.status_var.set(f"HTML exporté : {filename}")

    def _report_rows(self, results: list[FileCandidate] | None = None):
        selected_results = self.results if results is None else results
        return build_report_rows(
            selected_results,
            self.checked_paths,
            results_mode=self.results_mode,
            age_basis=self.results_age_basis,
        )

    def _scan_mode_label(self) -> str:
        if self.results_mode == "duplicates":
            return _("Doublons exacts")
        if self.results_mode == "folders":
            return _("Gros dossiers")
        if self.results_mode == "installers":
            return _("Installateurs oubliés")
        if self.results_mode == "uninstallers":
            return _("Désinstallateurs")
        return _("Fichiers inactifs")

    def _open_schedule_window(self) -> None:
        if not self._ensure_license_for_action(parent=self):
            return

        saved_config = self._load_schedule_config()
        frequency_var = tk.StringVar(
            value=_("Mensuelle") if saved_config and saved_config.frequency == "monthly" else _("Hebdomadaire")
        )
        time_var = tk.StringVar(value=saved_config.start_time if saved_config else "09:00")
        weekday_var = tk.StringVar(
            value=_(WEEKDAY_LABELS.get(saved_config.weekday, "Lundi")) if saved_config else _("Lundi")
        )
        month_day_var = tk.IntVar(value=saved_config.month_day if saved_config else 1)
        status_var = tk.StringVar(value=self._schedule_status_text(saved_config))
        summary_var = tk.StringVar(value="")

        window = tk.Toplevel(self)
        window.title("Planification")
        window.geometry("640x420")
        window.minsize(560, 360)
        window.transient(self)
        window.columnconfigure(0, weight=1)
        window.rowconfigure(2, weight=1)

        ttk.Label(window, textvariable=status_var, style="Status.TLabel", wraplength=600).grid(
            row=0, column=0, sticky="ew", padx=10, pady=(10, 6)
        )

        form = ttk.LabelFrame(window, text="Fréquence", padding=10)
        form.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 8))
        for index in range(6):
            form.columnconfigure(index, weight=0)
        form.columnconfigure(5, weight=1)

        ttk.Label(form, text="Rythme").grid(row=0, column=0, sticky="w")
        frequency_combo = ttk.Combobox(
            form,
            textvariable=frequency_var,
            values=translate_sequence(("Hebdomadaire", "Mensuelle")),
            state="readonly",
            width=16,
        )
        frequency_combo.grid(row=0, column=1, sticky="w", padx=(6, 18))

        ttk.Label(form, text="Heure").grid(row=0, column=2, sticky="w")
        ttk.Entry(form, textvariable=time_var, width=8).grid(row=0, column=3, sticky="w", padx=(6, 18))

        ttk.Label(form, text="Jour semaine").grid(row=1, column=0, sticky="w", pady=(8, 0))
        weekday_combo = ttk.Combobox(
            form,
            textvariable=weekday_var,
            values=translate_sequence(tuple(WEEKDAY_BY_LABEL)),
            state="readonly",
            width=16,
        )
        weekday_combo.grid(row=1, column=1, sticky="w", padx=(6, 18), pady=(8, 0))

        ttk.Label(form, text="Jour mois").grid(row=1, column=2, sticky="w", pady=(8, 0))
        ttk.Spinbox(form, from_=1, to=28, textvariable=month_day_var, width=6).grid(
            row=1, column=3, sticky="w", padx=(6, 18), pady=(8, 0)
        )

        summary = ttk.LabelFrame(window, text="Analyse planifiée", padding=10)
        summary.grid(row=2, column=0, sticky="nsew", padx=10, pady=(0, 8))
        summary.columnconfigure(0, weight=1)
        ttk.Label(summary, textvariable=summary_var, wraplength=590, justify=tk.LEFT).grid(row=0, column=0, sticky="nw")

        buttons = ttk.Frame(window, padding=(10, 0, 10, 10))
        buttons.grid(row=3, column=0, sticky="e")

        def refresh_summary(*_args: object) -> None:
            try:
                config = self._schedule_config_from_values(
                    frequency_var.get(),
                    weekday_var.get(),
                    month_day_var.get(),
                    time_var.get(),
                )
            except (SchedulerError, ValueError, tk.TclError) as exc:
                summary_var.set(f"Paramètres invalides : {exc}")
                return
            summary_var.set(self._schedule_summary(config))

        def save_schedule() -> None:
            try:
                config = self._schedule_config_from_values(
                    frequency_var.get(),
                    weekday_var.get(),
                    month_day_var.get(),
                    time_var.get(),
                )
                command, prefix_args = current_app_action()
                arguments = (*prefix_args, "--scheduled-scan", "--config", str(DEFAULT_CONFIG_PATH))
                create_scheduled_task(config, command, arguments)
            except (SchedulerError, ValueError, OSError, tk.TclError) as exc:
                messagebox.showerror("Planification", str(exc), parent=window)
                return

            status_var.set(self._schedule_status_text(config))
            summary_var.set(self._schedule_summary(config))
            self.status_var.set("Planification enregistrée. L'analyse planifiée ne supprimera rien automatiquement.")
            messagebox.showinfo("Planification", "Analyse planifiée enregistrée.", parent=window)

        def remove_schedule() -> None:
            if not messagebox.askyesno("Planification", "Supprimer la planification actuelle ?", parent=window):
                return
            try:
                delete_scheduled_task()
            except SchedulerError as exc:
                messagebox.showerror("Planification", str(exc), parent=window)
                return
            status_var.set(self._schedule_status_text(None))
            self.status_var.set("Planification supprimée.")

        def open_reports() -> None:
            DEFAULT_REPORT_DIR.mkdir(parents=True, exist_ok=True)
            os.startfile(DEFAULT_REPORT_DIR)  # type: ignore[attr-defined]

        ttk.Button(buttons, text="Ouvrir rapports", command=open_reports).pack(side=tk.LEFT)
        ttk.Button(buttons, text="Supprimer", command=remove_schedule).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(buttons, text="Enregistrer", command=save_schedule).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(buttons, text="Fermer", command=window.destroy).pack(side=tk.LEFT, padx=(8, 0))

        for variable in (frequency_var, time_var, weekday_var, month_day_var):
            variable.trace_add("write", refresh_summary)
        refresh_summary()

    def _load_schedule_config(self) -> ScheduledScanConfig | None:
        if not DEFAULT_CONFIG_PATH.exists():
            return None
        try:
            return load_config(DEFAULT_CONFIG_PATH)
        except SchedulerError:
            logger.exception("Planification illisible")
            return None

    def _schedule_config_from_values(
        self,
        frequency_label: str,
        weekday_label: str,
        month_day: int,
        start_time: str,
    ) -> ScheduledScanConfig:
        options = self._read_options()
        frequency = "monthly" if source_text(frequency_label) == "Mensuelle" else "weekly"
        weekday = WEEKDAY_BY_LABEL.get(str(source_text(weekday_label)))
        if not weekday:
            raise SchedulerError("Jour hebdomadaire invalide.")
        return ScheduledScanConfig(
            root=Path(options.root),
            scan_mode=self.scan_mode_var.get(),
            days_unused=options.days_unused,
            min_size_bytes=options.min_size_bytes,
            extension_filter=options.extension_filter,
            age_basis=options.age_basis,
            skip_hidden=options.skip_hidden,
            skip_system_locations=options.skip_system_locations,
            frequency=frequency,
            weekday=weekday,
            month_day=int(month_day),
            start_time=start_time.strip(),
            report_dir=DEFAULT_REPORT_DIR,
        )

    def _schedule_summary(self, config: ScheduledScanConfig) -> str:
        time_at = {"fr": "à", "en": "at", "es": "a las"}.get(current_language(), "à")
        if config.frequency == "monthly":
            frequency = f"{_('Mensuelle')}, {_('le')} {config.month_day} {time_at} {config.start_time}"
        else:
            frequency = (
                f"{_('Hebdomadaire')}, {_('le')} "
                f"{_(WEEKDAY_LABELS.get(config.weekday, config.weekday))} {time_at} {config.start_time}"
            )
        extensions = ", ".join(config.extension_filter) if config.extension_filter else _("toutes")
        return (
            f"{frequency}\n"
            f"{_('Analyse')} : {_(scan_mode_label(config.scan_mode))}\n"
            f"{_('Dossier')} : {config.root}\n"
            f"{_('Ancienneté')} : {config.days_unused} {_('jour(s)')}, "
            f"{_('taille min.')} : {format_bytes(config.min_size_bytes)}\n"
            f"{_('Extensions')} : {extensions}\n"
            f"{_('Rapports')} : {config.report_dir}\n"
            f"{_('Notification uniquement : aucune suppression, quarantaine ou Corbeille automatique.')}"
        )

    def _schedule_status_text(self, config: ScheduledScanConfig | None) -> str:
        try:
            info = query_scheduled_task()
        except (SchedulerError, OSError):
            logger.exception("Impossible de lire la tâche planifiée")
            info = None

        if info and info.exists:
            return _("Planification active dans le Planificateur de tâches Windows.")
        if config:
            return _("Configuration enregistrée, mais tâche Windows introuvable.")
        return _("Aucune planification active.")

    def _open_location(self) -> None:
        candidate = self._current_candidate()
        if not candidate:
            return
        self._open_candidate_location(candidate)

    def _preview_current(self) -> None:
        candidate = self._current_candidate()
        if candidate:
            self._preview_candidate(candidate)

    def _preview_context(self) -> None:
        candidate = self.item_to_result.get(self.tree.focus()) or self._current_candidate()
        if candidate:
            self._preview_candidate(candidate)

    def _preview_candidate(self, candidate: FileCandidate) -> None:
        path = candidate.path
        if self._is_uninstaller_candidate(candidate):
            self._open_text_preview("Aperçu désinstallateur", self._uninstaller_preview_text(candidate), candidate)
            return
        if path.is_dir() or candidate.item_type == "Dossier":
            self._open_text_preview("Aperçu dossier", self._folder_preview_text(candidate), candidate)
            return

        suffix = path.suffix.lower()
        if suffix == ".pdf":
            self._open_default_file(path, "PDF ouvert dans l'application par défaut.")
            return
        if suffix in IMAGE_PREVIEW_EXTENSIONS:
            self._open_image_preview(candidate)
            return
        if suffix in TEXT_PREVIEW_EXTENSIONS:
            self._open_file_text_preview(candidate)
            return

        self._open_text_preview(
            "Aperçu non disponible",
            (
                "Aperçu intégré non disponible pour ce type de fichier.\n\n"
                f"Fichier : {path.name}\n"
                f"Chemin : {path}\n"
                f"Taille : {format_bytes(candidate.size)}"
            ),
            candidate,
        )

    def _folder_preview_text(self, candidate: FileCandidate) -> str:
        return "\n".join(
            [
                f"Dossier : {candidate.path.name}",
                f"Chemin : {candidate.path}",
                f"Taille cumulée : {format_bytes(candidate.size)}",
                f"Fichiers inclus : {candidate.folder_file_count}",
                f"Sous-dossiers inclus : {candidate.folder_dir_count}",
                f"Indice : {candidate.folder_hint or 'Gros dossier'}",
                f"Dernière activité : {_format_datetime(candidate.last_activity_at)}",
                "",
                "Utilisez Ouvrir l'emplacement pour inspecter le dossier avant toute action.",
            ]
        )

    def _uninstaller_preview_text(self, candidate: FileCandidate) -> str:
        command = candidate.launch_command or (str(candidate.path),)
        return "\n".join(
            [
                f"Application détectée : {self._candidate_display_name(candidate)}",
                f"Dossier application : {candidate.path.parent}",
                f"Désinstallateur : {candidate.path}",
                f"Commande : {subprocess.list2cmdline(list(command))}",
                f"Source : {candidate.source_hint or 'Fichier'}",
                f"Taille du désinstallateur : {format_bytes(candidate.size)}",
                f"Dernière modification : {_format_datetime(candidate.modified_at)}",
                "",
                "Utilisez le clic droit puis Désinstaller pour lancer ce programme.",
            ]
        )

    def _open_file_text_preview(self, candidate: FileCandidate) -> None:
        path = candidate.path
        try:
            data = path.read_bytes()
        except OSError as exc:
            messagebox.showerror("Aperçu", f"Impossible de lire le fichier : {exc}", parent=self)
            return

        truncated = len(data) > MAX_TEXT_PREVIEW_BYTES
        preview_data = data[:MAX_TEXT_PREVIEW_BYTES]
        if b"\x00" in preview_data:
            self._open_text_preview(
                "Aperçu non disponible",
                f"Ce fichier semble binaire.\n\nChemin : {path}\nTaille : {format_bytes(candidate.size)}",
                candidate,
            )
            return

        text = self._decode_preview_text(preview_data)
        if truncated:
            text += f"\n\n--- Aperçu limité aux premiers {format_bytes(MAX_TEXT_PREVIEW_BYTES)} ---"
        self._open_text_preview(f"Aperçu texte - {path.name}", text, candidate)

    @staticmethod
    def _decode_preview_text(data: bytes) -> str:
        for encoding in ("utf-8-sig", "utf-16", "cp1252"):
            try:
                return data.decode(encoding)
            except UnicodeDecodeError:
                continue
        return data.decode("utf-8", errors="replace")

    def _open_text_preview(self, title: str, body: str, candidate: FileCandidate | None = None) -> None:
        window = tk.Toplevel(self)
        window.title(title)
        window.geometry("860x600")
        window.minsize(620, 420)
        window.transient(self)
        window.columnconfigure(0, weight=1)
        window.rowconfigure(0, weight=1)

        text = tk.Text(window, wrap=tk.WORD)
        text.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        scroll = ttk.Scrollbar(window, orient=tk.VERTICAL, command=text.yview)
        scroll.grid(row=0, column=1, sticky="ns", pady=8)
        text.configure(yscrollcommand=scroll.set)
        text.insert("1.0", body)
        text.configure(state=tk.DISABLED)

        buttons = ttk.Frame(window, padding=(8, 0, 8, 8))
        buttons.grid(row=1, column=0, columnspan=2, sticky="e")
        if candidate:
            ttk.Button(buttons, text="Ouvrir l'emplacement", command=lambda: self._open_candidate_location(candidate)).pack(
                side=tk.LEFT
            )
            if candidate.path.is_file():
                ttk.Button(buttons, text="Ouvrir le fichier", command=lambda: self._open_default_file(candidate.path)).pack(
                    side=tk.LEFT,
                    padx=(8, 0),
                )
        ttk.Button(buttons, text="Fermer", command=window.destroy).pack(side=tk.LEFT, padx=(8, 0))

    def _open_image_preview(self, candidate: FileCandidate) -> None:
        try:
            photo, details = self._load_preview_image(candidate.path)
        except Exception as exc:  # noqa: BLE001 - fallback to Windows default viewer
            logger.info("Aperçu image intégré indisponible pour %s: %s", candidate.path, exc)
            self._open_default_file(candidate.path, "Image ouverte dans l'application par défaut.")
            return

        window = tk.Toplevel(self)
        window.title(f"Aperçu image - {candidate.path.name}")
        window.geometry("960x760")
        window.minsize(520, 420)
        window.transient(self)
        window.columnconfigure(0, weight=1)
        window.rowconfigure(0, weight=1)
        window.preview_image = photo  # type: ignore[attr-defined]

        frame = ttk.Frame(window, padding=8)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        ttk.Label(frame, image=photo, anchor=tk.CENTER).grid(row=0, column=0, sticky="nsew")
        ttk.Label(
            frame,
            text=f"{candidate.path}\n{details} - {format_bytes(candidate.size)}",
            style="Status.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(8, 0))

        buttons = ttk.Frame(window, padding=(8, 0, 8, 8))
        buttons.grid(row=1, column=0, sticky="e")
        ttk.Button(buttons, text="Ouvrir l'emplacement", command=lambda: self._open_candidate_location(candidate)).pack(
            side=tk.LEFT
        )
        ttk.Button(buttons, text="Ouvrir le fichier", command=lambda: self._open_default_file(candidate.path)).pack(
            side=tk.LEFT,
            padx=(8, 0),
        )
        ttk.Button(buttons, text="Fermer", command=window.destroy).pack(side=tk.LEFT, padx=(8, 0))

    def _load_preview_image(self, path: Path) -> tuple[tk.PhotoImage, str]:
        try:
            from PIL import Image, ImageOps, ImageTk

            with Image.open(path) as image:
                original_size = image.size
                image = ImageOps.exif_transpose(image)
                image.thumbnail(MAX_IMAGE_PREVIEW_SIZE)
                photo = ImageTk.PhotoImage(image.copy())
                return photo, f"{original_size[0]} x {original_size[1]} px"
        except ImportError:
            photo = tk.PhotoImage(file=str(path))
            width = photo.width()
            height = photo.height()
            factor = max(1, width // MAX_IMAGE_PREVIEW_SIZE[0], height // MAX_IMAGE_PREVIEW_SIZE[1])
            if factor > 1:
                photo = photo.subsample(factor, factor)
            return photo, f"{width} x {height} px"

    def _open_default_file(self, path: Path, status_message: str | None = None) -> None:
        try:
            if os.name == "nt":
                os.startfile(path)  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except OSError as exc:
            messagebox.showerror("Ouvrir le fichier", str(exc), parent=self)
            return
        if status_message:
            self.status_var.set(status_message)

    def _uninstall_candidate(self, candidate: FileCandidate) -> None:
        if not self._ensure_license_for_action(parent=self):
            return

        if not self._is_uninstaller_candidate(candidate):
            messagebox.showinfo("Désinstaller", "Sélectionnez un résultat de type Désinstallateur.", parent=self)
            return
        command = candidate.launch_command or (str(candidate.path),)
        if not command:
            messagebox.showerror("Désinstaller", "Commande de désinstallation introuvable.", parent=self)
            return
        executable = Path(command[0])
        if executable.is_absolute() and not executable.exists():
            messagebox.showerror("Désinstaller", f"Fichier introuvable : {candidate.path}", parent=self)
            return

        app_name = self._candidate_display_name(candidate)
        tracking_key = self._uninstall_tracking_key(candidate)
        if tracking_key in self.pending_uninstall_keys:
            messagebox.showinfo(
                "Désinstaller",
                f"Vérification déjà en cours pour {app_name}.",
                parent=self,
            )
            return

        command_text = subprocess.list2cmdline(list(command))
        confirmed = messagebox.askyesno(
            "Lancer la désinstallation",
            f"Lancer le désinstallateur de {app_name} ?\n\n"
            f"Commande : {command_text}\n\n"
            "Une fenêtre de désinstallation ou une demande d'autorisation Windows peut s'ouvrir.",
            parent=self,
        )
        if not confirmed:
            return

        try:
            cwd = candidate.launch_cwd or (str(candidate.path.parent) if candidate.path.parent != Path(".") else None)
            process = subprocess.Popen(list(command), cwd=cwd)
        except OSError as exc:
            messagebox.showerror("Désinstaller", f"Impossible de lancer le désinstallateur : {exc}", parent=self)
            return

        self.pending_uninstall_keys.add(tracking_key)
        self._schedule_action_button_refresh()
        self.status_var.set(f"Désinstallateur lancé : {app_name}. Vérification après fermeture...")
        self._start_uninstall_verification(candidate, app_name, process)

    def _start_uninstall_verification(
        self,
        candidate: FileCandidate,
        app_name: str,
        process: subprocess.Popen,
    ) -> None:
        thread = threading.Thread(
            target=self._verify_uninstall_worker,
            args=(candidate, app_name, process),
            name="unused-file-uninstall-verify",
            daemon=True,
        )
        thread.start()

    def _verify_uninstall_worker(
        self,
        candidate: FileCandidate,
        app_name: str,
        process: subprocess.Popen,
    ) -> None:
        try:
            try:
                process.wait(timeout=900)
            except subprocess.TimeoutExpired:
                self.ui_queue.put(
                    ("uninstall_still_present", (candidate, app_name, "Le désinstallateur est encore ouvert."))
                )
                return

            for attempt in range(10):
                time.sleep(2 if attempt == 0 else 3)
                if not self._uninstaller_candidate_still_exists(candidate):
                    self.ui_queue.put(("uninstall_verified_removed", (candidate, app_name)))
                    return

            self.ui_queue.put(
                ("uninstall_still_present", (candidate, app_name, "Application encore détectée après vérification."))
            )
        except Exception as exc:  # noqa: BLE001 - surfaced to the user
            self.ui_queue.put(("uninstall_verify_error", (candidate, app_name, str(exc))))

    def _finish_uninstall_verified_removed(self, payload: tuple[FileCandidate, str]) -> None:
        candidate, app_name = payload
        self.pending_uninstall_keys.discard(self._uninstall_tracking_key(candidate))
        self._remove_single_result(candidate)
        self.status_var.set(f"{app_name} n'est plus détecté. Retiré de la liste.")

    def _finish_uninstall_still_present(self, payload: tuple[FileCandidate, str, str]) -> None:
        candidate, app_name, reason = payload
        self.pending_uninstall_keys.discard(self._uninstall_tracking_key(candidate))
        self._schedule_action_button_refresh()
        self.status_var.set(f"{app_name} est encore détecté. Il reste dans la liste. {reason}")

    def _finish_uninstall_verify_error(self, payload: tuple[FileCandidate, str, str]) -> None:
        candidate, app_name, message = payload
        self.pending_uninstall_keys.discard(self._uninstall_tracking_key(candidate))
        self._schedule_action_button_refresh()
        self.status_var.set(f"Vérification impossible pour {app_name}. Il reste dans la liste.")
        logger.warning("Vérification désinstallation impossible pour %s: %s", app_name, message)

    def _uninstaller_candidate_still_exists(self, candidate: FileCandidate) -> bool:
        return self._uninstaller_path_still_exists(candidate) or self._uninstaller_registry_entry_exists(candidate)

    @staticmethod
    def _uninstaller_path_still_exists(candidate: FileCandidate) -> bool:
        try:
            return candidate.path.is_absolute() and candidate.path.exists()
        except OSError:
            return True

    @staticmethod
    def _uninstaller_registry_entry_exists(candidate: FileCandidate) -> bool:
        if os.name != "nt":
            return False

        source_key = ""
        if candidate.source_hint.casefold().startswith("registre:"):
            source_key = candidate.source_hint.split(":", 1)[1].strip().casefold()
        display_name = candidate.display_name.strip().casefold()
        if not source_key and not display_name:
            return False

        try:
            import winreg
        except ImportError:
            return False

        registry_roots = (
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        )
        for hive, subkey in registry_roots:
            try:
                with winreg.OpenKey(hive, subkey) as uninstall_key:
                    count, _, _ = winreg.QueryInfoKey(uninstall_key)
                    for index in range(count):
                        try:
                            app_key_name = winreg.EnumKey(uninstall_key, index)
                            with winreg.OpenKey(uninstall_key, app_key_name) as app_key:
                                if source_key and app_key_name.casefold() == source_key:
                                    return True
                                if display_name:
                                    value, _kind = winreg.QueryValueEx(app_key, "DisplayName")
                                    if str(value).strip().casefold() == display_name:
                                        return True
                        except OSError:
                            continue
            except OSError:
                continue
        return False

    def _open_context_location(self) -> None:
        candidate = self.item_to_result.get(self.tree.focus()) or self._current_candidate()
        if candidate:
            self._open_candidate_location(candidate)

    def _open_candidate_location(self, candidate: FileCandidate) -> None:
        if not candidate.path.exists():
            if candidate.launch_cwd and Path(candidate.launch_cwd).exists():
                try:
                    subprocess.Popen(["explorer.exe", candidate.launch_cwd])
                except OSError as exc:
                    messagebox.showerror("Ouvrir l'emplacement", str(exc), parent=self)
                return
            messagebox.showinfo(
                "Ouvrir l'emplacement",
                "Aucun chemin de fichier local n'est disponible pour cette entrée.",
                parent=self,
            )
            return
        try:
            subprocess.Popen(["explorer.exe", "/select,", str(candidate.path)])
        except OSError:
            subprocess.Popen(["explorer.exe", str(candidate.path.parent)])

    def _copy_context_paths(self) -> None:
        candidates = self._context_candidates()
        if not candidates:
            return
        self.clipboard_clear()
        self.clipboard_append("\n".join(str(candidate.path) for candidate in candidates))
        self.status_var.set(
            "Chemin copié dans le presse-papiers."
            if len(candidates) == 1
            else f"{len(candidates)} chemins copiés dans le presse-papiers."
        )

    def _protect_context_parent(self) -> None:
        candidates = self._context_candidates()
        if not candidates:
            return
        folders = [candidate.path.parent for candidate in candidates]
        try:
            self.protection_list.add_paths(folders)
        except ProtectionError as exc:
            messagebox.showerror("Liste blanche", str(exc), parent=self)
            return
        self.status_var.set(f"{len(set(folders))} dossier(s) ajouté(s) à la liste blanche.")

    def _protect_context_extension(self) -> None:
        candidates = self._context_candidates()
        extensions = sorted({candidate.path.suffix.lower() for candidate in candidates if candidate.path.suffix})
        if not extensions:
            messagebox.showinfo("Liste blanche", "Aucune extension à protéger dans la sélection.", parent=self)
            return
        try:
            self.protection_list.add_extensions(extensions)
        except ProtectionError as exc:
            messagebox.showerror("Liste blanche", str(exc), parent=self)
            return
        self.status_var.set(f"Extension(s) protégée(s) : {', '.join(extensions)}")

    def _current_candidate(self) -> FileCandidate | None:
        selected = self.tree.selection()
        if selected:
            return self.item_to_result.get(selected[0])
        visible_results = self._visible_results()
        visible_checked_paths = self._visible_checked_paths()
        if visible_checked_paths:
            path = next(iter(visible_checked_paths))
            return next((item for item in visible_results if item.path == path), None)
        return visible_results[0] if visible_results else None

    def _selected_results(self) -> list[FileCandidate]:
        return [item for item in self._visible_results() if item.path in self.checked_paths]

    def _top_level_candidates(self, selected: list[FileCandidate]) -> list[FileCandidate]:
        top_level: list[FileCandidate] = []
        for candidate in sorted(selected, key=lambda item: len(item.path.parts)):
            if any(_same_or_child(candidate.path, parent.path) for parent in top_level):
                continue
            top_level.append(candidate)
        return top_level

    def _simulation_checked(self) -> None:
        self._show_action_report(
            self._selected_results(),
            "simulation seule",
            "Espace récupérable potentiel",
            empty_message="Cochez au moins un fichier.",
        )

    def _simulation_context(self) -> None:
        self._show_action_report(
            self._context_candidates(),
            "simulation seule",
            "Espace récupérable potentiel",
            empty_message="Sélectionnez au moins un fichier.",
        )

    def _confirm_action_report(self, selected: list[FileCandidate], action_label: str, space_label: str) -> bool:
        return self._show_action_report(
            selected,
            action_label,
            space_label,
            empty_message="Sélectionnez au moins un fichier.",
            require_confirmation=True,
        )

    def _show_action_report(
        self,
        selected: list[FileCandidate],
        action_label: str,
        space_label: str,
        empty_message: str,
        require_confirmation: bool = False,
    ) -> bool:
        if not selected:
            messagebox.showinfo("Aucune sélection", empty_message, parent=self)
            return False

        report = self._build_action_report(selected, action_label, space_label)
        title = "Simulation avant action" if require_confirmation else "Rapport de simulation"
        return self._open_report_window(title, report, require_confirmation=require_confirmation)

    def _build_action_report(self, selected: list[FileCandidate], action_label: str, space_label: str) -> str:
        effective = self._top_level_candidates(selected)
        total_size = sum(candidate.size for candidate in effective)
        type_counts = Counter(candidate.item_type for candidate in selected)
        folder_file_count = sum(candidate.folder_file_count for candidate in effective if candidate.item_type == "Dossier")
        folder_dir_count = sum(candidate.folder_dir_count for candidate in effective if candidate.item_type == "Dossier")
        risk_counts = Counter(self._candidate_risk(candidate).label for candidate in selected)
        recommendation_counts = Counter(self._candidate_recommendation(candidate).label for candidate in selected)
        folder_stats: dict[Path, list[int]] = defaultdict(lambda: [0, 0])

        for candidate in selected:
            stats = folder_stats[candidate.path.parent]
            stats[0] += 1
            stats[1] += candidate.size

        folders = sorted(folder_stats.items(), key=lambda item: (-item[1][1], str(item[0]).lower()))
        lines = [
            f"Action simulée : {action_label}",
            f"Éléments concernés : {len(selected)}",
            f"Éléments effectivement ciblés : {len(effective)}",
            f"Types : {', '.join(f'{label}: {count}' for label, count in sorted(type_counts.items()))}",
            f"{space_label} : {format_bytes(total_size)}",
        ]
        if folder_file_count or folder_dir_count:
            lines.append(f"Contenu de dossier inclus : {folder_file_count} fichier(s), {folder_dir_count} sous-dossier(s)")
        lines.extend(
            [
                "",
                "Risques :",
                *self._format_count_lines(risk_counts),
                "",
                "Recommandations :",
                *self._format_count_lines(recommendation_counts),
                "",
                "Dossiers concernés :",
            ]
        )

        for folder, (count, size) in folders[:12]:
            lines.append(f"- {folder} : {count} élément(s), {format_bytes(size)}")
        if len(folders) > 12:
            lines.append(f"- ... {len(folders) - 12} autre(s) dossier(s)")

        highest = self._highest_selected_risk(selected)
        lines.extend(
            [
                "",
                f"Risque maximal : {highest.label}",
                f"Raison principale : {highest.reason}",
            ]
        )
        return "\n".join(lines)

    @staticmethod
    def _format_count_lines(counts: Counter[str]) -> list[str]:
        if not counts:
            return ["- Aucun"]
        return [f"- {label} : {count}" for label, count in sorted(counts.items())]

    def _open_report_window(self, title: str, report: str, require_confirmation: bool = False) -> bool:
        result = tk.BooleanVar(value=not require_confirmation)
        window = tk.Toplevel(self)
        window.title(title)
        window.geometry("760x560")
        window.minsize(620, 420)
        window.transient(self)
        window.columnconfigure(0, weight=1)
        window.rowconfigure(0, weight=1)

        text = tk.Text(window, wrap=tk.WORD, height=24)
        text.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        scroll = ttk.Scrollbar(window, orient=tk.VERTICAL, command=text.yview)
        scroll.grid(row=0, column=1, sticky="ns", pady=8)
        text.configure(yscrollcommand=scroll.set)
        text.insert("1.0", report)
        text.configure(state=tk.DISABLED)

        buttons = ttk.Frame(window, padding=(8, 0, 8, 8))
        buttons.grid(row=1, column=0, columnspan=2, sticky="e")

        def close(value: bool) -> None:
            result.set(value)
            window.destroy()

        if require_confirmation:
            ttk.Button(buttons, text="Annuler", command=lambda: close(False)).pack(side=tk.LEFT)
            ttk.Button(buttons, text="Continuer", command=lambda: close(True)).pack(side=tk.LEFT, padx=(8, 0))
            window.protocol("WM_DELETE_WINDOW", lambda: close(False))
            window.grab_set()
            self.wait_window(window)
            return bool(result.get())

        ttk.Button(buttons, text="Fermer", command=lambda: close(True)).pack(side=tk.LEFT)
        return True

    def _has_full_duplicate_group_selected(self, selected: list[FileCandidate]) -> bool:
        if self.results_mode != "duplicates":
            return False

        selected_paths = {item.path for item in selected}
        return any(all(item.path in selected_paths for item in group) for group in self._duplicate_groups().values())

    def _highest_selected_risk(self, selected: list[FileCandidate]) -> RiskAssessment:
        risks = [self._candidate_risk(item) for item in selected]
        return max(risks, key=lambda risk: risk.score)

    def _selected_risk_counts(self, selected: list[FileCandidate]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in selected:
            label = self._candidate_risk(item).label
            counts[label] = counts.get(label, 0) + 1
        return counts

    def _confirm_risky_action(self, selected: list[FileCandidate], action_label: str) -> bool:
        highest = self._highest_selected_risk(selected)
        if highest.score < 2:
            return True

        counts = self._selected_risk_counts(selected)
        summary = ", ".join(f"{label}: {count}" for label, count in sorted(counts.items()))
        return messagebox.askyesno(
            "Risque élevé",
            f"La sélection contient des éléments à risque {highest.label}.\n\n"
            f"Détail : {summary}\n\n"
            f"Raison principale : {highest.reason}\n\n"
            f"Action demandée : {action_label}\n\n"
            "Pour ces éléments, vérifiez le rapport de simulation avant toute suppression. Continuer ?",
            parent=self,
        )

    def _remove_paths_from_results(self, paths: list[Path]) -> None:
        removed = set(paths)
        remaining = [
            item for item in self.results if item.path not in removed and not any(_same_or_child(item.path, path) for path in removed)
        ]
        if self.results_mode == "duplicates":
            groups: dict[int, list[FileCandidate]] = {}
            for candidate in remaining:
                if candidate.duplicate_group:
                    groups.setdefault(candidate.duplicate_group, []).append(candidate)
            remaining = [candidate for group in groups.values() if len(group) > 1 for candidate in group]

        self.results = remaining
        self.checked_paths -= removed
        self._apply_filters()

    def _remove_single_result(self, target: FileCandidate) -> None:
        self.results = [candidate for candidate in self.results if candidate != target]
        self.checked_paths.discard(target.path)
        self._apply_filters()

    def _quarantine_checked(self) -> None:
        self._quarantine_candidates(self._selected_results(), "Cochez au moins un fichier.")

    def _quarantine_context(self) -> None:
        self._quarantine_candidates(self._context_candidates(), "Sélectionnez au moins un fichier.")

    def _quarantine_candidates(
        self,
        selected: list[FileCandidate],
        empty_message: str,
        *,
        show_report: bool = True,
    ) -> None:
        if not self._ensure_license_for_action(parent=self):
            return

        if self.quarantine_thread and self.quarantine_thread.is_alive():
            return

        if not selected:
            messagebox.showinfo("Aucune sélection", empty_message, parent=self)
            return

        if any(self._is_uninstaller_candidate(item) for item in selected):
            messagebox.showinfo(
                "Quarantaine",
                "Les désinstallateurs détectés ne sont pas mis en quarantaine. Utilisez le clic droit puis Désinstaller.",
                parent=self,
            )
            return

        if self._has_full_duplicate_group_selected(selected):
            messagebox.showwarning(
                "Sélection risquée",
                "Au moins un groupe de doublons est entièrement coché. Gardez au moins une copie par groupe.",
                parent=self,
            )
            return

        if any(item.item_type == "Dossier" for item in selected):
            messagebox.showinfo(
                "Quarantaine",
                "La quarantaine est réservée aux fichiers. Pour un gros dossier, utilisez le rapport de simulation puis la Corbeille si nécessaire.",
                parent=self,
            )
            return

        if show_report:
            if not self._confirm_action_report(
                selected,
                "mise en quarantaine",
                "Espace déplacé en quarantaine",
            ):
                return

        if not self._confirm_risky_action(selected, "mise en quarantaine"):
            return

        total_size = sum(item.size for item in selected)
        confirmed = messagebox.askyesno(
            "Confirmer la quarantaine",
            f"Déplacer {len(selected)} fichier(s), {format_bytes(total_size)}, en quarantaine ?\n\n"
            "Les programmes ne les verront plus à leur emplacement d'origine, mais vous pourrez les restaurer.",
            parent=self,
        )
        if not confirmed:
            return

        paths = [item.path for item in selected]
        self.actions_menu_button.configure(state=tk.DISABLED)
        self._set_menu_entry_state(self.actions_menu, "Rapport de simulation...", False)
        self._set_menu_entry_state(self.actions_menu, "Mettre en quarantaine...", False)
        self._set_menu_entry_state(self.actions_menu, "Envoyer à la Corbeille...", False)
        self.status_var.set("Mise en quarantaine...")

        def worker() -> None:
            try:
                records = self.quarantine_manager.quarantine(paths)
                self.ui_queue.put(("quarantine_done", records))
            except QuarantineError as exc:
                self.ui_queue.put(("quarantine_error", str(exc)))
            except Exception as exc:  # noqa: BLE001 - surfaced to the user
                self.ui_queue.put(("quarantine_error", str(exc)))

        self.quarantine_thread = threading.Thread(target=worker, name="unused-file-quarantine", daemon=True)
        self.quarantine_thread.start()

    def _has_quarantine_recommendation(self, selected: list[FileCandidate]) -> bool:
        return any(self._candidate_recommendation(candidate).label == "Quarantaine" for candidate in selected)

    def _can_quarantine_selection(self, selected: list[FileCandidate]) -> bool:
        return bool(selected) and not any(item.item_type == "Dossier" for item in selected)

    def _ask_quarantine_before_delete(self, selected: list[FileCandidate]) -> str:
        total_size = sum(item.size for item in selected)
        quarantine_count = sum(
            1 for candidate in selected if self._candidate_recommendation(candidate).label == "Quarantaine"
        )
        result = tk.StringVar(value="cancel")
        window = tk.Toplevel(self)
        window.title("Quarantaine recommandée")
        window.geometry("520x210")
        window.minsize(460, 190)
        window.transient(self)
        window.resizable(False, False)
        window.columnconfigure(0, weight=1)

        content = ttk.Frame(window, padding=14)
        content.grid(row=0, column=0, sticky="nsew")
        content.columnconfigure(0, weight=1)

        ttk.Label(
            content,
            text="Mise en quarantaine conseillée",
            font=("Segoe UI", 11, "bold"),
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            content,
            text=(
                f"La sélection contient {quarantine_count} élément(s) recommandé(s) pour la quarantaine "
                f"sur {len(selected)} élément(s), {format_bytes(total_size)} au total.\n\n"
                "C'est l'option la plus prudente : le fichier est isolé, mais reste restaurable si besoin."
            ),
            wraplength=470,
            justify=tk.LEFT,
        ).grid(row=1, column=0, sticky="ew", pady=(8, 12))

        buttons = ttk.Frame(content)
        buttons.grid(row=2, column=0, sticky="e")

        def close(value: str) -> None:
            result.set(value)
            window.destroy()

        ttk.Button(buttons, text="Annuler", command=lambda: close("cancel")).pack(side=tk.LEFT)
        ttk.Button(buttons, text="Envoyer à la Corbeille", command=lambda: close("delete")).pack(
            side=tk.LEFT,
            padx=(8, 0),
        )
        ttk.Button(
            buttons,
            text="Mettre en quarantaine",
            command=lambda: close("quarantine"),
            style="Accent.TButton",
        ).pack(side=tk.LEFT, padx=(8, 0))

        window.protocol("WM_DELETE_WINDOW", lambda: close("cancel"))
        window.grab_set()
        self.wait_window(window)
        return result.get()

    def _finish_quarantine(self, records: list[QuarantineRecord]) -> None:
        paths = [record.original_path for record in records]
        self._remove_paths_from_results(paths)
        self.status_var.set(f"{len(records)} fichier(s) mis en quarantaine.")

    def _finish_quarantine_error(self, message: str) -> None:
        self.status_var.set("Mise en quarantaine interrompue.")
        messagebox.showerror("Erreur quarantaine", message, parent=self)
        self._update_action_state()

    def _prompt_expired_quarantine(self) -> None:
        try:
            settings = self.quarantine_manager.load_settings()
            if not settings.auto_prompt_enabled:
                return
            expired = self.quarantine_manager.expired_records(settings)
        except QuarantineError as exc:
            logger.warning("Impossible de vérifier les expirations de quarantaine: %s", exc)
            return

        if not expired:
            return

        total_size = sum(record.size for record in expired)
        confirmed = messagebox.askyesno(
            "Quarantaine expirée",
            f"{len(expired)} fichier(s), {format_bytes(total_size)}, sont en quarantaine depuis "
            f"au moins {settings.retention_days} jour(s).\n\n"
            "Les envoyer à la Corbeille maintenant ?",
            parent=self,
        )
        if not confirmed:
            self.status_var.set(f"{len(expired)} fichier(s) expiré(s) restent en quarantaine.")
            return

        try:
            recycled = self.quarantine_manager.send_to_recycle_bin([record.record_id for record in expired])
        except (QuarantineError, RecycleError) as exc:
            messagebox.showerror("Erreur Corbeille", str(exc), parent=self)
            return
        self.status_var.set(f"{len(recycled)} fichier(s) expiré(s) envoyé(s) à la Corbeille.")

    def _open_protection_window(self) -> None:
        window = tk.Toplevel(self)
        window.title("Liste blanche")
        window.geometry("900x500")
        window.minsize(700, 380)
        window.transient(self)
        window.columnconfigure(0, weight=1)
        window.rowconfigure(1, weight=1)

        header = ttk.Frame(window, padding=8)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(
            header,
            text=f"Ces règles sont ghostées pendant l'analyse : {self.protection_list.path}",
            style="Status.TLabel",
        ).grid(row=0, column=0, sticky="w")

        table_frame = ttk.Frame(window, padding=(8, 0, 8, 8))
        table_frame.grid(row=1, column=0, sticky="nsew")
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)

        columns = ("kind", "value")
        tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="extended")
        tree.heading("kind", text="Type")
        tree.heading("value", text="Règle")
        tree.column("kind", width=130, minwidth=110, stretch=False)
        tree.column("value", width=680, minwidth=320)

        y_scroll = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=tree.yview)
        x_scroll = ttk.Scrollbar(table_frame, orient=tk.HORIZONTAL, command=tree.xview)
        tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
        tree.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")

        footer = ttk.Frame(window, padding=(8, 0, 8, 8))
        footer.grid(row=2, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)
        protection_status = tk.StringVar(value="")
        ttk.Label(footer, textvariable=protection_status, style="Status.TLabel").grid(row=0, column=0, sticky="w")

        def load_rules() -> None:
            for item_id in tree.get_children():
                tree.delete(item_id)
            try:
                settings = self.protection_list.load()
            except ProtectionError as exc:
                messagebox.showerror("Liste blanche", str(exc), parent=window)
                return

            for path in settings.protected_paths:
                tree.insert("", tk.END, values=("Chemin", str(path)))
            for extension in settings.protected_extensions:
                tree.insert("", tk.END, values=("Extension", extension))
            protection_status.set(
                f"{len(settings.protected_paths)} chemin(s), {len(settings.protected_extensions)} extension(s) protégés."
            )

        def add_folder() -> None:
            folder = filedialog.askdirectory(parent=window, title="Ajouter un dossier à la liste blanche")
            if not folder:
                return
            try:
                self.protection_list.add_paths([folder])
            except ProtectionError as exc:
                messagebox.showerror("Liste blanche", str(exc), parent=window)
                return
            load_rules()

        def add_file() -> None:
            filename = filedialog.askopenfilename(parent=window, title="Ajouter un fichier à la liste blanche")
            if not filename:
                return
            try:
                self.protection_list.add_paths([filename])
            except ProtectionError as exc:
                messagebox.showerror("Liste blanche", str(exc), parent=window)
                return
            load_rules()

        def add_extension() -> None:
            raw = simpledialog.askstring(
                "Ajouter une extension",
                "Extension à protéger, par exemple .psd ou .blend :",
                parent=window,
            )
            if not raw:
                return
            extensions = normalize_protection_extensions(raw)
            if not extensions:
                return
            try:
                self.protection_list.add_extensions(extensions)
            except ProtectionError as exc:
                messagebox.showerror("Liste blanche", str(exc), parent=window)
                return
            load_rules()

        def remove_selected() -> None:
            selected = tree.selection()
            if not selected:
                messagebox.showinfo("Liste blanche", "Sélectionnez au moins une règle.", parent=window)
                return

            paths: list[str] = []
            extensions: list[str] = []
            for item_id in selected:
                kind, value = tree.item(item_id, "values")
                if kind == "Chemin":
                    paths.append(str(value))
                elif kind == "Extension":
                    extensions.append(str(value))

            try:
                if paths:
                    self.protection_list.remove_paths(paths)
                if extensions:
                    self.protection_list.remove_extensions(extensions)
            except ProtectionError as exc:
                messagebox.showerror("Liste blanche", str(exc), parent=window)
                return
            load_rules()

        buttons = ttk.Frame(footer)
        buttons.grid(row=0, column=1, sticky="e")
        ttk.Button(buttons, text="Ajouter dossier", command=add_folder).pack(side=tk.LEFT)
        ttk.Button(buttons, text="Ajouter fichier", command=add_file).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(buttons, text="Ajouter extension", command=add_extension).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(buttons, text="Retirer", command=remove_selected).pack(side=tk.LEFT, padx=(8, 0))

        load_rules()

    def _open_action_history_window(self) -> None:
        window = tk.Toplevel(self)
        window.title("Historique des actions")
        window.geometry("1100x560")
        window.minsize(760, 420)
        window.transient(self)
        window.columnconfigure(0, weight=1)
        window.rowconfigure(1, weight=1)

        header = ttk.Frame(window, padding=8)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(
            header,
            text=f"Historique local : {self.quarantine_manager.history_path}",
            style="Status.TLabel",
        ).grid(row=0, column=0, sticky="w")

        table_frame = ttk.Frame(window, padding=(8, 0, 8, 8))
        table_frame.grid(row=1, column=0, sticky="nsew")
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)

        columns = ("occurred_at", "action", "name", "size", "path", "details")
        tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="extended")
        tree.heading("occurred_at", text="Date")
        tree.heading("action", text="Action")
        tree.heading("name", text="Fichier")
        tree.heading("size", text="Taille")
        tree.heading("path", text="Chemin")
        tree.heading("details", text="Détails")
        tree.column("occurred_at", width=145, minwidth=130, stretch=False)
        tree.column("action", width=160, minwidth=130, stretch=False)
        tree.column("name", width=190, minwidth=140)
        tree.column("size", width=90, minwidth=80, anchor=tk.E, stretch=False)
        tree.column("path", width=380, minwidth=220)
        tree.column("details", width=320, minwidth=180)

        y_scroll = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=tree.yview)
        x_scroll = ttk.Scrollbar(table_frame, orient=tk.HORIZONTAL, command=tree.xview)
        tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
        tree.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")

        footer = ttk.Frame(window, padding=(8, 0, 8, 8))
        footer.grid(row=2, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)
        history_status = tk.StringVar(value="")
        ttk.Label(footer, textvariable=history_status, style="Status.TLabel").grid(row=0, column=0, sticky="w")

        def load_history() -> None:
            for item_id in tree.get_children():
                tree.delete(item_id)
            try:
                records = self.quarantine_manager.list_history()
            except QuarantineError as exc:
                messagebox.showerror("Historique", str(exc), parent=window)
                return

            for record in records:
                tree.insert(
                    "",
                    tk.END,
                    iid=record.event_id,
                    values=(
                        _format_datetime(record.occurred_at),
                        record.action,
                        record.path.name,
                        format_bytes(record.size),
                        str(record.path),
                        record.details,
                    ),
                )
            history_status.set(f"{len(records)} événement(s) enregistré(s).")

        buttons = ttk.Frame(footer)
        buttons.grid(row=0, column=1, sticky="e")
        ttk.Button(buttons, text="Actualiser", command=load_history).pack(side=tk.LEFT)
        ttk.Button(
            buttons,
            text="Ouvrir le dossier",
            command=lambda: subprocess.Popen(["explorer.exe", str(self.quarantine_manager.root)]),
        ).pack(side=tk.LEFT, padx=(8, 0))

        load_history()

    def _open_quarantine_window(self) -> None:
        window = tk.Toplevel(self)
        window.title("Quarantaine")
        window.geometry("1000x520")
        window.minsize(760, 420)
        window.transient(self)
        window.columnconfigure(0, weight=1)
        window.rowconfigure(1, weight=1)

        header = ttk.Frame(window, padding=8)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)

        try:
            current_settings = self.quarantine_manager.load_settings()
        except QuarantineError:
            current_settings = QuarantineSettings()
        retention_days_var = tk.IntVar(value=current_settings.retention_days)
        auto_prompt_var = tk.BooleanVar(value=current_settings.auto_prompt_enabled)

        ttk.Label(header, text=f"Dossier : {self.quarantine_manager.root}", style="Status.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Button(
            header,
            text="Ouvrir le dossier",
            command=lambda: subprocess.Popen(["explorer.exe", str(self.quarantine_manager.root)]),
        ).grid(row=0, column=1, padx=(8, 0))

        settings_frame = ttk.Frame(header)
        settings_frame.grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Label(settings_frame, text="Proposer la Corbeille après").pack(side=tk.LEFT)
        ttk.Spinbox(settings_frame, from_=1, to=3650, textvariable=retention_days_var, width=6).pack(
            side=tk.LEFT,
            padx=(6, 4),
        )
        ttk.Label(settings_frame, text="jours").pack(side=tk.LEFT, padx=(0, 12))
        ttk.Checkbutton(settings_frame, text="Demander au démarrage", variable=auto_prompt_var).pack(
            side=tk.LEFT,
            padx=(0, 12),
        )
        ttk.Button(settings_frame, text="Enregistrer délai", command=lambda: save_quarantine_settings()).pack(
            side=tk.LEFT
        )

        table_frame = ttk.Frame(window, padding=(8, 0, 8, 8))
        table_frame.grid(row=1, column=0, sticky="nsew")
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)

        columns = ("name", "size", "quarantined_at", "expires_at", "status", "original_path", "quarantined_path")
        tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="extended")
        tree.heading("name", text="Nom")
        tree.heading("size", text="Taille")
        tree.heading("quarantined_at", text="Mis en quarantaine")
        tree.heading("expires_at", text="Expire le")
        tree.heading("status", text="Statut")
        tree.heading("original_path", text="Chemin d'origine")
        tree.heading("quarantined_path", text="Chemin quarantaine")
        tree.column("name", width=180, minwidth=140)
        tree.column("size", width=90, minwidth=80, anchor=tk.E)
        tree.column("quarantined_at", width=150, minwidth=140)
        tree.column("expires_at", width=150, minwidth=140)
        tree.column("status", width=90, minwidth=80, anchor=tk.CENTER)
        tree.column("original_path", width=320, minwidth=220)
        tree.column("quarantined_path", width=320, minwidth=220)

        y_scroll = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=tree.yview)
        x_scroll = ttk.Scrollbar(table_frame, orient=tk.HORIZONTAL, command=tree.xview)
        tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
        tree.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        tree.tag_configure("expired", foreground="#9f1d1d")

        footer = ttk.Frame(window, padding=(8, 0, 8, 8))
        footer.grid(row=2, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)
        quarantine_status = tk.StringVar(value="")
        ttk.Label(footer, textvariable=quarantine_status, style="Status.TLabel").grid(row=0, column=0, sticky="w")

        records_by_id: dict[str, QuarantineRecord] = {}

        def save_quarantine_settings() -> None:
            try:
                settings = QuarantineSettings(
                    retention_days=max(1, int(retention_days_var.get())),
                    auto_prompt_enabled=auto_prompt_var.get(),
                )
                self.quarantine_manager.save_settings(settings)
            except (tk.TclError, ValueError, QuarantineError) as exc:
                messagebox.showerror("Quarantaine", f"Réglage invalide: {exc}", parent=window)
                return
            quarantine_status.set(f"Délai enregistré : {settings.retention_days} jour(s).")
            load_records()

        def load_records() -> None:
            nonlocal records_by_id
            for item_id in tree.get_children():
                tree.delete(item_id)
            try:
                settings = self.quarantine_manager.load_settings()
                records = self.quarantine_manager.list_records()
            except QuarantineError as exc:
                messagebox.showerror("Erreur quarantaine", str(exc), parent=window)
                return

            now = datetime.now().timestamp()
            records_by_id = {record.record_id: record for record in records}
            for record in records:
                expires_at = self.quarantine_manager.expires_at(record, settings)
                expired = expires_at <= now
                tree.insert(
                    "",
                    tk.END,
                    iid=record.record_id,
                    tags=("expired",) if expired else (),
                    values=(
                        record.original_path.name,
                        format_bytes(record.size),
                        _format_datetime(record.quarantined_at),
                        _format_datetime(expires_at),
                        "Expiré" if expired else "En attente",
                        str(record.original_path),
                        str(record.quarantined_path),
                    ),
                )
            expired_count = sum(1 for record in records if self.quarantine_manager.expires_at(record, settings) <= now)
            quarantine_status.set(f"{len(records)} fichier(s) en quarantaine, {expired_count} expiré(s).")

        def selected_ids() -> list[str]:
            return list(tree.selection())

        def open_original_parent() -> None:
            ids = selected_ids()
            if not ids:
                return
            record = records_by_id.get(ids[0])
            if record:
                subprocess.Popen(["explorer.exe", str(record.original_path.parent)])

        def restore_selected() -> None:
            ids = selected_ids()
            if not ids:
                messagebox.showinfo("Aucune sélection", "Sélectionnez au moins un fichier.", parent=window)
                return
            confirmed = messagebox.askyesno(
                "Restaurer",
                f"Restaurer {len(ids)} fichier(s) à leur emplacement d'origine ?",
                parent=window,
            )
            if not confirmed:
                return
            try:
                restored = self.quarantine_manager.restore(ids)
            except QuarantineError as exc:
                messagebox.showerror("Erreur restauration", str(exc), parent=window)
                return
            quarantine_status.set(f"{len(restored)} fichier(s) restauré(s).")
            load_records()

        def recycle_selected() -> None:
            ids = selected_ids()
            if not ids:
                messagebox.showinfo("Aucune sélection", "Sélectionnez au moins un fichier.", parent=window)
                return
            confirmed = messagebox.askyesno(
                "Envoyer à la Corbeille",
                f"Envoyer {len(ids)} fichier(s) de la quarantaine à la Corbeille ?",
                parent=window,
            )
            if not confirmed:
                return
            try:
                recycled = self.quarantine_manager.send_to_recycle_bin(ids)
            except (QuarantineError, RecycleError) as exc:
                messagebox.showerror("Erreur Corbeille", str(exc), parent=window)
                return
            quarantine_status.set(f"{len(recycled)} fichier(s) envoyé(s) à la Corbeille.")
            load_records()

        def recycle_expired() -> None:
            try:
                settings = self.quarantine_manager.load_settings()
                expired = self.quarantine_manager.expired_records(settings)
            except QuarantineError as exc:
                messagebox.showerror("Erreur quarantaine", str(exc), parent=window)
                return

            if not expired:
                messagebox.showinfo(
                    "Quarantaine",
                    f"Aucun fichier n'a dépassé le délai de {settings.retention_days} jour(s).",
                    parent=window,
                )
                return

            total_size = sum(record.size for record in expired)
            confirmed = messagebox.askyesno(
                "Corbeille des expirés",
                f"Envoyer {len(expired)} fichier(s), {format_bytes(total_size)}, à la Corbeille ?\n\n"
                f"Ils sont en quarantaine depuis au moins {settings.retention_days} jour(s).",
                parent=window,
            )
            if not confirmed:
                return

            try:
                recycled = self.quarantine_manager.send_to_recycle_bin([record.record_id for record in expired])
            except (QuarantineError, RecycleError) as exc:
                messagebox.showerror("Erreur Corbeille", str(exc), parent=window)
                return
            quarantine_status.set(f"{len(recycled)} fichier(s) expiré(s) envoyé(s) à la Corbeille.")
            load_records()

        buttons = ttk.Frame(footer)
        buttons.grid(row=0, column=1, sticky="e")
        ttk.Button(buttons, text="Actualiser", command=load_records).pack(side=tk.LEFT)
        ttk.Button(buttons, text="Ouvrir origine", command=open_original_parent).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(buttons, text="Restaurer", command=restore_selected).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(buttons, text="Corbeille expirés", command=recycle_expired, style="Danger.TButton").pack(
            side=tk.LEFT,
            padx=(8, 0),
        )
        ttk.Button(buttons, text="Envoyer à la Corbeille", command=recycle_selected, style="Danger.TButton").pack(
            side=tk.LEFT,
            padx=(8, 0),
        )
        ttk.Button(buttons, text="Historique", command=self._open_action_history_window).pack(side=tk.LEFT, padx=(8, 0))

        load_records()

    def _delete_checked(self) -> None:
        self._delete_candidates(self._selected_results(), "Cochez au moins un fichier.")

    def _delete_context(self) -> None:
        self._delete_candidates(self._context_candidates(), "Sélectionnez au moins un fichier.")

    def _delete_candidates(self, selected: list[FileCandidate], empty_message: str) -> None:
        if not self._ensure_license_for_action(parent=self):
            return

        if self.delete_thread and self.delete_thread.is_alive():
            return

        if not selected:
            messagebox.showinfo("Aucune sélection", empty_message, parent=self)
            return

        if any(self._is_uninstaller_candidate(item) for item in selected):
            messagebox.showinfo(
                "Corbeille",
                "Les désinstallateurs détectés ne doivent pas être supprimés directement. Utilisez le clic droit puis Désinstaller.",
                parent=self,
            )
            return

        if self._has_full_duplicate_group_selected(selected):
            messagebox.showwarning(
                "Sélection risquée",
                "Au moins un groupe de doublons est entièrement coché. Gardez au moins une copie par groupe.",
                parent=self,
            )
            return

        if not self._confirm_action_report(
            selected,
            "envoi à la Corbeille",
            "Espace libérable après vidage de la Corbeille",
        ):
            return

        if self._has_quarantine_recommendation(selected) and self._can_quarantine_selection(selected):
            choice = self._ask_quarantine_before_delete(selected)
            if choice == "cancel":
                return
            if choice == "quarantine":
                self._quarantine_candidates(
                    selected,
                    "Sélectionnez au moins un fichier.",
                    show_report=False,
                )
                return

        if not self._confirm_risky_action(selected, "envoi direct à la Corbeille"):
            return

        effective = self._top_level_candidates(selected)
        total_size = sum(item.size for item in effective)
        item_label = "élément" if len(effective) == 1 else "éléments"
        confirmed = messagebox.askyesno(
            "Confirmer l'envoi à la Corbeille",
            f"Envoyer {len(effective)} {item_label}, {format_bytes(total_size)}, à la Corbeille ?",
            parent=self,
        )
        if not confirmed:
            return

        paths = [item.path for item in effective]
        history_items = [(item.path, item.size) for item in effective]
        self.actions_menu_button.configure(state=tk.DISABLED)
        self._set_menu_entry_state(self.actions_menu, "Rapport de simulation...", False)
        self._set_menu_entry_state(self.actions_menu, "Envoyer à la Corbeille...", False)
        self.status_var.set("Envoi à la Corbeille...")
        self._schedule_action_button_refresh()

        def worker() -> None:
            try:
                move_to_recycle_bin(paths)
                try:
                    self.quarantine_manager.record_recycle_paths(history_items)
                except QuarantineError:
                    logger.exception("Impossible d'écrire l'historique Corbeille")
                self.ui_queue.put(("delete_done", paths))
            except RecycleError as exc:
                self.ui_queue.put(("delete_error", str(exc)))
            except Exception as exc:  # noqa: BLE001 - surfaced to the user
                self.ui_queue.put(("delete_error", str(exc)))

        self.delete_thread = threading.Thread(target=worker, name="unused-file-delete", daemon=True)
        self.delete_thread.start()

    def _finish_delete(self, paths: list[Path]) -> None:
        self._remove_paths_from_results(paths)
        self.status_var.set(f"{len(paths)} élément(s) envoyé(s) à la Corbeille.")

    def _finish_delete_error(self, message: str) -> None:
        self.status_var.set("Envoi à la Corbeille interrompu.")
        messagebox.showerror("Erreur Corbeille", message, parent=self)
        self._update_action_state()
        self._schedule_action_button_refresh()

    def _sort_tree(self, column: str, reverse: bool) -> None:
        items = list(self.tree.get_children(""))

        def key_for(item_id: str) -> object:
            candidate = self.item_to_result[item_id]
            if column == "checked":
                return candidate.path in self.checked_paths
            if column == "type":
                return candidate.item_type
            if column == "risk":
                risk = self._candidate_risk(candidate)
                return (risk.score, candidate.size, str(candidate.path).lower())
            if column == "recommendation":
                recommendation = self._candidate_recommendation(candidate)
                return (recommendation.rank, candidate.size, str(candidate.path).lower())
            if column == "group":
                return self._candidate_group_label(candidate)
            if column == "name":
                return self._candidate_display_name(candidate).lower()
            if column == "folder":
                return str(candidate.path.parent).lower()
            if column == "size":
                return candidate.size
            if column == "last_activity":
                return self._candidate_retained_at(candidate)
            if column == "accessed":
                return candidate.accessed_at
            if column == "modified":
                return candidate.modified_at
            return str(candidate.path).lower()

        for index, item_id in enumerate(sorted(items, key=key_for, reverse=reverse)):
            self.tree.move(item_id, "", index)
        self.tree.heading(column, command=lambda: self._sort_tree(column, not reverse))
        self._schedule_action_button_refresh()


def _format_datetime(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M")


def _same_or_child(path: Path, parent: Path) -> bool:
    try:
        path_resolved = path.resolve(strict=False)
        parent_resolved = parent.resolve(strict=False)
        return os.path.commonpath([os.fspath(path_resolved), os.fspath(parent_resolved)]) == os.fspath(parent_resolved)
    except (OSError, ValueError):
        return False


def _uninstaller_source_label(candidate: FileCandidate) -> str:
    source = candidate.source_hint.strip()
    if not source:
        return "Fichier"
    if source.casefold().startswith("registre"):
        return "Registre"
    return source


def _configure_logging() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=LOG_FILE,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        encoding="utf-8",
    )


def run_app() -> None:
    _configure_logging()
    app = UnusedFileFinderApp()
    app.mainloop()
