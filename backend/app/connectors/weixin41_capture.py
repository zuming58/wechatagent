"""Fail-closed planning primitives for a future Windows passphrase capture.

This module does not attach to a process or set a breakpoint.  It turns a
read-only preflight result into a version- and binary-bound plan, and provides
an in-memory secret buffer that can be wiped after SQLCipher verification.
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from pathlib import Path

from .weixin41_crypto import PAGE_SIZE, derive_verified_key
from .weixin41_pe import PeAnalysisError, PeAnchorReport, select_capture_hook_rva
from .weixin41_preflight import ProcessPreflight, SUPPORTED_VERSION

PASSPHRASE_SIZE = 32


class CapturePlanError(RuntimeError):
    def __init__(self, error_code: str) -> None:
        super().__init__(error_code)
        self.error_code = error_code


@dataclass(frozen=True)
class CapturePlan:
    pid: int
    image_version: str
    module_sha256: str
    anchor_rva: int
    reference_rva: int
    hook_rva: int


@dataclass(frozen=True)
class PassphraseVerification:
    valid: bool
    matched_pages: int
    checked_pages: int


class PassphraseSecret:
    """Mutable secret storage with redacted display and deterministic wiping."""

    def __init__(self, value: bytes | bytearray | memoryview) -> None:
        if len(value) != PASSPHRASE_SIZE:
            raise ValueError(f"passphrase must be {PASSPHRASE_SIZE} bytes")
        self._buffer = bytearray(value)
        self._wiped = False

    def __repr__(self) -> str:
        return "<PassphraseSecret redacted>"

    def __enter__(self) -> PassphraseSecret:
        return self

    def __exit__(self, _exc_type, _exc, _traceback) -> None:
        self.wipe()

    @property
    def wiped(self) -> bool:
        return self._wiped

    def view(self) -> memoryview:
        if self._wiped:
            raise RuntimeError("passphrase_wiped")
        return memoryview(self._buffer)

    def wipe(self) -> None:
        for index in range(len(self._buffer)):
            self._buffer[index] = 0
        self._wiped = True


def select_hook_rva(report: PeAnchorReport) -> int:
    try:
        return select_capture_hook_rva(report)
    except PeAnalysisError as error:
        raise CapturePlanError(error.error_code) from error


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def build_capture_plan(preflight: ProcessPreflight, module_path: str | Path) -> CapturePlan:
    if preflight.error_code:
        raise CapturePlanError(preflight.error_code)
    if not preflight.handle_opened or not preflight.header_readable:
        raise CapturePlanError("process_not_readable")
    if preflight.image_version != SUPPORTED_VERSION:
        raise CapturePlanError("unsupported_version")
    if preflight.pe_report is None:
        raise CapturePlanError("module_analysis_missing")
    path = Path(module_path)
    if not path.is_file() or path.name.lower() != "weixin.dll":
        raise CapturePlanError("module_missing")
    if preflight.module_sha256 is None:
        raise CapturePlanError("module_binding_missing")
    module_sha256 = _sha256(path)
    if not hmac.compare_digest(module_sha256, preflight.module_sha256):
        raise CapturePlanError("module_changed")
    hook = select_hook_rva(preflight.pe_report)
    return CapturePlan(
        preflight.pid,
        preflight.image_version,
        module_sha256,
        preflight.pe_report.anchor_rvas[0],
        preflight.pe_report.rip_relative_reference_rvas[0],
        hook,
    )


def verify_passphrase(secret: PassphraseSecret, page_ones: list[bytes]) -> PassphraseVerification:
    if not page_ones:
        raise ValueError("at least one synthetic or caller-authorized page is required")
    checked = 0
    matched = 0
    for page in page_ones:
        if len(page) != PAGE_SIZE:
            raise ValueError("every page must be exactly one SQLCipher page")
        checked += 1
        if derive_verified_key(secret.view(), page) is not None:
            matched += 1
    return PassphraseVerification(matched > 0, matched, checked)
