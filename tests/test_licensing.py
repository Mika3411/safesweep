from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Mapping

import pytest

from unused_file_finder.cli import run_cli
from unused_file_finder.licensing import (
    LICENSE_KEY_PROTECTED_FIELD,
    LicenseApiResponse,
    LicenseClient,
    LicenseError,
    LicenseManager,
    LicenseNetworkError,
    LicenseStatus,
    is_expired,
    mask_license_key,
    normalize_license_key,
)
from unused_file_finder.scheduler import SchedulerError, run_scheduled_scan


def test_license_key_helpers_normalize_and_mask() -> None:
    assert normalize_license_key("abcd efgh-ijkl/mnop") == "ABCD-EFGH-IJKL-MNOP"
    assert mask_license_key("ABCD-EFGH-IJKL-MNOP") == "ABCD-****-****-MNOP"
    assert is_expired("2026-01-01", today=date(2026, 1, 2)) is True


def test_license_manager_generates_stable_local_device_id(tmp_path: Path) -> None:
    state_path = tmp_path / "license.json"
    first = LicenseManager(state_path=state_path, client=_client_with_response({})).local_status()
    second = LicenseManager(state_path=state_path, client=_client_with_response({})).local_status()

    assert first.device_id == second.device_id
    assert first.device_id.startswith("safesweep-")
    assert state_path.exists()


def test_activate_license_calls_api_and_persists_state(tmp_path: Path) -> None:
    calls: list[tuple[str, Mapping[str, object]]] = []

    def transport(url: str, payload: Mapping[str, object], _timeout: float) -> LicenseApiResponse:
        calls.append((url, dict(payload)))
        return LicenseApiResponse(
            200,
            {
                "valid": True,
                "activated": True,
                "status": "active",
                "expiresAt": "2027-06-25",
                "remainingActivations": 2,
            },
        )

    state_path = tmp_path / "license.json"
    manager = LicenseManager(
        state_path=state_path,
        client=LicenseClient("https://licenses.example", transport=transport),
    )

    status = manager.activate("abcd efgh ijkl mnop")

    assert status.can_use is True
    assert calls[0][0] == "https://licenses.example/api/license/activate"
    assert calls[0][1]["licenseKey"] == "ABCD-EFGH-IJKL-MNOP"
    assert set(calls[0][1]) == {"licenseKey", "deviceId", "deviceName", "platform"}
    stored = json.loads(state_path.read_text(encoding="utf-8"))
    assert "license_key" not in stored
    assert stored[LICENSE_KEY_PROTECTED_FIELD] != "ABCD-EFGH-IJKL-MNOP"
    assert stored["activated"] is True
    assert LicenseManager(state_path=state_path, client=_client_with_response({})).local_status().can_use is True


def test_explicit_server_url_overrides_saved_server_url(tmp_path: Path) -> None:
    state_path = tmp_path / "license.json"
    first = LicenseManager(state_path=state_path, client=_client_with_response({}))
    first.save_state(
        first._replace_state(
            first.ensure_state(),
            license_key="ABCD-EFGH-IJKL-MNOP",
            server_url="https://old.example",
        )
    )
    calls: list[str] = []

    def transport(url: str, _payload: Mapping[str, object], _timeout: float) -> LicenseApiResponse:
        calls.append(url)
        return LicenseApiResponse(
            200,
            {
                "valid": True,
                "activated": True,
                "status": "active",
                "expiresAt": "2027-06-25",
            },
        )

    manager = LicenseManager(
        state_path=state_path,
        client=LicenseClient("https://new.example", transport=transport),
    )

    status = manager.validate_saved_license()

    assert status.can_use is True
    assert calls == ["https://new.example/api/license/validate"]


def test_server_denial_blocks_license(tmp_path: Path) -> None:
    manager = LicenseManager(
        state_path=tmp_path / "license.json",
        client=_client_with_response(
            {
                "valid": False,
                "status": "revoked",
                "reason": "Licence revoquee.",
                "expiresAt": "2027-06-25",
                "remainingActivations": 0,
            },
            status_code=403,
        ),
    )

    status = manager.activate("ABCD-EFGH-IJKL-MNOP")

    assert status.can_use is False
    assert status.status == "revoked"
    assert "revoquee" in status.reason


