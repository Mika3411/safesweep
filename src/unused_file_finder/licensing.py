from __future__ import annotations

import base64
import ctypes
import json
import os
import platform as platform_module
import re
import socket
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Callable, Mapping
from urllib import error, request

from . import __version__

APP_DATA_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "NettoyeurFichiers"
LICENSE_STATE_PATH = APP_DATA_DIR / "license.json"
DEFAULT_LICENSE_API_BASE_URL = os.environ.get("SAFESWEEP_LICENSE_API_URL", "http://localhost:3000")
LICENSE_API_URL_ENV = "SAFESWEEP_LICENSE_API_URL"
USER_AGENT = f"SafeSweep/{__version__}"
LICENSE_KEY_PROTECTED_FIELD = "license_key_protected"
TEMPORARY_STATUS_CODES = frozenset({408, 425, 429, 500, 502, 503, 504})


class LicenseError(RuntimeError):
    pass


class LicenseNetworkError(LicenseError):
    pass


@dataclass(frozen=True)
class LicenseApiResponse:
    status_code: int
    payload: dict[str, object]


@dataclass(frozen=True)
class LicenseState:
    device_id: str
    license_key: str = ""
    device_name: str = ""
    platform: str = ""
    status: str = "missing"
    valid: bool = False
    activated: bool = False
    expires_at: str | None = None
    remaining_activations: int | None = None
    device_authorized: bool = False
    requires_activation: bool = False
    server_url: str = DEFAULT_LICENSE_API_BASE_URL
    last_checked_at: str | None = None
    last_error: str | None = None

    @classmethod
    def from_mapping(cls, payload: Mapping[str, object]) -> "LicenseState":
        license_key, license_error = _license_key_from_mapping(payload)
        last_error = _optional_string(payload.get("last_error") or payload.get("lastError"))
        if license_error:
            last_error = license_error

        return cls(
            device_id=str(payload.get("device_id") or payload.get("deviceId") or ""),
            license_key=license_key,
            device_name=str(payload.get("device_name") or payload.get("deviceName") or ""),
            platform=str(payload.get("platform") or ""),
            status=str(payload.get("status") or "missing").casefold(),
            valid=bool(payload.get("valid")),
            activated=bool(payload.get("activated")),
            expires_at=_optional_string(payload.get("expires_at") or payload.get("expiresAt")),
            remaining_activations=_optional_int(
                payload.get("remaining_activations") or payload.get("remainingActivations")
            ),
            device_authorized=bool(payload.get("device_authorized") or payload.get("deviceAuthorized")),
            requires_activation=bool(payload.get("requires_activation") or payload.get("requiresActivation")),
            server_url=str(payload.get("server_url") or payload.get("serverUrl") or DEFAULT_LICENSE_API_BASE_URL),
            last_checked_at=_optional_string(payload.get("last_checked_at") or payload.get("lastCheckedAt")),
            last_error=last_error,
        )

    def to_json_payload(self) -> dict[str, object]:
        payload = asdict(self)
        license_key = str(payload.pop("license_key", "") or "")
        if license_key:
            payload[LICENSE_KEY_PROTECTED_FIELD] = protect_secret(license_key)
        return payload


@dataclass(frozen=True)
class LicenseStatus:
    can_use: bool
    valid: bool
    status: str
    reason: str
    source: str
    expires_at: str | None = None
    remaining_activations: int | None = None
    device_id: str = ""
    device_name: str = ""
    platform: str = ""
    masked_license_key: str = ""
    requires_activation: bool = False
    device_authorized: bool = False
    activated: bool = False
    server_url: str = DEFAULT_LICENSE_API_BASE_URL

    @property
    def is_blocking(self) -> bool:
        return not self.can_use


Transport = Callable[[str, Mapping[str, object], float], LicenseApiResponse]


class LicenseClient:
    def __init__(
        self,
        base_url: str | None = None,
        *,
        timeout: float = 8.0,
        transport: Transport | None = None,
    ) -> None:
        self.base_url = normalize_base_url(base_url or os.environ.get(LICENSE_API_URL_ENV) or DEFAULT_LICENSE_API_BASE_URL)
        self.timeout = timeout
        self._transport = transport or post_json

    def validate(self, payload: Mapping[str, object]) -> LicenseApiResponse:
        return self._post("/api/license/validate", payload)

    def activate(self, payload: Mapping[str, object]) -> LicenseApiResponse:
        return self._post("/api/license/activate", payload)

    def deactivate(self, payload: Mapping[str, object]) -> LicenseApiResponse:
        return self._post("/api/license/deactivate", payload)

    def _post(self, path: str, payload: Mapping[str, object]) -> LicenseApiResponse:
        return self._transport(f"{self.base_url}{path}", payload, self.timeout)


