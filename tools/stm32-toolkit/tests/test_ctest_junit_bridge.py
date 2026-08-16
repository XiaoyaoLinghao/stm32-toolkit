"""Direct closed-frame tests for the private CTest JUnit bridge."""

from hashlib import sha256
from io import BytesIO
from multiprocessing.connection import Listener
import os
from pathlib import Path
import sys
import threading

import pytest

import stm32_toolkit.testing._ctest_junit_bridge as bridge
from stm32_toolkit.testing._ctest_junit_bridge import (
    BridgeFrameError,
    decode_frame,
    encode_frame,
)
from stm32_toolkit.testing.native_output import (
    NativeExitMismatch,
    NativeOutputError,
    parse_ctest_431_text,
)


NONCE = sha256(b"bridge-test").hexdigest()


def test_bridge_frame_binds_nonce_exit_streams_and_raw_junit_bytes():
    frame = encode_frame(NONCE, 1, b"out\n", b"err\n", b"<testsuite/>", None)
    assert decode_frame(frame, NONCE) == (1, b"out\n", b"err\n", b"<testsuite/>")
    with pytest.raises(BridgeFrameError):
        decode_frame(frame, "0" * 64)


def test_bridge_frame_rejects_corruption_and_helper_errors():
    frame = bytearray(encode_frame(NONCE, 0, b"out", b"", b"<testsuite/>", None))
    frame[-1] ^= 1
    with pytest.raises(BridgeFrameError, match="digest"):
        decode_frame(bytes(frame), NONCE)
    with pytest.raises(BridgeFrameError, match="deliberate"):
        decode_frame(encode_frame(NONCE, -1, b"", b"", b"", "deliberate"), NONCE)


@pytest.mark.parametrize("frame", [b"", b"\x00\x00\x00\x00", b"\x00\x00\x10\x01{}"])
def test_bridge_frame_rejects_invalid_bounds(frame: bytes):
    with pytest.raises(BridgeFrameError):
        decode_frame(frame, NONCE)


def test_bounded_sink_drains_and_marks_discarded_overflow():
    sink = bridge._BoundedSink(4)
    sink.drain(BytesIO(b"abcdef"))
    assert bytes(sink.data) == b"abcd"
    assert sink.truncated is True


@pytest.mark.parametrize(
    "arguments",
    [
        ("short", 0, b"", b"", b"", None),
        (NONCE, 0, b"", b"", b"", "x" * 1025),
        (NONCE, 0, b"", b"", b"", 1),
    ],
)
def test_encode_frame_rejects_invalid_scalar_contract(arguments):
    with pytest.raises(BridgeFrameError):
        encode_frame(*arguments)


def test_encode_frame_rejects_stream_overflow(monkeypatch):
    monkeypatch.setattr(bridge, "MAX_OUTPUT_BYTES", 0)
    with pytest.raises(BridgeFrameError, match="exceeds"):
        encode_frame(NONCE, 0, b"x", b"", b"", None)


def test_run_ctest_captures_real_exit_streams_and_junit(tmp_path: Path):
    code = (
        "import pathlib,sys; pathlib.Path(sys.argv[-1]).write_bytes(b'<testsuite/>'); "
        "print('out'); print('err',file=sys.stderr); raise SystemExit(3)"
    )
    result = bridge._run_ctest((sys.executable, "-c", code), tmp_path, tmp_path / "junit.xml")
    assert result == (3, b"out\r\n" if os.name == "nt" else b"out\n", b"err\r\n" if os.name == "nt" else b"err\n", b"<testsuite/>", None)


def test_run_ctest_reports_launch_missing_junit_and_output_limit(tmp_path: Path, monkeypatch):
    missing = bridge._run_ctest(("stm32tk-no-such-ctest",), tmp_path, tmp_path / "none.xml")
    assert missing[0] == -1 and missing[4].startswith("CTest bridge failed")

    monkeypatch.setattr(bridge, "MAX_OUTPUT_BYTES", 4)
    code = "import sys; sys.stdout.write('12345')"
    limited = bridge._run_ctest((sys.executable, "-c", code), tmp_path, tmp_path / "missing.xml")
    assert limited[1] == b"1234" and limited[4] == "CTest output exceeded bridge bound"