def test_cached_license_is_used_when_server_is_temporarily_unreachable(tmp_path: Path) -> None:
    state_path = tmp_path / "license.json"
    activated = LicenseManager(
        state_path=state_path,
        client=_client_with_response(
            {
                "valid": True,
                "activated": True,
                "status": "active",
                "expiresAt": "2027-06-25",
                "remainingActivations": 1,
            }
        ),
    )
    assert activated.activate("ABCD-EFGH-IJKL-MNOP").can_use is True

    def down(_url: str, _payload: Mapping[str, object], _timeout: float) -> LicenseApiResponse:
        raise LicenseNetworkError("Serveur indisponible")

    offline = LicenseManager(
        state_path=state_path,
        client=LicenseClient("https://licenses.example", transport=down),
    )

    status = offline.validate_saved_license()

    assert status.can_use is True
    assert "locale" in status.reason


def test_temporary_server_response_keeps_cached_license_valid(tmp_path: Path) -> None:
    state_path = tmp_path / "license.json"
    activated = LicenseManager(
        state_path=state_path,
        client=_client_with_response(
            {
                "valid": True,
                "activated": True,
                "status": "active",
                "expiresAt": "2027-06-25",
                "remainingActivations": 1,
            }
        ),
    )
    assert activated.activate("ABCD-EFGH-IJKL-MNOP").can_use is True

    limited = LicenseManager(
        state_path=state_path,
        client=_client_with_response({"error": "Trop de validations."}, status_code=429),
    )

    status = limited.validate_saved_license()
    reloaded = LicenseManager(state_path=state_path, client=_client_with_response({})).local_status()

    assert status.can_use is True
    assert reloaded.can_use is True


def test_cli_license_activate_does_not_print_raw_key(monkeypatch, capsys) -> None:
    class FakeManager:
        def activate(self, license_key: str) -> LicenseStatus:
            assert license_key == "ABCD-EFGH-IJKL-MNOP"
            return LicenseStatus(
                can_use=True,
                valid=True,
                status="active",
                reason="Licence active.",
                source="server",
                masked_license_key="ABCD-****-****-MNOP",
                device_id="safesweep-device",
                device_name="Test PC",
                server_url="https://licenses.example",
            )

    monkeypatch.setattr("unused_file_finder.cli._license_manager", lambda _args=None: FakeManager())

    exit_code = run_cli(["license", "activate", "ABCD-EFGH-IJKL-MNOP"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "ABCD-****-****-MNOP" in captured.out
    assert "ABCD-EFGH-IJKL-MNOP" not in captured.out


def test_cli_scan_is_blocked_without_valid_license(monkeypatch, tmp_path: Path, capsys) -> None:
    monkeypatch.setattr(
        "unused_file_finder.cli._require_license_for_cli",
        lambda _args: LicenseStatus(
            can_use=False,
            valid=False,
            status="expired",
            reason="Licence expiree.",
            source="test",
        ),
    )

    exit_code = run_cli(["scan", "--root", str(tmp_path), "--no-whitelist"])

    captured = capsys.readouterr()
    assert exit_code == 3
    assert "Licence requise" in captured.err


def test_scheduled_scan_is_blocked_without_valid_license(monkeypatch, tmp_path: Path) -> None:
    class BlockedLicenseManager:
        def require_valid_license(self) -> None:
            raise LicenseError("Licence revoquee.")

    monkeypatch.setattr("unused_file_finder.scheduler.LicenseManager", BlockedLicenseManager)

    with pytest.raises(SchedulerError):
        run_scheduled_scan(tmp_path / "missing.json", notify=False)


def _client_with_response(payload: dict[str, object], *, status_code: int = 200) -> LicenseClient:
    def transport(_url: str, _payload: Mapping[str, object], _timeout: float) -> LicenseApiResponse:
        return LicenseApiResponse(status_code, payload)

    return LicenseClient("https://licenses.example", transport=transport)