class LicenseManager:
    def __init__(
        self,
        *,
        state_path: str | Path = LICENSE_STATE_PATH,
        client: LicenseClient | None = None,
        api_base_url: str | None = None,
    ) -> None:
        self.state_path = Path(state_path)
        explicit_url = bool(api_base_url or os.environ.get(LICENSE_API_URL_ENV))
        self._explicit_api_base_url = explicit_url or client is not None
        self.client = client or LicenseClient(api_base_url)

    def load_state(self) -> LicenseState:
        try:
            raw = json.loads(self.state_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return self._new_state()
        except (OSError, json.JSONDecodeError):
            return self._new_state(last_error="Etat de licence local illisible.")

        state = LicenseState.from_mapping(raw if isinstance(raw, dict) else {})
        if state.server_url and not self._explicit_api_base_url:
            self.client.base_url = normalize_base_url(state.server_url)
        return self._complete_state(state)

    def save_state(self, state: LicenseState) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.state_path.with_suffix(".tmp")
        temp_path.write_text(json.dumps(state.to_json_payload(), ensure_ascii=False, indent=2), encoding="utf-8")
        temp_path.replace(self.state_path)

    def ensure_state(self) -> LicenseState:
        state = self.load_state()
        self.save_state(state)
        return state

    def local_status(self) -> LicenseStatus:
        return self._status_from_state(self.ensure_state(), source="local")

    def validate_saved_license(self) -> LicenseStatus:
        state = self.ensure_state()
        if not state.license_key:
            return self._status_from_state(state, source="local", reason="Aucune licence activee.")

        try:
            response = self.client.validate(self._request_payload(state.license_key, state))
        except LicenseNetworkError as exc:
            return self._temporary_status(state, str(exc), source="network")

        if is_temporary_response(response):
            return self._temporary_status(state, temporary_response_reason(response), source="server")

        return self._apply_response(state, response, action="validate")

    def activate(self, license_key: str) -> LicenseStatus:
        state = self.ensure_state()
        normalized_key = normalize_license_key(license_key)
        if not normalized_key:
            return self._status_from_state(state, source="local", reason="Saisissez une cle de licence.")

        try:
            response = self.client.activate(self._request_payload(normalized_key, state))
        except LicenseNetworkError as exc:
            return self._temporary_status(state, str(exc), source="network")

        if is_temporary_response(response):
            return self._temporary_status(state, temporary_response_reason(response), source="server")

        return self._apply_response(state, response, action="activate", license_key=normalized_key)

    def deactivate(self) -> LicenseStatus:
        state = self.ensure_state()
        if not state.license_key:
            return self._status_from_state(state, source="local", reason="Aucune licence a desactiver.")

        try:
            response = self.client.deactivate(self._request_payload(state.license_key, state))
        except LicenseNetworkError as exc:
            return self._temporary_status(state, str(exc), source="network")

        if is_temporary_response(response):
            return self._temporary_status(state, temporary_response_reason(response), source="server")

        return self._apply_response(state, response, action="deactivate")

    def require_valid_license(self) -> LicenseStatus:
        status = self.validate_saved_license()
        if status.can_use:
            return status
        raise LicenseError(status.reason)

    def _new_state(self, *, last_error: str | None = None) -> LicenseState:
        return LicenseState(
            device_id=new_device_id(),
            device_name=device_name(),
            platform=platform_label(),
            server_url=self.client.base_url,
            last_error=last_error,
        )

    def _complete_state(self, state: LicenseState) -> LicenseState:
        return self._replace_state(
            state,
            device_id=state.device_id or new_device_id(),
            device_name=state.device_name or device_name(),
            platform=state.platform or platform_label(),
            server_url=self.client.base_url,
        )

    def _request_payload(self, license_key: str, state: LicenseState) -> dict[str, object]:
        return {
            "licenseKey": normalize_license_key(license_key),
            "deviceId": state.device_id,
            "deviceName": state.device_name or device_name(),
            "platform": state.platform or platform_label(),
        }

    def _apply_response(
        self,
        state: LicenseState,
        response: LicenseApiResponse,
        *,
        action: str,
        license_key: str | None = None,
    ) -> LicenseStatus:
        payload = response.payload
        normalized_key = normalize_license_key(license_key or state.license_key)
        valid = bool(payload.get("valid"))
        status = str(payload.get("status") or ("active" if valid else "invalid")).casefold()
        expires_at = _optional_string(payload.get("expiresAt") or payload.get("expires_at"))
        remaining = _optional_int(payload.get("remainingActivations") or payload.get("remaining_activations"))
        reason = str(payload.get("reason") or payload.get("error") or "")
        device_authorized = bool(payload.get("deviceAuthorized") or payload.get("device_authorized"))
        requires_activation = bool(payload.get("requiresActivation") or payload.get("requires_activation"))
        activated = (
            bool(payload.get("activated"))
            or (action == "validate" and device_authorized and not requires_activation)
            or (state.activated and valid and not requires_activation and action != "deactivate")
        )

        if action == "deactivate" and bool(payload.get("deactivated")):
            valid = False
            activated = False
            device_authorized = False
            requires_activation = True
            reason = "Licence desactivee sur cet appareil."

        if not reason:
            reason = reason_for_status(
                status,
                valid=valid,
                activated=activated,
                requires_activation=requires_activation,
                expires_at=expires_at,
                status_code=response.status_code,
            )

        updated = self._replace_state(
            state,
            license_key=normalized_key,
            status=status,
            valid=valid,
            activated=activated,
            expires_at=expires_at,
            remaining_activations=remaining,
            device_authorized=device_authorized,
            requires_activation=requires_activation,
            server_url=self.client.base_url,
            last_checked_at=utc_now_iso(),
            last_error=None if valid and activated else reason,
        )
        self.save_state(updated)
        return self._status_from_state(updated, source="server", reason=reason)

    def _status_from_state(
        self,
        state: LicenseState,
        *,
        source: str,
        reason: str | None = None,
    ) -> LicenseStatus:
        expired = is_expired(state.expires_at)
        valid = state.valid and not expired
        can_use = (
            bool(state.license_key)
            and valid
            and state.status == "active"
            and state.activated
            and not state.requires_activation
        )
        status = "expired" if expired else state.status
        message = reason or reason_for_status(
            status,
            valid=valid,
            activated=state.activated,
            requires_activation=state.requires_activation,
            expires_at=state.expires_at,
        )
        return LicenseStatus(
            can_use=can_use,
            valid=valid,
            status=status,
            reason=message,
            source=source,
            expires_at=state.expires_at,
            remaining_activations=state.remaining_activations,
            device_id=state.device_id,
            device_name=state.device_name,
            platform=state.platform,
            masked_license_key=mask_license_key(state.license_key),
            requires_activation=state.requires_activation,
            device_authorized=state.device_authorized,
            activated=state.activated,
            server_url=state.server_url,
        )

    def _temporary_status(self, state: LicenseState, reason: str, *, source: str) -> LicenseStatus:
        cached = self._status_from_state(state, source="local")
        if cached.can_use:
            return LicenseStatus(
                **{
                    **asdict(cached),
                    "source": source,
                    "reason": "Validation serveur temporairement indisponible. Licence locale utilisee.",
                }
            )

        updated = self._replace_state(state, status="network_error", last_error=reason, server_url=self.client.base_url)
        self.save_state(updated)
        return self._status_from_state(updated, source=source, reason=reason)

    @staticmethod
    def _replace_state(state: LicenseState, **updates: object) -> LicenseState:
        payload = asdict(state)
        payload.update(updates)
        return LicenseState.from_mapping(payload)


def post_json(url: str, payload: Mapping[str, object], timeout: float) -> LicenseApiResponse:
    data = json.dumps(payload).encode("utf-8")
    http_request = request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
    )

    try:
        with request.urlopen(http_request, timeout=timeout) as response:  # noqa: S310 - URL is user/deployment config.
            return LicenseApiResponse(response.status, _decode_response(response.read()))
    except error.HTTPError as exc:
        return LicenseApiResponse(exc.code, _decode_response(exc.read()))
    except (OSError, TimeoutError, ValueError) as exc:
        raise LicenseNetworkError(f"Serveur de licence indisponible : {exc}") from exc


