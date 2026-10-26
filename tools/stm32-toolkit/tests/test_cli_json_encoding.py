"""A real child CLI must emit decodable JSON under a legacy stdout codec.

The child process is started with ``PYTHONIOENCODING=gbk`` and
``PYTHONUTF8=0`` so inherited UTF-8 mode cannot hide the problem.  Only the
raw bytes are inspected: stdout must stay ASCII-escaped, decode as UTF-8, parse
as JSON, and preserve the original Chinese and non-BMP values.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_subprocess_json_is_ascii_escaped_under_gbk_stdout(tmp_path: Path) -> None:
    marker = "旧工程\U0001f600.ioc"  # 旧工程😀.ioc
    (tmp_path / marker).write_text("", encoding="utf-8")

    source_root = Path(__file__).resolve().parents[1] / "src"
    environment = dict(os.environ)
    environment["PYTHONIOENCODING"] = "gbk"
    environment["PYTHONUTF8"] = "0"
    environment["PYTHONPATH"] = os.pathsep.join(
        value
        for value in (str(source_root), environment.get("PYTHONPATH", ""))
        if value
    )

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "stm32_toolkit.cli",
            "--project-root",
            str(tmp_path),
            "project",
            "detect",
            "--json",
        ],
        capture_output=True,
        env=environment,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr.decode("utf-8", "replace")
    assert completed.stderr == b""
    # ASCII-only bytes make the output independent of the console code page.
    assert all(byte < 0x80 for byte in completed.stdout)

    payload = json.loads(completed.stdout.decode("utf-8"))
    assert payload["ok"] is True
    assert payload["operation"] == "project.detect"
    assert payload["data"]["kind"] == "cubemx"
    assert payload["data"]["files"] == [marker]
    # The non-BMP code point survived the escape round trip exactly.
    assert "\U0001f600" in payload["data"]["files"][0]
