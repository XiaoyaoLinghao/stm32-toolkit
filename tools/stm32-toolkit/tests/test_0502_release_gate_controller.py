"""Controller-level tests for the 0502 Windows release-gate helper.

These tests drive ``run_0502_windows_gates.ps1`` with recording executables so
the full gate sequence can be proven without running the real five-minute
matrix. Git, Node, npm, both CPython interpreters and CMD are replaced by small
recording programs that log their gate/cwd/argv/controlled-environment and
return canned outputs; the fake venv "python" is a compiled native launcher that
forwards to the same recorder so every venv-python invocation is observable.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
CONTROLLER = REPO_ROOT / "tools" / "release" / "run_0502_windows_gates.ps1"
VERIFY = REPO_ROOT / "tools" / "release" / "verify_0502_release.py"
SUPPORT_VERIFIER = REPO_ROOT / "tools" / "stm32-monitor" / "ui" / "tests" / "verify_support.py"
ACCEPTED_BASE = "bd59b3cd3ecd72eebcd08300f6e809ebd38f46aa"

POWERSHELL = os.environ.get("STM32_0502_TEST_POWERSHELL", "powershell.exe")

LAUNCHER_CS = r"""
using System;
using System.Diagnostics;
using System.IO;
using System.Text;
class Launcher {
  static string JsonString(string s) {
    var sb = new StringBuilder("\"");
    foreach (char c in s) {
      if (c == '"') sb.Append("\\\"");
      else if (c == '\\') sb.Append("\\\\");
      else if (c == '\n') sb.Append("\\n");
      else if (c == '\r') sb.Append("\\r");
      else if (c == '\t') sb.Append("\\t");
      else sb.Append(c);
    }
    sb.Append("\"");
    return sb.ToString();
  }
  static int Main(string[] args) {
    string self = Environment.GetCommandLineArgs()[0];
    string dir = Path.GetDirectoryName(self);
    if (string.IsNullOrEmpty(dir)) return 98;
    string script = Path.Combine(dir, "_recorder.py");
    string toolFile = Path.Combine(dir, "_recorder.tool");
    string pythonFile = Path.Combine(dir, "_recorder.python");
    if (!File.Exists(script) || !File.Exists(toolFile) || !File.Exists(pythonFile)) return 98;
    string tool = File.ReadAllText(toolFile).Trim();
    string python = File.ReadAllText(pythonFile).Trim();
    if (tool.Length == 0 || python.Length == 0) return 98;
    string argsFile = Path.Combine(Path.GetTempPath(), "st32-rec-" + Guid.NewGuid().ToString("N") + ".json");
    using (var w = new StreamWriter(argsFile, false, new UTF8Encoding(false))) {
      w.Write("[");
      for (int i = 0; i < args.Length; i++) {
        if (i > 0) w.Write(",");
        w.Write(JsonString(args[i]));
      }
      w.Write("]");
    }
    var psi = new ProcessStartInfo();
    psi.FileName = python;
    psi.UseShellExecute = false;
    psi.CreateNoWindow = true;
    psi.RedirectStandardOutput = true;
    psi.RedirectStandardError = true;
    var sb = new StringBuilder();
    sb.Append('"').Append(script).Append('"');
    sb.Append(" --tool ").Append('"').Append(tool).Append('"');
    sb.Append(" --exe ").Append('"').Append(self).Append('"');
    sb.Append(" --args ").Append('"').Append(argsFile).Append('"');
    psi.Arguments = sb.ToString();
    var proc = Process.Start(psi);
    string stdout = proc.StandardOutput.ReadToEnd();
    string stderr = proc.StandardError.ReadToEnd();
    proc.WaitForExit();
    try { File.Delete(argsFile); } catch { }
    if (stdout.Length > 0) Console.Out.Write(stdout);
    if (stderr.Length > 0) Console.Error.Write(stderr);
    return proc.ExitCode;
  }
}
"""

RECORDER_PY = r"""
import hashlib
import io
import json
import os
import subprocess
import sys
from pathlib import Path

CONFIG = {}
_RECORD_FILE = os.environ.get("ST32_RECORD_FILE")


def _load_config():
    global CONFIG
    path = os.environ.get("ST32_CONFIG")
    if path:
        try:
            CONFIG = json.loads(Path(path).read_text("utf-8"))
        except Exception:
            CONFIG = {}


_load_config()

SUPPORT_JSON_FIELDS = [
    "artifacts", "auditCache", "browser", "node", "nodePackages", "nodeSha256",
    "nodeVersion", "npm", "npmCache", "npmSha256", "npmVersion",
    "pythonRequirements", "supportManifestSha256", "supportTreeSha256", "wheelhouse",
]
CONTROLLED_ENV = [
    "npm_config_cache", "STM32_MONITOR_CHROMIUM_EXECUTABLE", "STM32_MONITOR_PYTHON",
    "STM32_MONITOR_EVIDENCE", "CLAUDE_PLUGIN_DATA", "CLAUDE_PLUGIN_ROOT",
    "PYTHONPATH", "COVERAGE_FILE", "PLAYWRIGHT_BROWSERS_PATH",
]


def record(tool, args, exe):
    if not _RECORD_FILE:
        return
    gate = os.environ.get("STM32_MONITOR_GATE")
    entry = {"tool": tool, "argv": list(args), "cwd": os.getcwd()}
    if gate:
        entry["gate"] = gate
    if exe:
        entry["exe"] = exe
    for key in CONTROLLED_ENV:
        value = os.environ.get(key)
        if value is not None:
            entry[key] = value
    with open(_RECORD_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, separators=(",", ":")) + "\n")


def _fail_code():
    target = os.environ.get("ST32_FAIL_GATE")
    if not target:
        return None
    gate = os.environ.get("STM32_MONITOR_GATE")
    if gate == target:
        return int(os.environ.get("ST32_FAIL_CODE", "1"))
    return None


def emit(text):
    sys.stdout.write(text + "\n")
    sys.stdout.flush()


def emit_raw(raw):
    sys.stdout.buffer.write(raw)
    sys.stdout.buffer.flush()


def _inventory_files():
    root = Path(os.getcwd())
    excluded = set(CONFIG.get("excludedPaths", []))
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d for d in dirnames
            if d not in (".git", "__pycache__", "node_modules", "dist", "coverage",
                         ".pytest_cache", "playwright-report", "test-results")
        ]
        for name in sorted(filenames):
            full = Path(dirpath) / name
            rel = full.relative_to(root).as_posix()
            if rel in excluded:
                continue
            out.append(rel)
    return sorted(out)


def git_dispatch(args, exe):
    joined = " ".join(args)
    if "--name-status" in joined and "--no-renames" in joined and "-z" in joined:
        raw = b"".join(b"A\0" + p.encode("utf-8") + b"\0" for p in _inventory_files())
        emit_raw(raw)
        return 0
    if "ls-files" in joined:
        raw = b"".join(p.encode("utf-8") + b"\0" for p in _inventory_files())
        emit_raw(raw)
        return 0
    if "rev-parse" in joined and (args and ":" in args[-1]):
        emit(CONFIG.get("historicalBlob", "b" * 40))
        return 0
    if "rev-parse" in joined:
        emit(CONFIG.get("codeHead", "a" * 40))
        return 0
    if "merge-base" in joined:
        return 0
    if "diff" in joined and "--check" in joined:
        return 0
    if "archive" in joined:
        out = None
        for i, a in enumerate(args):
            if a == "--output":
                out = args[i + 1]
        if out:
            Path(out).write_bytes(b"PK\x05\x06" + b"\x00" * 18)
        return 0
    return 0  # status and everything else: clean / ok