def is_temporary_response(response: LicenseApiResponse) -> bool:
    return response.status_code in TEMPORARY_STATUS_CODES


def temporary_response_reason(response: LicenseApiResponse) -> str:
    reason = str(response.payload.get("reason") or response.payload.get("error") or "").strip()
    if reason:
        return reason
    if response.status_code == 429:
        return "Trop de tentatives. Reessayez plus tard."
    return "Serveur de licence temporairement indisponible."


def protect_secret(value: str) -> str:
    if not value:
        return ""
    if os.name == "nt":
        try:
            return "dpapi:" + base64.b64encode(_dpapi_protect(value.encode("utf-8"))).decode("ascii")
        except OSError:
            pass
    return "portable:" + base64.b64encode(value.encode("utf-8")).decode("ascii")


def unprotect_secret(value: str) -> str:
    if not value:
        return ""
    if value.startswith("dpapi:"):
        if os.name != "nt":
            raise LicenseError("Cle de licence locale protegee par Windows DPAPI illisible sur ce systeme.")
        encrypted = base64.b64decode(value.removeprefix("dpapi:"))
        return _dpapi_unprotect(encrypted).decode("utf-8")
    if value.startswith("portable:"):
        return base64.b64decode(value.removeprefix("portable:")).decode("utf-8")
    return value


