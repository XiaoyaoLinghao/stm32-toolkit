"""Private CTest JUnit transport used by :mod:`stm32_toolkit.testing.host`.

CTest writes JUnit through an atomic temporary-file rename.  This helper keeps
that pathname inside a per-run scratch directory and returns the completed
bytes to the controller over a pre-created IPC endpoint.
"""

from __future__ import annotations

from hashlib import sha256
import json
from multiprocessing.connection import Client
import os
from pathlib import Path
import subprocess
import sys
import threading


FRAME_SCHEMA = "stm32-ctest-junit-bridge/1"
MAX_JUNIT_BYTES = 64 * 1024 * 1024
MAX_OUTPUT_BYTES = 8 * 1024 * 1024
MAX_FRAME_BYTES = MAX_JUNIT_BYTES + 2 * MAX_OUTPUT_BYTES + 4096
_HEADER_KEYS = {
    "schema", "nonce", "returncode", "stdout_length", "stdout_sha256",
    "stderr_length", "stderr_sha256", "junit_length", "junit_sha256", "error",
}


class BridgeFrameError(ValueError):
    """The helper/controller frame was malformed or exceeded a hard bound."""


class _BoundedSink:
    def __init__(self, limit: int) -> None:
        self.data = bytearray()
        self.limit = limit
        self.truncated = False

    def drain(self, stream) -> None:
        while True:
            chunk = stream.read(65536)
            if not chunk:
                return
            room = self.limit - len(self.data)
            self.data.extend(chunk[:room])
            if len(chunk) > room:
                self.truncated = True


def encode_frame(
    nonce: str, returncode: int | None, stdout: bytes, stderr: bytes,
    junit: bytes, error: str | None,
) -> bytes:
    if not isinstance(nonce, str) or len(nonce) != 64:
        raise BridgeFrameError("invalid nonce")
    if error is not None and (not isinstance(error, str) or len(error.encode("utf-8")) > 1024):
        raise BridgeFrameError("invalid error")
    if len(stdout) > MAX_OUTPUT_BYTES or len(stderr) > MAX_OUTPUT_BYTES or len(junit) > MAX_JUNIT_BYTES:
        raise BridgeFrameError("bridge payload exceeds bound")
    header = {
        "schema": FRAME_SCHEMA, "nonce": nonce, "returncode": returncode,
        "stdout_length": len(stdout), "stdout_sha256": sha256(stdout).hexdigest(),
        "stderr_length": len(stderr), "stderr_sha256": sha256(stderr).hexdigest(),
        "junit_length": len(junit), "junit_sha256": sha256(junit).hexdigest(),
        "error": error,
    }
    encoded = json.dumps(header, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return len(encoded).to_bytes(4, "big") + encoded + stdout + stderr + junit


def decode_frame(frame: bytes, expected_nonce: str) -> tuple[int, bytes, bytes, bytes]:
    if not isinstance(frame, bytes) or not 4 <= len(frame) <= MAX_FRAME_BYTES:
        raise BridgeFrameError("invalid frame size")
    header_length = int.from_bytes(frame[:4], "big")
    if not 1 <= header_length <= 4096 or 4 + header_length > len(frame):
        raise BridgeFrameError("invalid frame header")
    try:
        header = json.loads(frame[4:4 + header_length].decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise BridgeFrameError("invalid frame header") from exc
    if not isinstance(header, dict) or set(header) != _HEADER_KEYS:
        raise BridgeFrameError("invalid frame shape")
    lengths = [header.get(name) for name in ("stdout_length", "stderr_length", "junit_length")]
    if (
        header.get("schema") != FRAME_SCHEMA or header.get("nonce") != expected_nonce
        or any(type(value) is not int or value < 0 for value in lengths)
        or lengths[0] > MAX_OUTPUT_BYTES or lengths[1] > MAX_OUTPUT_BYTES
        or lengths[2] > MAX_JUNIT_BYTES or sum(lengths) != len(frame) - 4 - header_length
    ):
        raise BridgeFrameError("invalid frame binding")
    offset = 4 + header_length
    stdout = frame[offset:offset + lengths[0]]; offset += lengths[0]
    stderr = frame[offset:offset + lengths[1]]; offset += lengths[1]
    junit = frame[offset:offset + lengths[2]]
    for name, value in (("stdout", stdout), ("stderr", stderr), ("junit", junit)):
        if header.get(f"{name}_sha256") != sha256(value).hexdigest():
            raise BridgeFrameError("frame digest mismatch")
    error = header.get("error")
    returncode = header.get("returncode")
    if error is not None:
        if not isinstance(error, str):
            raise BridgeFrameError("invalid helper error")
        raise BridgeFrameError(error)
    if type(returncode) is not int:
        raise BridgeFrameError("missing CTest return code")
    return returncode, stdout, stderr, junit


def _run_ctest(argv: tuple[str, ...], cwd: Path, junit_path: Path) -> tuple[int, bytes, bytes, bytes, str | None]:
    stdout = _BoundedSink(MAX_OUTPUT_BYTES)
    stderr = _BoundedSink(MAX_OUTPUT_BYTES)
    command = (*argv, "--output-junit", str(junit_path))
    try:
        process = subprocess.Popen(
            command, cwd=str(cwd), stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False,
        )
        threads = [
            threading.Thread(target=stdout.drain, args=(process.stdout,)),
            threading.Thread(target=stderr.drain, args=(process.stderr,)),
        ]
        for thread in threads: thread.start()
        returncode = process.wait()
        for thread in threads: thread.join()
        if stdout.truncated or stderr.truncated:
            return returncode, bytes(stdout.data), bytes(stderr.data), b"", "CTest output exceeded bridge bound"
        junit = junit_path.read_bytes()
        return returncode, bytes(stdout.data), bytes(stderr.data), junit, None
    except (OSError, ValueError) as exc:
        return -1, bytes(stdout.data), bytes(stderr.data), b"", f"CTest bridge failed: {type(exc).__name__}"


def _send(kind: str, channel: str, auth_hex: str, frame: bytes) -> None:
    if kind == "named-pipe":
        connection = Client(channel, family="AF_PIPE", authkey=bytes.fromhex(auth_hex))
        try:
            connection.send_bytes(frame)
        finally:
            connection.close()
    elif kind == "fd":
        descriptor = int(channel)
        view = memoryview(frame)
        while view:
            view = view[os.write(descriptor, view):]
        os.close(descriptor)
    else:
        raise BridgeFrameError("invalid channel kind")


def main(argv: list[str]) -> int:
    if len(argv) < 7 or argv[5] != "--":
        return 64
    kind, channel, nonce, scratch_text, cwd_text = argv[:5]
    scratch = Path(scratch_text)
    junit_path = scratch / "ctest-native-junit.xml"
    returncode, stdout, stderr, junit, error = _run_ctest(tuple(argv[6:]), Path(cwd_text), junit_path)
    try:
        frame = encode_frame(nonce, returncode, stdout, stderr, junit, error)
        _send(kind, channel, nonce, frame)
    except (BridgeFrameError, OSError, ValueError):
        return 74
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised as a real subprocess
    raise SystemExit(main(sys.argv[1:]))