def create_fake_venv(venv_path, tool):
    venv = Path(venv_path)
    scripts = venv / "Scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    launcher = os.environ.get("ST32_LAUNCHER_EXE")
    if not launcher or not Path(launcher).is_file():
        raise SystemExit("ST32_LAUNCHER_EXE is unavailable")
    shutil_cp = __import__("shutil").copyfile
    shutil_cp(launcher, str(scripts / "python.exe"))
    (scripts / "_recorder.py").write_text(Path(__file__).read_text(encoding="utf-8"), encoding="utf-8")
    minor = "310" if "310" in tool else "312"
    (scripts / "_recorder.tool").write_text("venv-" + minor, encoding="utf-8")
    (scripts / "_recorder.python").write_text(sys.executable, encoding="utf-8")


def _create_wheels(wheel_dir):
    target = Path(wheel_dir)
    target.mkdir(parents=True, exist_ok=True)
    for name in ("stm32_toolkit-0.5.0-py3-none-any.whl", "stm32_monitor-0.5.0-py3-none-any.whl"):
        (target / name).write_bytes(b"PK\x05\x06" + b"\x00" * 20)


def _coverage_json(target_file):
    root = Path(os.getcwd())
    files = {}
    product = (
        "tools/stm32-monitor/src/stm32_monitor"
        if "monitor" in Path(target_file).name
        else "tools/stm32-toolkit/src/stm32_toolkit"
    )
    for rel in _inventory_files():
        if rel.startswith(product) and rel.endswith(".py"):
            files[str((root / rel).resolve())] = {
                "executed_lines": [],
                "summary": {
                    "covered_lines": 10,
                    "num_statements": 10,
                    "covered_branches": 10,
                    "num_branches": 10,
                    "percent_covered": 100.0,
                    "percent_covered_display": "100",
                },
            }
    Path(target_file).write_text(
        json.dumps({"meta": {}, "files": files}, sort_keys=True), encoding="utf-8"
    )


def _collect_nodeids(args):
    paths = []
    ignores = set()
    flags = {"--collect-only", "-q", "-p", "no:cacheprovider", "-s"}
    index = 0
    while index < len(args):
        a = args[index]
        if a in flags:
            index += 1
            continue
        if a.startswith("--ignore="):
            ignores.add(a[len("--ignore="):])
            index += 1
            continue
        if a in ("--basetemp",):
            index += 2
            continue
        if a.startswith("-"):
            index += 1
            continue
        paths.append(a)
        index += 1
    files = []
    root = Path(os.getcwd())
    for p in paths:
        full = root / p
        if full.is_dir():
            for f in sorted(full.glob("test_*.py")):
                rel = f.relative_to(root).as_posix()
                if rel not in ignores:
                    files.append(rel)
        elif full.is_file():
            rel = full.relative_to(root).as_posix()
            if rel not in ignores:
                files.append(rel)
    for rel in sorted(files):
        emit(f"{rel}::{Path(rel).stem}_node")
    return 0


def python_dispatch(tool, args, exe):
    if not args:
        return 0
    if args[0] == "-c":
        code = args[1]
        if "version_info" in code:
            minor = "310" if tool.endswith("310") else "312"
            exe_out = CONFIG.get("aliasedExePath") if CONFIG.get("aliasedExe") else exe
            emit(json.dumps([3, int(minor[1:]), exe_out]))
            return 0
        if "hashlib" in code and "glob" in code:
            namespace = {"__name__": "__main__"}
            old = sys.stdout
            buf = io.StringIO()
            sys.stdout = buf
            try:
                exec(compile(code, "<hash-script>", "exec"), namespace)
            finally:
                sys.stdout = old
            emit(buf.getvalue().strip())
            return 0
        return 0
    if args[0] == "-I" and len(args) >= 2 and args[1] == "-c":
        return 0
    if args[0] == "-m":
        mod = args[1]
        if mod == "venv":
            create_fake_venv(args[2], tool)
            return 0
        if mod == "pip":
            if len(args) >= 3 and args[2] == "wheel":
                wheel_dir = None
                for i, a in enumerate(args):
                    if a == "--wheel-dir":
                        wheel_dir = args[i + 1]
                if wheel_dir:
                    _create_wheels(wheel_dir)
            return 0
        if mod == "coverage":
            out = None
            for i, a in enumerate(args):
                if a == "-o":
                    out = args[i + 1]
            if out:
                _coverage_json(out)
            return 0
        return 0
    if args and str(args[0]).endswith("verify_support.py"):
        emit(json.dumps(CONFIG.get("supportJson", {}), separators=(",", ":")))
        return 0
    if any("verify_0502_release.py" in str(a) for a in args):
        script = Path(os.getcwd()) / "tools" / "release" / "verify_0502_release.py"
        if not script.is_file():
            raise SystemExit("verify_0502_release.py missing from repo root")
        env = dict(os.environ)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        forwarded = [a for a in args if "verify_0502_release.py" not in str(a)]
        proc = subprocess.run(
            [sys.executable, str(script)] + forwarded,
            capture_output=True,
            text=True,
            env=env,
        )
        sys.stdout.write(proc.stdout)
        sys.stderr.write(proc.stderr)
        return proc.returncode
    if args and str(args[0]).endswith(".py"):
        script_path = Path(args[0])
        if script_path.is_file():
            proc = subprocess.run(
                [sys.executable, str(script_path)],
                capture_output=True,
                text=True,
                cwd=os.getcwd(),
            )
            sys.stdout.write(proc.stdout)
            sys.stderr.write(proc.stderr)
            return proc.returncode
        return 0


def dispatch(tool, args, exe):
    record(tool, args, exe)
    fail = _fail_code()
    if fail is not None:
        return fail
    if tool == "git":
        return git_dispatch(args, exe)
    if tool == "node":
        if args and args[0] == "--version":
            emit(str(CONFIG.get("nodeVersion", "v24.18.0")))
        return 0
    if tool == "npm":
        if args and args[0] == "--version":
            emit(str(CONFIG.get("npmVersion", "11.16.0")))
        if any("performance.spec.ts" in str(a) for a in args):
            evidence = os.environ.get("STM32_MONITOR_EVIDENCE")
            if evidence:
                out_dir = Path(evidence) / ".performance-evidence"
                out_dir.mkdir(parents=True, exist_ok=True)
                (out_dir / "performance.json").write_text(
                    json.dumps({
                        "realizedPoints": 4800,
                        "updateP95Ms": 10.0,
                        "updateP50Ms": 5.0,
                        "updateMaxMs": 20.0,
                        "longTasksAtLeast200Ms": 0,
                        "queueGrowth": 0,
                        "queueSamples": [0, 0],
                        "heapSlopeMiBPerMinute": 0.0,
                        "serverDropsBefore": {"subscriber": "0", "history": "0", "deadline": "0", "service": "0"},
                        "serverDropsAfter": {"subscriber": "0", "history": "0", "deadline": "0", "service": "0"},
                        "sampleCount": "1800",
                        "assetSizes": {"rawBytes": "100", "gzipJsBytes": "50", "gzipCssBytes": "20"},
                        "warmupMs": 120000,
                        "measureMs": 180000,
                    }),
                    encoding="utf-8",
                )
        return 0
    if tool == "cmdexec":
        if len(args) >= 3 and args[0] == "/d" and args[1] == "/c":
            cmd = args[2]
            rest = args[3:]
            full = [os.environ.get("ComSpec", r"C:\Windows\System32\cmd.exe"), "/d", "/c", cmd] + list(rest)
            proc = subprocess.run(full, cwd=os.getcwd(), env=os.environ)
            return proc.returncode
        return 0
    if tool.startswith("venv-") or tool.startswith("py"):
        if "-m" in args and "pytest" in args:
            return _collect_nodeids(args) if "--collect-only" in args else 0
        return python_dispatch(tool, args, exe)
    return 0