def _license_key_from_mapping(payload: Mapping[str, object]) -> tuple[str, str | None]:
    raw = str(payload.get("license_key") or payload.get("licenseKey") or "")
    if raw:
        return normalize_license_key(raw), None

    protected = _optional_string(payload.get(LICENSE_KEY_PROTECTED_FIELD) or payload.get("licenseKeyProtected"))
    if not protected:
        return "", None

    try:
        return normalize_license_key(unprotect_secret(protected)), None
    except (LicenseError, OSError, ValueError) as exc:
        return "", f"Cle de licence locale illisible : {exc}"


class _DataBlob(ctypes.Structure):
    _fields_ = (
        ("cbData", ctypes.c_ulong),
        ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
    )


def _dpapi_protect(data: bytes) -> bytes:
    buffer = ctypes.create_string_buffer(data)
    data_in = _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    data_out = _DataBlob()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32

    if not crypt32.CryptProtectData(
        ctypes.byref(data_in),
        None,
        None,
        None,
        None,
        0,
        ctypes.byref(data_out),
    ):
        raise ctypes.WinError()

    try:
        return ctypes.string_at(data_out.pbData, data_out.cbData)
    finally:
        kernel32.LocalFree(data_out.pbData)


def _dpapi_unprotect(data: bytes) -> bytes:
    buffer = ctypes.create_string_buffer(data)
    data_in = _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    data_out = _DataBlob()
    description = ctypes.c_wchar_p()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32

    if not crypt32.CryptUnprotectData(
        ctypes.byref(data_in),
        ctypes.byref(description),
        None,
        None,
        None,
        0,
        ctypes.byref(data_out),
    ):
        raise ctypes.WinError()

    try:
        return ctypes.string_at(data_out.pbData, data_out.cbData)
    finally:
        kernel32.LocalFree(data_out.pbData)
        if description:
            kernel32.LocalFree(description)


def normalize_base_url(value: str) -> str:
    cleaned = value.strip().rstrip("/")
    return cleaned or DEFAULT_LICENSE_API_BASE_URL


def normalize_license_key(value: str) -> str:
    raw = value.strip().upper()
    compact = re.sub(r"[^A-Z0-9]", "", raw)
    if len(compact) == 16:
        return "-".join(compact[index : index + 4] for index in range(0, 16, 4))
    return re.sub(r"\s+", "", raw)


def mask_license_key(value: str) -> str:
    normalized = normalize_license_key(value)
    compact = normalized.replace("-", "")
    if len(compact) < 8:
        return ""
    return f"{compact[:4]}-****-****-{compact[-4:]}"


def new_device_id() -> str:
    return f"safesweep-{uuid.uuid4().hex}"


def device_name() -> str:
    hostname = socket.gethostname().strip()
    return hostname[:120] if len(hostname) >= 2 else "PC Windows"


def platform_label() -> str:
    parts = [platform_module.system() or "Windows", platform_module.release(), platform_module.machine()]
    return " ".join(part for part in parts if part).strip()[:80]


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def is_expired(expires_at: str | None, *, today: date | None = None) -> bool:
    if not expires_at:
        return False
    try:
        expires = date.fromisoformat(expires_at[:10])
    except ValueError:
        return False
    return expires < (today or date.today())


def reason_for_status(
    status: str,
    *,
    valid: bool,
    activated: bool,
    requires_activation: bool,
    expires_at: str | None,
    status_code: int | None = None,
) -> str:
    normalized = status.casefold()
    if status_code == 401:
        return "Client logiciel non autorise par le serveur de licences."
    if normalized == "missing":
        return "Aucune licence activee."
    if normalized == "expired" or is_expired(expires_at):
        return "Licence expiree."
    if normalized == "revoked":
        return "Licence revoquee."
    if normalized == "suspended":
        return "Licence suspendue."
    if normalized in {"not_found", "invalid"}:
        return "Licence introuvable ou invalide."
    if requires_activation or (valid and not activated):
        return "Activation requise sur cet appareil."
    if not valid:
        return "Licence non valide."
    return "Licence active."


def _decode_response(data: bytes) -> dict[str, object]:
    if not data:
        return {}
    try:
        decoded = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {"error": data.decode("utf-8", errors="replace")}
    return decoded if isinstance(decoded, dict) else {"response": decoded}


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