def test_send_supports_controller_owned_fd_and_named_pipe():
    read_fd, write_fd = os.pipe()
    bridge._send("fd", str(write_fd), NONCE, b"frame")
    assert os.read(read_fd, 16) == b"frame"
    os.close(read_fd)

    address = rf"\\.\pipe\stm32tk-bridge-unit-{os.getpid()}"
    listener = Listener(address, family="AF_PIPE", authkey=bytes.fromhex(NONCE))
    received = []
    worker = threading.Thread(target=lambda: received.append(listener.accept().recv_bytes()))
    worker.start()
    bridge._send("named-pipe", address, NONCE, b"pipe-frame")
    worker.join(5)
    listener.close()
    assert received == [b"pipe-frame"]
    with pytest.raises(BridgeFrameError):
        bridge._send("unknown", "x", NONCE, b"")


def test_main_writes_a_complete_frame_to_inherited_fd(tmp_path: Path):
    read_fd, write_fd = os.pipe()
    code = "import pathlib,sys; pathlib.Path(sys.argv[-1]).write_bytes(b'<testsuite/>')"
    arguments = [
        "fd", str(write_fd), NONCE, str(tmp_path), str(tmp_path), "--",
        sys.executable, "-c", code,
    ]
    assert bridge.main(arguments) == 0
    frame = os.read(read_fd, bridge.MAX_FRAME_BYTES)
    os.close(read_fd)
    assert decode_frame(frame, NONCE) == (0, b"", b"", b"<testsuite/>")
    assert bridge.main([]) == 64


def test_main_returns_transport_failure_without_leaking_exception(tmp_path: Path):
    arguments = [
        "unknown", "x", NONCE, str(tmp_path), str(tmp_path), "--",
        sys.executable, "-c", "pass",
    ]
    assert bridge.main(arguments) == 74


def test_shared_ctest_431_adapter_parses_frozen_real_pass_and_failure_outputs():
    fixture = Path(__file__).parent / "release/fixtures/native-outcomes"
    passed = (fixture / "ctest-4.3.1-output.txt").read_bytes()
    failed = (fixture / "ctest-4.3.1-failure-output.txt").read_bytes()
    assert parse_ctest_431_text(passed, exit_code=0) == (("native-pass", "passed"),)
    assert parse_ctest_431_text(failed, exit_code=1) == (
        ("pass-one", "passed"), ("pass-two", "passed"), ("fail-one", "failed"),
    )


def test_shared_ctest_431_adapter_maps_both_native_skip_spellings():
    raw = (
        b"1/2 Test #1: skip-one .... Not Run 0.01 sec\n"
        b"2/2 Test #2: skip-two .... Skipped 0.01 sec\n"
        b"100% tests passed, 0 tests failed out of 2\n"
    )
    assert parse_ctest_431_text(raw, exit_code=0) == (
        ("skip-one", "skipped"), ("skip-two", "skipped"),
    )


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"\xff",
        b"2/1 Test #1: one .... Passed 0.01 sec\n100% tests passed, 0 tests failed out of 1\n",
        b"1/1 Test #1: one .... Passed 0.01 sec\n",
        b"1/1 Test #1: one .... Passed 0.01 sec\n0% tests passed, 1 tests failed out of 1\n",
        (
            "1/1 Test #1: e\u0301 .... Passed 0.01 sec\n"
            "100% tests passed, 0 tests failed out of 1\n"
        ).encode("utf-8"),
    ],
)
def test_shared_ctest_431_adapter_rejects_malformed_or_contradictory_text(raw: bytes):
    with pytest.raises(NativeOutputError):
        parse_ctest_431_text(raw, exit_code=0)


def test_shared_ctest_431_adapter_rejects_invalid_or_contradictory_exit():
    raw = (
        b"1/1 Test #1: one .... Passed 0.01 sec\n"
        b"100% tests passed, 0 tests failed out of 1\n"
    )
    assert parse_ctest_431_text(raw) == (("one", "passed"),)
    with pytest.raises(NativeOutputError, match="exit code"):
        parse_ctest_431_text(raw, exit_code=True)
    with pytest.raises(NativeExitMismatch):
        parse_ctest_431_text(raw, exit_code=1)
