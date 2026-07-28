import hashlib
from pathlib import Path

import pytest

from app.connectors.weixin41_capture import (
    CapturePlanError,
    PassphraseSecret,
    build_capture_plan,
    select_hook_rva,
    verify_passphrase,
)
from app.connectors.weixin41_pe import PeAnchorReport, PeSection
from app.connectors.weixin41_preflight import ProcessPreflight
from tests.test_weixin41_crypto import make_page_one


def report(*, anchors=(0x410,), refs=(0x320,), candidates=(0x310,)) -> PeAnchorReport:
    return PeAnchorReport(0x8664, 0x20B, (PeSection(".text", 0x300, 0x300, 0x100),), anchors, refs, candidates)


def preflight(pe_report=None, version="4.1.12.24", module_path=None, error_code=None) -> ProcessPreflight:
    module_sha256 = hashlib.sha256(module_path.read_bytes()).hexdigest() if module_path else None
    return ProcessPreflight(
        1234,
        "Weixin.exe",
        version,
        True,
        True,
        True,
        pe_report or report(),
        module_sha256,
        error_code,
    )


def test_capture_plan_is_bound_to_exact_version_binary_and_nearest_hook(tmp_path):
    module = tmp_path / "Weixin.dll"
    module.write_bytes(b"synthetic-weixin-module")
    pe_report = report(candidates=(0x310,))

    plan = build_capture_plan(preflight(pe_report, module_path=module), module)

    assert plan.pid == 1234
    assert plan.image_version == "4.1.12.24"
    assert plan.reference_rva == 0x320
    assert plan.hook_rva == 0x310
    assert len(plan.module_sha256) == 64


@pytest.mark.parametrize(
    ("pe_report", "error_code"),
    [
        (report(anchors=()), "wcdb_anchor_ambiguous"),
        (report(anchors=(0x410, 0x420)), "wcdb_anchor_ambiguous"),
        (report(refs=()), "wcdb_reference_ambiguous"),
        (report(refs=(0x320, 0x330)), "wcdb_reference_ambiguous"),
        (report(candidates=()), "capture_hook_missing"),
        (report(candidates=(0x300, 0x310)), "capture_hook_ambiguous"),
        (report(refs=(0x1000,), candidates=(0x100,)), "capture_hook_too_distant"),
    ],
)
def test_capture_plan_fails_closed_for_ambiguous_analysis(pe_report, error_code):
    with pytest.raises(CapturePlanError, match=error_code):
        select_hook_rva(pe_report)


def test_capture_plan_rejects_unapproved_version_and_module_name(tmp_path):
    module = tmp_path / "Weixin.dll"
    module.write_bytes(b"synthetic")
    with pytest.raises(CapturePlanError, match="unsupported_version"):
        build_capture_plan(preflight(version="4.1.13.1", module_path=module), module)

    wrong_module = tmp_path / "Other.dll"
    wrong_module.write_bytes(b"synthetic")
    with pytest.raises(CapturePlanError, match="module_missing"):
        build_capture_plan(preflight(module_path=module), wrong_module)


def test_capture_plan_rejects_a_module_that_changed_after_preflight(tmp_path):
    module = tmp_path / "Weixin.dll"
    module.write_bytes(b"analyzed-module")
    result = preflight(module_path=module)
    module.write_bytes(b"different-module")

    with pytest.raises(CapturePlanError, match="module_changed"):
        build_capture_plan(result, module)


def test_passphrase_secret_is_redacted_verified_and_wiped():
    passphrase = b"0123456789abcdef0123456789abcdef"
    page = make_page_one(passphrase)

    with PassphraseSecret(passphrase) as secret:
        assert repr(secret) == "<PassphraseSecret redacted>"
        assert verify_passphrase(secret, [page]).matched_pages == 1
        view = secret.view()

    assert secret.wiped
    assert bytes(view) == bytes(32)
    with pytest.raises(RuntimeError, match="passphrase_wiped"):
        secret.view()


def test_wrong_passphrase_is_not_accepted():
    page = make_page_one(b"0123456789abcdef0123456789abcdef")
    with PassphraseSecret(b"fedcba9876543210fedcba9876543210") as secret:
        result = verify_passphrase(secret, [page])

    assert not result.valid
    assert result.matched_pages == 0
    assert result.checked_pages == 1
