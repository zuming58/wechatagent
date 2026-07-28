from app.connectors.weixin41_pe import PeAnchorReport, PeSection
from app.connectors.weixin41_preflight import ProcessPreflight, _inspect_open_process, main
from tests.test_weixin41_pe import make_synthetic_pe


def report(*, anchors=(0x410,), refs=(0x320,), candidates=(0x310,)) -> PeAnchorReport:
    return PeAnchorReport(0x8664, 0x20B, (PeSection(".text", 0x300, 0x300, 0x100),), anchors, refs, candidates)


def result(*, pe_report=None, module_sha256="a" * 64, error_code=None) -> ProcessPreflight:
    return ProcessPreflight(
        pid=1234,
        image_name="Weixin.exe",
        image_version="4.1.12.24",
        image_path_available=True,
        handle_opened=True,
        header_readable=True,
        pe_report=report() if pe_report is None else pe_report,
        module_sha256=module_sha256,
        error_code=error_code,
    )


def test_capture_ready_requires_a_complete_unambiguous_analysis():
    assert result().capture_ready
    assert not result(module_sha256=None).capture_ready
    assert not result(pe_report=report(anchors=())).capture_ready
    assert not result(pe_report=report(refs=())).capture_ready
    assert not result(pe_report=report(candidates=())).capture_ready
    assert not result(error_code="module_analysis_failed").capture_ready


def test_main_fails_when_any_process_is_not_capture_ready(monkeypatch, capsys):
    blocked = result(error_code="module_missing")
    monkeypatch.setattr("app.connectors.weixin41_preflight.run_preflight", lambda: [result(), blocked])

    assert main() == 3
    output = capsys.readouterr().out
    assert "ready=True" in output
    assert "ready=False" in output
    assert "error=module_missing" in output


def test_main_succeeds_only_for_fully_valid_results(monkeypatch, capsys):
    monkeypatch.setattr("app.connectors.weixin41_preflight.run_preflight", lambda: [result()])

    assert main() == 0
    assert "ready=True" in capsys.readouterr().out


def test_inspection_binds_version_hash_and_analysis_to_the_target_image(monkeypatch, tmp_path):
    executable = tmp_path / "Weixin.exe"
    executable.touch()
    module = tmp_path / "Weixin.dll"
    make_synthetic_pe(module)
    seen_paths = []
    monkeypatch.setattr("app.connectors.weixin41_preflight._query_image_path", lambda _handle: executable)
    monkeypatch.setattr("app.connectors.weixin41_preflight._read_module_header", lambda _handle, _name: True)
    monkeypatch.setattr(
        "app.connectors.weixin41_preflight.WxCliConnector._executable_version",
        lambda path: seen_paths.append(path) or "4.1.12.24",
    )

    inspected = _inspect_open_process(1234, 99)

    assert inspected.capture_ready
    assert inspected.module_sha256 and len(inspected.module_sha256) == 64
    assert seen_paths == [executable]


def test_inspection_reports_invalid_and_missing_modules_without_false_success(monkeypatch, tmp_path):
    executable = tmp_path / "Weixin.exe"
    executable.touch()
    module = tmp_path / "Weixin.dll"
    module.write_bytes(b"not-a-pe")
    monkeypatch.setattr("app.connectors.weixin41_preflight._query_image_path", lambda _handle: executable)
    monkeypatch.setattr("app.connectors.weixin41_preflight._read_module_header", lambda _handle, _name: True)
    monkeypatch.setattr(
        "app.connectors.weixin41_preflight.WxCliConnector._executable_version",
        lambda _path: "4.1.12.24",
    )

    invalid = _inspect_open_process(1234, 99)
    assert invalid.error_code == "module_analysis_failed"
    assert not invalid.capture_ready

    module.unlink()
    missing = _inspect_open_process(1234, 99)
    assert missing.error_code == "module_missing"
    assert not missing.capture_ready