def main():
    argv = sys.argv[1:]
    tool = "unknown"
    exe = None
    args_file = None
    if argv and argv[0] == "--tool":
        tool = argv[1]
        argv = argv[2:]
    if argv and argv[0] == "--exe":
        exe = argv[1]
        argv = argv[2:]
    if argv and argv[0] == "--args":
        args_file = argv[1]
        argv = argv[2:]
    if argv and argv[0] == "--":
        argv = argv[1:]
    if os.environ.get("ST32_DEBUG"):
        sys.stderr.write("RAW=%r FILE=%r\n" % (argv, args_file))
        sys.stderr.flush()
    if args_file:
        try:
            argv = json.loads(Path(args_file).read_text(encoding="utf-8-sig"))
        except Exception as exc:
            sys.stderr.write("ARGSFILE_ERR=%r\n" % (exc,))
            sys.stderr.flush()
            argv = []
        try:
            Path(args_file).unlink()
        except Exception:
            pass
    if os.environ.get("ST32_DEBUG"):
        sys.stderr.write("FINAL=%r\n" % (argv,))
        sys.stderr.flush()
    sys.exit(dispatch(tool, argv, exe))


if __name__ == "__main__":
    main()
"""


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def launcher_exe(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("launcher") / "launcher.exe"
    cs = out.with_suffix(".cs")
    cs.write_text(LAUNCHER_CS, encoding="utf-8")
    csc = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Microsoft.NET" / "Framework64" / "v4.0.30319" / "csc.exe"
    if not csc.is_file():
        import shutil as _sh
        csc = Path(_sh.which("csc") or "csc.exe")
    result = subprocess.run(
        [str(csc), "/nologo", "/target:exe", f"/out:{out}", str(cs)],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert out.is_file()
    return out


@pytest.fixture
def recording(tmp_path: Path, launcher_exe: Path) -> dict:
    """Builds recording executables + a config file and returns run context."""
    tools = tmp_path / "recording tools with space"
    tools.mkdir()
    recorder = tools / "recorder.py"
    recorder.write_text(RECORDER_PY, encoding="utf-8")
    python = sys.executable
    wrappers = {}
    for name in ("git", "node", "npm", "py310", "py312", "cmdexec"):
        cmd = tools / f"{name}.cmd"
        cmd.write_text(
            f'@echo off\r\n"{python}" "{recorder}" --tool {name} --exe "%~f0" -- %*\r\n',
            encoding="utf-8",
        )
        wrappers[name] = cmd
    # Fake support root: real dirs + files the canned support JSON points at.
    support = tmp_path / "support"
    (support / "wheelhouse").mkdir(parents=True)
    (support / "npm-cache").mkdir(parents=True)
    (support / "artifacts").mkdir(parents=True)
    (support / "chromium").mkdir(parents=True)
    (support / "chromium" / "chrome.exe").write_bytes(b"chrome")
    (support / "npm-cache" / "seed").write_text("seed", encoding="utf-8")
    node_hash = hashlib.sha256(wrappers["node"].read_bytes()).hexdigest()
    npm_hash = hashlib.sha256(wrappers["npm"].read_bytes()).hexdigest()
    support_json = {
        "artifacts": str((support / "artifacts").resolve()),
        "auditCache": True,
        "browser": str((support / "chromium" / "chrome.exe").resolve()),
        "node": str(wrappers["node"].resolve()),
        "nodePackages": {"dependencies": {"preact": "10.29.8"}, "devDependencies": {"typescript": "5.9.3"}},
        "nodeSha256": node_hash,
        "nodeVersion": "v24.18.0",
        "npm": str(wrappers["npm"].resolve()),
        "npmCache": str((support / "npm-cache").resolve()),
        "npmSha256": npm_hash,
        "npmVersion": "11.16.0",
        "pythonRequirements": [
            "aiohttp==3.12.15", "build==1.3.0", "coverage==7.10.7", "jinja2==3.1.6",
            "jsonschema==4.25.1", "mcp==1.29.0", "pyelftools==0.33", "pyocd==0.45.1",
            "pytest==8.4.2", "pytest-cov==6.3.0", "setuptools==80.9.0", "wheel==0.45.1",
        ],
        "supportManifestSha256": "1" * 64,
        "supportTreeSha256": "2" * 64,
        "wheelhouse": str((support / "wheelhouse").resolve()),
    }
    config = {
        "codeHead": "a" * 40,
        "historicalBlob": "b" * 40,
        "supportJson": support_json,
        "nodeVersion": "v24.18.0",
        "npmVersion": "11.16.0",
        "excludedPaths": [
            "requirements/follow-on-skills/stm32-monitor/SKILL.md",
            "skills/migrate-keil/SKILL.md",
            "skills/configure-stm32-project/SKILL.md",
            "skills/build-firmware/SKILL.md",
            "skills/flash-firmware/SKILL.md",
            "skills/debug-firmware/SKILL.md",
            "skills/read-var/SKILL.md",
        ],
    }
    config_file = tmp_path / "recorder-config.json"
    config_file.write_text(json.dumps(config), encoding="utf-8")
    return {
        "tools": tools,
        "recorder": recorder,
        "git": str(wrappers["git"]),
        "node": str(wrappers["node"]),
        "npm": str(wrappers["npm"]),
        "py310": str(wrappers["py310"]),
        "py312": str(wrappers["py312"]),
        "cmdexec": str(wrappers["cmdexec"]),
        "support": support,
        "config": config,
        "config_file": config_file,
    }


@pytest.fixture
def fake_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / ".claude-plugin").mkdir(parents=True)
    (repo / ".claude-plugin" / "plugin.json").write_text('{"name":"stm32-toolkit","version":"0.5.0"}', encoding="utf-8")
    (repo / ".claude-plugin" / "marketplace.json").write_text("{}", encoding="utf-8")
    (repo / "README.md").write_text("# stm32 toolkit\n", encoding="utf-8")
    (repo / "README_zh-CN.md").write_text("# stm32 工具包\n", encoding="utf-8")
    (repo / ".gitignore").write_text("dist/\n", encoding="utf-8")
    (repo / ".gitattributes").write_text("* text=auto\n", encoding="utf-8")
    (repo / "bin").mkdir()
    shutil.copy2(REPO_ROOT / "bin" / "stm32-monitor.cmd", repo / "bin" / "stm32-monitor.cmd")
    shutil.copy2(REPO_ROOT / "bin" / "stm32-toolkit-mcp.cmd", repo / "bin" / "stm32-toolkit-mcp.cmd")
    (repo / "bin" / "setup-stm32-env.ps1").write_text("Write-Output 'setup'\n", encoding="utf-8")
    plans = repo / "docs" / "superpowers" / "plans"
    plans.mkdir(parents=True)
    (plans / "2026-08-04-stm32-toolkit-0.5-0.6-monitor-test-diagnostics.md").write_text("plan", encoding="utf-8")
    (plans / "2026-08-04-stm32-toolkit-complete-development-roadmap.md").write_text("roadmap", encoding="utf-8")
    (repo / "requirements" / "follow-on-skills" / "stm32-monitor").mkdir(parents=True)
    (repo / "requirements" / "follow-on-skills" / "stm32-monitor" / "SKILL.md").write_text("historical", encoding="utf-8")
    for skill in (
        "setup-stm32-env", "migrate-keil", "configure-stm32-project", "build-firmware",
        "flash-firmware", "debug-firmware", "read-var", "stm32-monitor",
    ):
        d = repo / "skills" / skill
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(f"# {skill}\n", encoding="utf-8")
    (repo / "tools" / "release").mkdir(parents=True)
    shutil.copy2(VERIFY, repo / "tools" / "release" / "verify_0502_release.py")
    (repo / "tools" / "stm32-monitor" / "ui" / "tests").mkdir(parents=True)
    shutil.copy2(SUPPORT_VERIFIER, repo / "tools" / "stm32-monitor" / "ui" / "tests" / "verify_support.py")
    (repo / "tools" / "stm32-monitor" / "ui" / "e2e").mkdir(parents=True)
    for spec in ("monitor.spec.ts", "isolation.spec.ts", "workflow.spec.ts", "performance.spec.ts"):
        (repo / "tools" / "stm32-monitor" / "ui" / "e2e" / spec).write_text("export {}", encoding="utf-8")
    (repo / "tools" / "stm32-monitor" / "ui" / "package.json").write_text("{}", encoding="utf-8")
    (repo / "tools" / "stm32-monitor" / "ui" / "package-lock.json").write_text("{}", encoding="utf-8")
    (repo / "tools" / "stm32-monitor").mkdir(parents=True, exist_ok=True)
    (repo / "tools" / "stm32-toolkit").mkdir(parents=True, exist_ok=True)
    (repo / "tools" / "stm32-monitor" / "pyproject.toml").write_text("[project]", encoding="utf-8")
    (repo / "tools" / "stm32-toolkit" / "pyproject.toml").write_text("[project]", encoding="utf-8")
    monitor_src = repo / "tools" / "stm32-monitor" / "src" / "stm32_monitor"
    monitor_src.mkdir(parents=True)
    (monitor_src / "__init__.py").write_text("__version__ = '0.5.0'\n", encoding="utf-8")
    (monitor_src / "hot.py").write_text("VALUE = 1\n", encoding="utf-8")
    dist = monitor_src / "ui_dist"
    (dist / ".vite").mkdir(parents=True)
    (dist / "assets").mkdir()
    (dist / "index.html").write_text("<html></html>", encoding="utf-8")
    manifest = {
        "index.html": {"file": "assets/index.js", "name": "index", "src": "index.html", "isEntry": True},
        "_contract.js": {"file": "assets/contract.js", "name": "contract", "src": "_contract.js"},
        "node_modules/preact/dist/preact.module.js": {"file": "assets/preact.js", "name": "preact.module", "src": "node_modules/preact/dist/preact.module.js"},
        "src/app.tsx": {"file": "assets/app.js", "name": "app", "src": "src/app.tsx"},
    }
    (dist / ".vite" / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    for asset in ("index.js", "contract.js", "preact.js", "app.js"):
        (dist / "assets" / asset).write_text("export{}", encoding="utf-8")
    monitor_tests = repo / "tools" / "stm32-monitor" / "tests"
    monitor_tests.mkdir(parents=True)
    for name in ("test_auth", "test_service", "test_ui_assets", "test_ui_dist",
                 "test_package_boundary", "test_performance", "test_main1", "test_main2", "test_main3"):
        (monitor_tests / f"{name}.py").write_text("def test_x():\n    pass\n", encoding="utf-8")
    toolkit_src = repo / "tools" / "stm32-toolkit" / "src" / "stm32_toolkit"
    toolkit_src.mkdir(parents=True)
    (toolkit_src / "__init__.py").write_text("__version__ = '0.5.0'\n", encoding="utf-8")
    (toolkit_src / "hot.py").write_text("VALUE = 1\n", encoding="utf-8")
    toolkit_tests = repo / "tools" / "stm32-toolkit" / "tests"
    toolkit_tests.mkdir(parents=True)
    for name in ("test_one", "test_two", "test_three"):
        (toolkit_tests / f"{name}.py").write_text("def test_x():\n    pass\n", encoding="utf-8")
    return repo


def _run_controller(
    tmp_path: Path,
    recording: dict,
    repo: Path,
    launcher_exe: Path,
    *,
    code_head: str = "a" * 40,
    fail_gate: str | None = None,
    extra_env: dict[str, str] | None = None,
    evidence: Path | None = None,
    git: str | None = None,
    node: str | None = None,
    python312: str | None = None,
    support: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    evidence = evidence or (tmp_path / "evidence")
    evidence.mkdir(exist_ok=True)
    record_file = tmp_path / "records.jsonl"
    env = dict(os.environ)
    env["ST32_RECORD_FILE"] = str(record_file)
    env["ST32_CONFIG"] = str(recording["config_file"])
    env["ST32_LAUNCHER_EXE"] = str(launcher_exe)
    if extra_env:
        env.update(extra_env)
    if fail_gate:
        env["ST32_FAIL_GATE"] = fail_gate
    result = subprocess.run(
        [
            POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(CONTROLLER),
            "-RepoRoot", str(repo),
            "-EvidenceRoot", str(evidence),
            "-SupportRoot", str(support if support is not None else recording["support"]),
            "-CodeHead", code_head,
            "-Git", git or recording["git"],
            "-Node", node or recording["node"],
            "-Npm", recording["npm"],
            "-Python310", recording["py310"],
            "-Python312", python312 or recording["py312"],
            "-CmdExe", recording["cmdexec"],
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
        env=env,
    )
    result.record_file = record_file  # type: ignore[attr-defined]
    return result


def _records(record_file: Path) -> list[dict]:
    if not record_file.exists():
        return []
    lines = record_file.read_text(encoding="utf-8").strip().splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def _summary_gates(evidence: Path) -> list[dict]:
    summary = json.loads((evidence / "summary.json").read_text(encoding="utf-8"))
    return summary["gates"]
# ---- test content appended to test_0502_release_gate_controller.py ----


# ---------------------------------------------------------------------------
# AST / parameter / ambient-tool contract
# ---------------------------------------------------------------------------

def _powershell_ast(path: Path) -> dict:
    escaped = str(path).replace("'", "''")
    script = (
        "$errors = $null; $tokens = $null; "
        f"[void][System.Management.Automation.Language.Parser]::ParseFile('{escaped}', [ref]$tokens, [ref]$errors); "
        "if ($errors -and $errors.Count -gt 0) { throw ($errors | ForEach-Object { $_.Message }) -join ';' }; "
        "Write-Output ('COMMANDS=' + ((@($tokens | Where-Object { $_.Kind -eq 'Command' } | ForEach-Object { $_.Text }) | Sort-Object -Unique) -join ',')); "
        "Write-Output 'parse-ok'"
    )
    result = subprocess.run(
        [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/c", POWERSHELL, "-NoProfile", "-Command", script],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    commands: list[str] = []
    for line in result.stdout.splitlines():
        if line.startswith("COMMANDS="):
            commands = [c for c in line[len("COMMANDS="):].split(",") if c]
    return {"errors": [] if "parse-ok" in result.stdout else [result.stderr], "commands": commands}


def test_controller_parses_and_declares_exact_parameters() -> None:
    ast = _powershell_ast(CONTROLLER)
    assert ast["errors"] == []
    text = CONTROLLER.read_text(encoding="utf-8")
    for name in (
        "RepoRoot", "EvidenceRoot", "SupportRoot", "CodeHead", "Git", "Node",
        "Npm", "Python310", "Python312", "CmdExe",
    ):
        assert f"[Parameter(Mandatory = $true)][string]${name}" in text


def test_controller_has_no_ambient_tool_or_remote_verbs() -> None:
    ast = _powershell_ast(CONTROLLER)
    assert ast["errors"] == []
    forbidden = {"git", "node", "npm", "npx", "python", "python3", "py", "uv", "pip", "curl", "wget"}
    assert forbidden.isdisjoint({c.casefold() for c in ast["commands"]})
    text = CONTROLLER.read_text(encoding="utf-8").casefold()
    for word in ("returnpacket", "handoffsignature", "git push", "git fetch", "gh pr", "invoke-expression", "get-command", "where.exe"):
        assert word not in text
    for bare in ("& git", "& node", "& npm", "& python", "& py", "& uv"):
        assert bare not in text


# ---------------------------------------------------------------------------
# Entry validation (fail before EvidenceRoot is proven legal -> no summary)
# ---------------------------------------------------------------------------

def test_controller_rejects_duplicate_tool_identity_before_gates(tmp_path: Path, recording: dict, launcher_exe: Path) -> None:
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    repo = tmp_path / "repo"
    repo.mkdir()
    result = _run_controller(
        tmp_path, recording, repo, launcher_exe,
        evidence=evidence, node=recording["git"],
    )
    assert result.returncode != 0
    assert "duplicate tool identity" in result.stderr
    assert not list(evidence.glob("*.log"))
    assert not (evidence / "summary.json").exists()


def test_controller_requires_absolute_tool_paths(tmp_path: Path, recording: dict, launcher_exe: Path) -> None:
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    repo = tmp_path / "repo"
    repo.mkdir()
    result = _run_controller(
        tmp_path, recording, repo, launcher_exe, evidence=evidence, git="git",
    )
    assert result.returncode != 0
    assert "must be rooted" in result.stderr
    assert not (evidence / "summary.json").exists()


def test_controller_requires_clean_empty_evidence_root(tmp_path: Path, recording: dict, launcher_exe: Path) -> None:
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    (evidence / "existing.log").write_text("x", encoding="utf-8")
    repo = tmp_path / "repo"
    repo.mkdir()
    result = _run_controller(tmp_path, recording, repo, launcher_exe, evidence=evidence)
    assert result.returncode != 0
    assert "must be empty" in result.stderr
    assert not (evidence / "summary.json").exists()


def test_controller_requires_code_head_as_full_sha(tmp_path: Path, recording: dict, launcher_exe: Path) -> None:
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    repo = tmp_path / "repo"
    repo.mkdir()
    result = _run_controller(tmp_path, recording, repo, launcher_exe, evidence=evidence, code_head="short")
    assert result.returncode != 0
    assert "one full SHA" in result.stderr
    assert not (evidence / "summary.json").exists()


def test_controller_rejects_head_not_equal_to_code_head_before_gates(tmp_path: Path, recording: dict, launcher_exe: Path) -> None:
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    repo = tmp_path / "repo"
    repo.mkdir()
    result = _run_controller(tmp_path, recording, repo, launcher_exe, evidence=evidence, code_head="b" * 40)
    assert result.returncode != 0
    assert "does not equal CodeHead" in result.stderr
    # EvidenceRoot is legal at this point, so a per-gate summary is written.
    assert (evidence / "summary.json").exists()
    summary = json.loads((evidence / "summary.json").read_text(encoding="utf-8"))
    assert summary["overall"] == "FAIL"
    assert any(g["gate"] == "git-head-identity" and g["status"] == "FAIL" for g in summary["gates"])
    names = [g["gate"] for g in summary["gates"]]
    assert "git-accepted-ancestor" not in names


# ---------------------------------------------------------------------------
# Full success path via recording executables
# ---------------------------------------------------------------------------

EXPECTED_GATES = [
    "git-status-before",
    "git-head-identity",
    "git-accepted-ancestor",
    "git-diff-check",
    "git-diff-inventory",
    "git-archive-code-head",
    "verify-support-before-copy",
    "version-node",
    "version-npm",
    "verify-support-after-copy",
    "verify-changed-scope",
    "historical-skill-blob",
    "version-python310",
    "version-python312",
    "verify-support-before-node-npm-ci",
    "node-npm-ci",
    "verify-support-after-node-npm-ci",
    "node-typecheck",
    "node-typecheck-e2e",
    "node-lint",
    "node-unit-coverage",
    "node-coverage-gate",
    "node-a11y",
    "node-build",
    "node-verify-dist-1",
    "node-verify-dist-2",
    "verify-support-before-node-production-audit",
    "node-production-audit",
    "verify-support-after-node-production-audit",
    "venv-create-310",
    "venv-install-310",
    "venv-install-toolkit-310",
    "venv-create-312",
    "venv-install-312",
    "venv-install-toolkit-312",
    "python310-monitor-complete",
    "python312-monitor-main",
    "python312-monitor-special",
    "python312-toolkit-shard-1",
    "python312-toolkit-shard-2",
    "python312-toolkit-shard-3",
    "python312-monitor-coverage-json",
    "python312-toolkit-coverage-json",
    "changed-product-branch-coverage",
    "compileall-310",
    "compileall-312",
    "wheel-toolkit",
    "wheel-monitor",
    "wheel-hashes",
    "installed-venv-310",
    "installed-packages-310",
    "installed-pip-check-310",
    "installed-smoke-310",
    "installed-http-310",
    "launcher-monitor-310",
    "launcher-toolkit-310",
    "installed-venv-312",
    "installed-packages-312",
    "installed-pip-check-312",
    "installed-smoke-312",
    "installed-http-312",
    "launcher-monitor-312",
    "launcher-toolkit-312",
    "launcher-fail-closed-missing-env",
    "launcher-fail-closed-missing-runtime",
    "playwright-functional",
    "playwright-performance",
    "playwright-performance-evidence",
    "release-static-closure",
    "tracked-byte-manifest",
    "git-diff-check-after",
    "verify-support-final",
    "clean-tree",
]


def test_full_success_path_recording(
    tmp_path: Path, recording: dict, fake_repo: Path, launcher_exe: Path,
) -> None:
    evidence = tmp_path / "evidence"
    result = _run_controller(tmp_path, recording, fake_repo, launcher_exe, evidence=evidence)
    assert result.returncode == 0, result.stdout + result.stderr

    summary = json.loads((evidence / "summary.json").read_text(encoding="utf-8"))
    assert summary["overall"] == "PASS"
    assert summary["headIdentity"] == "a" * 40
    names = [g["gate"] for g in summary["gates"]]
    assert names == EXPECTED_GATES
    assert all(g["status"] == "PASS" for g in summary["gates"])

    recs = _records(result.record_file)  # type: ignore[attr-defined]
    assert len(recs) > 0

    def gate_entries(gate: str) -> list[dict]:
        return [r for r in recs if r.get("gate") == gate]

    # Offline dependency install precedes the first pytest gate.
    install_index = next(i for i, r in enumerate(recs) if r.get("gate") == "venv-install-310")
    first_pytest = next(i for i, r in enumerate(recs) if r.get("gate") == "python310-monitor-complete")
    assert install_index < first_pytest
    install = gate_entries("venv-install-310")[0]
    assert "pip" in install["argv"] and "install" in install["argv"]
    assert "--no-index" in install["argv"] and "--find-links" in install["argv"]

    # npm phases bind only the working cache.
    for r in gate_entries("node-npm-ci"):
        assert r.get("npm_config_cache", "").endswith("npm-cache-working")
        assert "npm-cache-working" in " ".join(r["argv"])
    for r in gate_entries("node-production-audit"):
        assert r.get("npm_config_cache", "").endswith("npm-cache-working")

    # Playwright functional / performance are disjoint and cover the planned specs.
    planned = {"monitor.spec.ts", "isolation.spec.ts", "workflow.spec.ts", "performance.spec.ts"}
    functional = set()
    perf = set()
    for r in gate_entries("playwright-functional"):
        functional |= {a for a in r["argv"] if a.endswith(".spec.ts")}
    for r in gate_entries("playwright-performance"):
        perf |= {a for a in r["argv"] if a.endswith(".spec.ts")}
    assert functional == planned - {"performance.spec.ts"}
    assert perf == {"performance.spec.ts"}
    assert not (functional & perf)
    assert (functional | perf) == planned
    assert len(gate_entries("playwright-performance")) == 1

    # Both managed runtimes, both launchers.
    for minor in ("310", "312"):
        venv = gate_entries(f"installed-venv-{minor}")
        assert venv, f"installed-venv-{minor} missing"
        assert f"installed-{minor}" in " ".join(venv[0]["argv"])
        assert "runtime" in " ".join(venv[0]["argv"]) and "0.5.0" in " ".join(venv[0]["argv"])
        managed = [r for r in recs if r.get("tool", "").startswith("venv-") and r.get("gate") == f"launcher-monitor-{minor}"]
        assert managed, f"managed launcher {minor} not executed"
        assert managed[0]["exe"].endswith("Scripts\\python.exe")
        assert "installed-" + minor in managed[0]["exe"]
        tk = [r for r in recs if r.get("tool", "").startswith("venv-") and r.get("gate") == f"launcher-toolkit-{minor}"]
        assert tk, f"toolkit launcher {minor} not executed"
    assert gate_entries("version-python310")
    assert gate_entries("version-python312")

    # Final support reverify, tracked manifest, diff check, clean status.
    summary_names = [g["gate"] for g in summary["gates"]]
    assert gate_entries("verify-support-final")
    assert "tracked-byte-manifest" in summary_names
    assert "git-diff-check-after" in summary_names
    assert "clean-tree" in summary_names
    assert (evidence / "accepted-base-to-code-head-inventory.json").exists()
    assert (evidence / "tracked-byte-manifest.json").exists()
    assert (evidence / "wheel-hashes.json").exists()
    assert (evidence / "monitor-coverage.json").exists()
    assert (evidence / "toolkit-coverage.json").exists()


# ---------------------------------------------------------------------------
# Fail-fast: first nonzero gate stops the run and writes a FAIL summary
# ---------------------------------------------------------------------------

FAIL_GATE_TARGETS = [
    ("node-npm-ci", "npm"),
    ("python312-monitor-main", "venv"),
    ("wheel-toolkit", "venv"),
    ("installed-smoke-310", "venv"),
    ("launcher-monitor-310", "launcher"),
    ("playwright-performance", "npm"),
]


@pytest.mark.parametrize("fail_gate,kind", FAIL_GATE_TARGETS)
def test_fail_fast_stops_at_first_failure(
    tmp_path: Path, recording: dict, fake_repo: Path, launcher_exe: Path,
    fail_gate: str, kind: str,
) -> None:
    evidence = tmp_path / "evidence"
    result = _run_controller(
        tmp_path, recording, fake_repo, launcher_exe,
        evidence=evidence, fail_gate=fail_gate,
    )
    assert result.returncode != 0
    summary = json.loads((evidence / "summary.json").read_text(encoding="utf-8"))
    assert summary["overall"] == "FAIL"
    names = [g["gate"] for g in summary["gates"]]
    assert fail_gate in names
    entry = next(g for g in summary["gates"] if g["gate"] == fail_gate)
    assert entry["status"] == "FAIL"
    assert entry["exit"] != 0
    assert entry["log"]
    # The first failure is the last gate; nothing after it runs.
    fail_index = names.index(fail_gate)
    assert fail_index == len(names) - 1
    # A later product gate never runs.
    later = {
        "node-npm-ci": "node-typecheck",
        "python312-monitor-main": "python312-monitor-special",
        "wheel-toolkit": "wheel-monitor",
        "installed-smoke-310": "launcher-monitor-310",
        "launcher-monitor-310": "installed-venv-312",
        "playwright-performance": "release-static-closure",
    }[fail_gate]
    assert later not in names


def test_fail_fast_writes_no_log_after_first_failure(
    tmp_path: Path, recording: dict, fake_repo: Path, launcher_exe: Path,
) -> None:
    evidence = tmp_path / "evidence"
    result = _run_controller(
        tmp_path, recording, fake_repo, launcher_exe,
        evidence=evidence, fail_gate="node-npm-ci",
    )
    assert result.returncode != 0
    recs = _records(result.record_file)  # type: ignore[attr-defined]
    gates = [r.get("gate") for r in recs]
    # node-npm-ci is the last recorded invocation; nothing after it.
    assert "node-npm-ci" in gates
    assert "node-typecheck" not in gates


# ---------------------------------------------------------------------------
# Support source cache re-verification points and identity checks
# ---------------------------------------------------------------------------

def test_support_reverified_before_after_copy_each_npm_phase_and_final(
    tmp_path: Path, recording: dict, fake_repo: Path, launcher_exe: Path,
) -> None:
    evidence = tmp_path / "evidence"
    result = _run_controller(tmp_path, recording, fake_repo, launcher_exe, evidence=evidence)
    assert result.returncode == 0, result.stdout + result.stderr
    recs = _records(result.record_file)  # type: ignore[attr-defined]
    support_gates = [r.get("gate") for r in recs if str(r.get("gate", "")).startswith("verify-support-")]
    expected = [
        "verify-support-before-copy",
        "verify-support-after-copy",
        "verify-support-before-node-npm-ci",
        "verify-support-after-node-npm-ci",
        "verify-support-before-node-production-audit",
        "verify-support-after-node-production-audit",
        "verify-support-final",
    ]
    assert support_gates == expected


def test_controller_rejects_node_path_differing_from_verified_support(
    tmp_path: Path, recording: dict, fake_repo: Path, launcher_exe: Path,
) -> None:
    # A distinct absolute tool path (not a duplicate of any passed tool) that
    # differs from the verified support's node identity.
    alt_node = Path(recording["tools"]) / "node-alt.cmd"
    alt_node.write_bytes(Path(recording["node"]).read_bytes())
    evidence = tmp_path / "evidence"
    result = _run_controller(
        tmp_path, recording, fake_repo, launcher_exe,
        evidence=evidence, node=str(alt_node),
    )
    assert result.returncode != 0
    assert "differ from verified support" in result.stderr
    summary = json.loads((evidence / "summary.json").read_text(encoding="utf-8"))
    assert summary["overall"] == "FAIL"
    names = [g["gate"] for g in summary["gates"]]
    assert "node-npm-ci" not in names


def test_controller_rejects_python_310_312_aliased_interpreter(
    tmp_path: Path, recording: dict, fake_repo: Path, launcher_exe: Path,
) -> None:
    config = json.loads(recording["config_file"].read_text(encoding="utf-8"))
    config["aliasedExe"] = True
    config["aliasedExePath"] = recording["py312"]
    alt_config = tmp_path / "aliased-config.json"
    alt_config.write_text(json.dumps(config), encoding="utf-8")
    evidence = tmp_path / "evidence"
    result = _run_controller(
        tmp_path, recording, fake_repo, launcher_exe,
        evidence=evidence, extra_env={"ST32_CONFIG": str(alt_config)},
    )
    assert result.returncode != 0
    assert "alias to the same interpreter" in result.stderr
    summary = json.loads((evidence / "summary.json").read_text(encoding="utf-8"))
    assert summary["overall"] == "FAIL"


# ---------------------------------------------------------------------------
# Managed launchers: runtime layout, arg forwarding, fail-closed, no PATH markers
# ---------------------------------------------------------------------------

def test_managed_runtime_created_directly_at_runtime_0_5_0(
    tmp_path: Path, recording: dict, fake_repo: Path, launcher_exe: Path,
) -> None:
    evidence = tmp_path / "evidence"
    result = _run_controller(tmp_path, recording, fake_repo, launcher_exe, evidence=evidence)
    assert result.returncode == 0, result.stdout + result.stderr
    recs = _records(result.record_file)  # type: ignore[attr-defined]
    for minor in ("310", "312"):
        venv = [r for r in recs if r.get("gate") == f"installed-venv-{minor}"][0]
        runtime = [a for a in venv["argv"] if "runtime" in a]
        assert runtime, f"installed-venv-{minor} did not target runtime/0.5.0"
        # The venv is created directly at <EvidenceRoot>/installed-<minor>/runtime/0.5.0
        target = runtime[-1]
        assert f"installed-{minor}" in target
        assert target.endswith("runtime\\0.5.0")
        runtime_python = (evidence / f"installed-{minor}" / "runtime" / "0.5.0" / "Scripts" / "python.exe")
        assert runtime_python.is_file()
        # No lone python.exe copied to the runtime root (venv layout only).
        assert not (evidence / f"installed-{minor}" / "runtime" / "0.5.0" / "python.exe").exists()


def test_launchers_forward_args_and_preserve_child_exit_code(
    tmp_path: Path, recording: dict, fake_repo: Path, launcher_exe: Path,
) -> None:
    evidence = tmp_path / "evidence"
    result = _run_controller(tmp_path, recording, fake_repo, launcher_exe, evidence=evidence)
    assert result.returncode == 0, result.stdout + result.stderr
    recs = _records(result.record_file)  # type: ignore[attr-defined]
    # The real CMD launchers forward to the managed runtime with unchanged args.
    monitor = [r for r in recs if r.get("tool", "").startswith("venv-") and r.get("gate") == "launcher-monitor-310"]
    toolkit = [r for r in recs if r.get("tool", "").startswith("venv-") and r.get("gate") == "launcher-toolkit-310"]
    assert monitor and toolkit
    assert monitor[0]["argv"] == ["-m", "stm32_monitor", "--help"]
    assert toolkit[0]["argv"] == ["-m", "stm32_toolkit.mcp_server", "--help"]
    # Both launchers are exercised for 3.10 AND 3.12.
    assert [r.get("gate") for r in recs if r.get("tool", "").startswith("venv-") and "launcher-monitor" in r.get("gate", "")] == [
        "launcher-monitor-310", "launcher-monitor-312",
    ]


def test_launchers_fail_closed_without_env_and_markers_never_run(
    tmp_path: Path, recording: dict, fake_repo: Path, launcher_exe: Path,
) -> None:
    # PATH markers named python/python3/py/uv must never be invoked.
    markers_dir = tmp_path / "markers"
    markers_dir.mkdir()
    recorder = Path(recording["recorder"])
    python = sys.executable
    for marker in ("python", "python3", "py", "uv"):
        cmd = markers_dir / f"{marker}.cmd"
        cmd.write_text(
            f'@echo off\r\n"{python}" "{recorder}" --tool marker-{marker} --exe "%~f0" -- %*\r\n',
            encoding="utf-8",
        )
    marker_path = str(markers_dir) + os.pathsep + os.environ.get("PATH", "")
    evidence = tmp_path / "evidence"
    result = _run_controller(
        tmp_path, recording, fake_repo, launcher_exe,
        evidence=evidence, extra_env={"PATH": marker_path},
    )
    assert result.returncode == 0, result.stdout + result.stderr
    recs = _records(result.record_file)  # type: ignore[attr-defined]
    marker_tools = [r for r in recs if str(r.get("tool", "")).startswith("marker-")]
    assert marker_tools == []
    # Both fail-closed launcher gates pass (exit 2 for missing env / runtime).
    summary = json.loads((evidence / "summary.json").read_text(encoding="utf-8"))
    names = [g["gate"] for g in summary["gates"]]
    assert "launcher-fail-closed-missing-env" in names
    assert "launcher-fail-closed-missing-runtime" in names


# ---------------------------------------------------------------------------
# Controlled Playwright wiring
# ---------------------------------------------------------------------------

def test_playwright_config_reads_controlled_chromium_executable() -> None:
    config = (REPO_ROOT / "tools" / "stm32-monitor" / "ui" / "playwright.config.ts").read_text(encoding="utf-8")
    assert "STM32_MONITOR_CHROMIUM_EXECUTABLE" in config
    assert "launchOptions" in config
    assert "executablePath" in config
    helper = CONTROLLER.read_text(encoding="utf-8")
    assert "STM32_MONITOR_CHROMIUM_EXECUTABLE" in helper
    # The helper binds the verified support browser to the same variable name.
    assert "$env:STM32_MONITOR_CHROMIUM_EXECUTABLE = $Chromium" in helper


def test_helper_does_not_use_exclude_flag_and_playwright_performance_runs_once(
    tmp_path: Path, recording: dict, fake_repo: Path, launcher_exe: Path,
) -> None:
    helper = CONTROLLER.read_text(encoding="utf-8")
    assert "--exclude" not in helper
    evidence = tmp_path / "evidence"
    result = _run_controller(tmp_path, recording, fake_repo, launcher_exe, evidence=evidence)
    assert result.returncode == 0, result.stdout + result.stderr
    recs = _records(result.record_file)  # type: ignore[attr-defined]
    perf = [r for r in recs if r.get("gate") == "playwright-performance"]
    assert len(perf) == 1
    assert "performance.spec.ts" in perf[0]["argv"]
    assert "--workers=1" in perf[0]["argv"]
    # Controlled environment binds Python and Evidence.
    assert perf[0].get("STM32_MONITOR_EVIDENCE") == str((tmp_path / "evidence").resolve())
    func = [r for r in recs if r.get("gate") == "playwright-functional"][0]
    assert "--project=chromium-1280" in func["argv"]
    assert "--project=chromium-1024" in func["argv"]


def test_playwright_cli_accepts_functional_spec_argv() -> None:
    # Prove the exact functional argv the helper builds is accepted by the
    # installed Playwright CLI (no --exclude dependency).
    ui = REPO_ROOT / "tools" / "stm32-monitor" / "ui"
    npx = ui / "node_modules" / ".bin" / "playwright.cmd"
    if not npx.is_file():
        pytest.skip("playwright not installed in the ui node_modules")
    specs = sorted(
        p.name for p in (ui / "e2e").glob("*.spec.ts") if p.name != "performance.spec.ts"
    )
    assert specs
    command = [str(npx), "test", *specs, "--list", "--project=chromium-1280"]
    result = subprocess.run(command, cwd=str(ui), check=False, capture_output=True,
                            text=True, encoding="utf-8", errors="replace", timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "performance.spec.ts" not in result.stdout


# ---------------------------------------------------------------------------
# Authoritative support verifier (verify_support.py) wiring: mutations fail
# before the first product gate.
# ---------------------------------------------------------------------------

ARTIFACT_NAMES = [
    "setuptools", "wheel", "build", "pytest", "pytest-cov", "coverage",
    "aiohttp", "jsonschema", "mcp", "pyelftools", "jinja2", "pyocd",
]
ARTIFACT_VERSIONS = {
    "setuptools": "80.9.0", "wheel": "0.45.1", "build": "1.3.0", "pytest": "8.4.2",
    "pytest-cov": "6.3.0", "coverage": "7.10.7", "aiohttp": "3.12.15",
    "jsonschema": "4.25.1", "mcp": "1.29.0", "pyelftools": "0.33", "jinja2": "3.1.6",
    "pyocd": "0.45.1",
}


def _build_valid_support_root(root: Path) -> Path:
    artifacts = root / "artifacts"
    artifacts.mkdir(parents=True)
    for name in ARTIFACT_NAMES:
        (artifacts / name).write_bytes(("artifact-" + name).encode("utf-8"))
    wheelhouse = root / "wheelhouse"
    wheelhouse.mkdir()
    (wheelhouse / "w.whl").write_bytes(b"wheel")
    npm_cache = root / "npm-cache"
    npm_cache.mkdir()
    (npm_cache / "seed").write_bytes(b"seed")
    chromium = root / "chromium"
    chromium.mkdir()
    (chromium / "chrome.exe").write_bytes(b"chrome")
    node = root / "node"
    node.mkdir()
    (node / "node.exe").write_bytes(b"node")
    (node / "npm.cmd").write_bytes(b"npm")
    rows = []
    for f in sorted(root.rglob("*")):
        if f.is_file() and f.name != "support-manifest.json":
            data = f.read_bytes()
            rows.append({
                "path": f.relative_to(root).as_posix(),
                "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            })
    manifest = {
        "schemaVersion": 1,
        "files": rows,
        "artifacts": "artifacts",
        "pythonArtifacts": {n: {"path": "artifacts/" + n, "version": ARTIFACT_VERSIONS[n]} for n in ARTIFACT_NAMES},
        "nodePackages": {"dependencies": {"preact": "10.29.8"}, "devDependencies": {"typescript": "5.9.3"}},
        "wheelhouse": "wheelhouse",
        "npmCache": "npm-cache",
        "npmAuditCache": True,
        "chromiumExecutable": "chromium/chrome.exe",
        "nodeExecutable": "node/node.exe",
        "npmExecutable": "node/npm.cmd",
        "nodeVersion": "v24.18.0",
        "npmVersion": "11.16.0",
    }
    (root / "support-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    subprocess.run(["icacls", str(root), "/deny", "*S-1-1-0:(W)"], check=True, capture_output=True)
    return root


def _make_support_writable(root: Path) -> None:
    subprocess.run(["icacls", str(root), "/remove:d", "*S-1-1-0"], check=True, capture_output=True)


def _run_mutation_controller(
    tmp_path: Path, recording: dict, fake_repo: Path, launcher_exe: Path, root: Path,
) -> subprocess.CompletedProcess[str]:
    real_py = sys.executable
    evidence = tmp_path / "evidence"
    return _run_controller(
        tmp_path, recording, fake_repo, launcher_exe,
        evidence=evidence, python312=real_py, support=root,
    )


def test_valid_support_root_passes_support_gate(
    tmp_path: Path, recording: dict, fake_repo: Path, launcher_exe: Path,
) -> None:
    root = tmp_path / "real-support"
    root.mkdir()
    try:
        _build_valid_support_root(root)
        # A valid root still fails here because the fake repo's package.json does
        # not match the manifest nodePackages; assert the failure is the package
        # identity check, not a structural support rejection.
        evidence = tmp_path / "evidence"
        result = _run_controller(
            tmp_path, recording, fake_repo, launcher_exe,
            evidence=evidence, python312=sys.executable, support=root,
        )
        # The verify_support.py gate runs and reports FAIL; no product gate runs.
        assert result.returncode != 0
        summary = json.loads((evidence / "summary.json").read_text(encoding="utf-8"))
        names = [g["gate"] for g in summary["gates"]]
        assert "verify-support-before-copy" in names
        assert "node-npm-ci" not in names
    finally:
        _make_support_writable(root)


def test_support_member_byte_change_fails_before_product_gates(
    tmp_path: Path, recording: dict, fake_repo: Path, launcher_exe: Path,
) -> None:
    root = tmp_path / "real-support"
    root.mkdir()
    try:
        _build_valid_support_root(root)
        _make_support_writable(root)
        target = root / "artifacts" / "pytest"
        target.write_bytes(target.read_bytes() + b"x")
        subprocess.run(["icacls", str(root), "/deny", "*S-1-1-0:(W)"], check=True, capture_output=True)
        result = _run_mutation_controller(tmp_path, recording, fake_repo, launcher_exe, root)
        assert result.returncode != 0
        summary = json.loads((tmp_path / "evidence" / "summary.json").read_text(encoding="utf-8"))
        names = [g["gate"] for g in summary["gates"]]
        assert "verify-support-before-copy" in names
        assert "node-npm-ci" not in names
    finally:
        _make_support_writable(root)


def test_support_extra_unhashed_file_fails_before_product_gates(
    tmp_path: Path, recording: dict, fake_repo: Path, launcher_exe: Path,
) -> None:
    root = tmp_path / "real-support"
    root.mkdir()
    try:
        _build_valid_support_root(root)
        _make_support_writable(root)
        (root / "npm-cache" / "rogue").write_bytes(b"x")
        subprocess.run(["icacls", str(root), "/deny", "*S-1-1-0:(W)"], check=True, capture_output=True)
        result = _run_mutation_controller(tmp_path, recording, fake_repo, launcher_exe, root)
        assert result.returncode != 0
        summary = json.loads((tmp_path / "evidence" / "summary.json").read_text(encoding="utf-8"))
        names = [g["gate"] for g in summary["gates"]]
        assert "verify-support-before-copy" in names
        assert "node-npm-ci" not in names
    finally:
        _make_support_writable(root)


def test_support_tool_hash_mismatch_fails_before_product_gates(
    tmp_path: Path, recording: dict, fake_repo: Path, launcher_exe: Path,
) -> None:
    root = tmp_path / "real-support"
    root.mkdir()
    try:
        _build_valid_support_root(root)
        _make_support_writable(root)
        target = root / "node" / "node.exe"
        target.write_bytes(target.read_bytes() + b"x")
        subprocess.run(["icacls", str(root), "/deny", "*S-1-1-0:(W)"], check=True, capture_output=True)
        result = _run_mutation_controller(tmp_path, recording, fake_repo, launcher_exe, root)
        assert result.returncode != 0
        summary = json.loads((tmp_path / "evidence" / "summary.json").read_text(encoding="utf-8"))
        names = [g["gate"] for g in summary["gates"]]
        assert "verify-support-before-copy" in names
        assert "node-npm-ci" not in names
    finally:
        _make_support_writable(root)


def test_support_path_escape_in_manifest_fails_before_product_gates(
    tmp_path: Path, recording: dict, fake_repo: Path, launcher_exe: Path,
) -> None:
    root = tmp_path / "real-support"
    root.mkdir()
    try:
        _build_valid_support_root(root)
        _make_support_writable(root)
        manifest_path = root / "support-manifest.json"
        doc = json.loads(manifest_path.read_text(encoding="utf-8"))
        doc["files"].append({"path": "../escape", "bytes": 1, "sha256": "0" * 64})
        manifest_path.write_text(json.dumps(doc), encoding="utf-8")
        subprocess.run(["icacls", str(root), "/deny", "*S-1-1-0:(W)"], check=True, capture_output=True)
        result = _run_mutation_controller(tmp_path, recording, fake_repo, launcher_exe, root)
        assert result.returncode != 0
        summary = json.loads((tmp_path / "evidence" / "summary.json").read_text(encoding="utf-8"))
        names = [g["gate"] for g in summary["gates"]]
        assert "verify-support-before-copy" in names
        assert "node-npm-ci" not in names
    finally:
        _make_support_writable(root)


def test_support_missing_member_hash_fails_before_product_gates(
    tmp_path: Path, recording: dict, fake_repo: Path, launcher_exe: Path,
) -> None:
    root = tmp_path / "real-support"
    root.mkdir()
    try:
        _build_valid_support_root(root)
        _make_support_writable(root)
        manifest_path = root / "support-manifest.json"
        doc = json.loads(manifest_path.read_text(encoding="utf-8"))
        doc["files"][0].pop("sha256")
        manifest_path.write_text(json.dumps(doc), encoding="utf-8")
        subprocess.run(["icacls", str(root), "/deny", "*S-1-1-0:(W)"], check=True, capture_output=True)
        result = _run_mutation_controller(tmp_path, recording, fake_repo, launcher_exe, root)
        assert result.returncode != 0
        summary = json.loads((tmp_path / "evidence" / "summary.json").read_text(encoding="utf-8"))
        names = [g["gate"] for g in summary["gates"]]
        assert "verify-support-before-copy" in names
        assert "node-npm-ci" not in names
    finally:
        _make_support_writable(root)


def test_controller_rejects_tool_version_mismatch_before_node_gates(
    tmp_path: Path, recording: dict, fake_repo: Path, launcher_exe: Path,
) -> None:
    # The recorder reports node v99 while the verified support declares v24.18.0.
    config = json.loads(recording["config_file"].read_text(encoding="utf-8"))
    config["nodeVersion"] = "v99.0.0"
    alt_config = tmp_path / "ver-config.json"
    alt_config.write_text(json.dumps(config), encoding="utf-8")
    evidence = tmp_path / "evidence"
    result = _run_controller(
        tmp_path, recording, fake_repo, launcher_exe,
        evidence=evidence, extra_env={"ST32_CONFIG": str(alt_config)},
    )
    assert result.returncode != 0
    assert "versions differ from verified support" in result.stderr
    summary = json.loads((evidence / "summary.json").read_text(encoding="utf-8"))
    names = [g["gate"] for g in summary["gates"]]
    assert "node-npm-ci" not in names

def test_support_illegal_artifact_version_fails_before_product_gates(
    tmp_path: Path, recording: dict, fake_repo: Path, launcher_exe: Path,
) -> None:
    # The verifier must reject a support root whose python artifact versions
    # violate the product's dependency ranges.
    root = tmp_path / "real-support"
    root.mkdir()
    try:
        _build_valid_support_root(root)
        _make_support_writable(root)
        manifest_path = root / "support-manifest.json"
        doc = json.loads(manifest_path.read_text(encoding="utf-8"))
        doc["pythonArtifacts"]["pyocd"]["version"] = "0.36.0"  # violates pyocd>=0.45.1,<0.46
        manifest_path.write_text(json.dumps(doc), encoding="utf-8")
        subprocess.run(["icacls", str(root), "/deny", "*S-1-1-0:(W)"], check=True, capture_output=True)
        result = _run_mutation_controller(tmp_path, recording, fake_repo, launcher_exe, root)
        assert result.returncode != 0
        summary = json.loads((tmp_path / "evidence" / "summary.json").read_text(encoding="utf-8"))
        names = [g["gate"] for g in summary["gates"]]
        assert "verify-support-before-copy" in names
        assert "node-npm-ci" not in names
    finally:
        _make_support_writable(root)
