"""Pure-stdlib deterministic release-surface verifier for STM32TK-0502.

Three subcommands, no network/process/checkout behavior:

- ``scope``     Validates the exhaustive no-renames ``acceptedBase..CodeHead``
                inventory: every changed path must be an allowed release surface,
                required active release surfaces must be present, and no changed
                active product file may contain a forbidden 0.6 term.
- ``coverage``  Maps every changed product ``.py`` file to exactly one row across
                the supplied coverage JSON documents and enforces branch
                coverage >= 90% from integer counts.
- ``static``    Validates the committed ``ui_dist`` manifest closure, the eight
                active Skills, and required active docs/marketplace presence.

Support-root verification is NOT this tool's job; the authoritative verifier is
``tools/stm32-monitor/ui/tests/verify_support.py`` (Task 1).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REQUIRED_ACTIVE = {
    ".claude-plugin/plugin.json",
    ".claude-plugin/marketplace.json",
    "README.md",
    "README_zh-CN.md",
    "bin/setup-stm32-env.ps1",
    "bin/stm32-monitor.cmd",
    "bin/stm32-toolkit-mcp.cmd",
    "skills/setup-stm32-env/SKILL.md",
    "skills/stm32-monitor/SKILL.md",
    "docs/superpowers/plans/2026-08-04-stm32-toolkit-0.5-0.6-monitor-test-diagnostics.md",
    "docs/superpowers/plans/2026-08-04-stm32-toolkit-complete-development-roadmap.md",
    "docs/superpowers/specs/2026-08-10-stm32tk-0502-lean-monitor-ui-design.md",
    "docs/superpowers/plans/2026-08-10-stm32tk-0502-lean-monitor-ui.md",
    "docs/superpowers/plans/2026-08-10-stm32tk-0502-frontend-core.md",
    "docs/superpowers/plans/2026-08-10-stm32tk-0502-runtime-release.md",
    "docs/superpowers/plans/2026-08-10-stm32tk-0502-browser-evidence.md",
    "docs/superpowers/plans/2026-08-10-stm32tk-0502-monitor-ui-release-rewrite.md",
}
REQUIRED_REFERENCES = {
    "docs/superpowers/plans/2026-08-04-stm32-toolkit-complete-development-roadmap.md": (
        "../specs/2026-08-10-stm32tk-0502-lean-monitor-ui-design.md",
    ),
    "docs/superpowers/plans/2026-08-04-stm32-toolkit-0.5-0.6-monitor-test-diagnostics.md": (
        "docs/superpowers/specs/2026-08-10-stm32tk-0502-lean-monitor-ui-design.md",
    ),
    "docs/superpowers/plans/2026-08-10-stm32tk-0502-lean-monitor-ui.md": (
        "docs/superpowers/plans/2026-08-10-stm32tk-0502-monitor-ui-release-rewrite.md",
    ),
    "docs/superpowers/plans/2026-08-10-stm32tk-0502-frontend-core.md": (
        "docs/superpowers/plans/2026-08-10-stm32tk-0502-monitor-ui-release-rewrite.md",
    ),
    "docs/superpowers/plans/2026-08-10-stm32tk-0502-runtime-release.md": (
        "docs/superpowers/plans/2026-08-10-stm32tk-0502-monitor-ui-release-rewrite.md",
    ),
    "docs/superpowers/plans/2026-08-10-stm32tk-0502-browser-evidence.md": (
        "docs/superpowers/plans/2026-08-10-stm32tk-0502-monitor-ui-release-rewrite.md",
    ),
    "docs/superpowers/plans/2026-08-10-stm32tk-0502-monitor-ui-release-rewrite.md": (
        "docs/superpowers/specs/2026-08-10-stm32tk-0502-lean-monitor-ui-design.md",
    ),
}
# Report path is a legitimate tracked release surface (report-only commits).
SPECIAL_ALLOWED = {
    ".gitignore",
    ".gitattributes",
    "tools/stm32-monitor/pyproject.toml",
    "tools/stm32-toolkit/pyproject.toml",
    "docs/codex/returns/STM32TK-0502-MONITOR-UI-RELEASE/implementation-report.md",
}
PREFIXES = (
    "tools/stm32-monitor/ui/",
    "tools/stm32-monitor/src/stm32_monitor/",
    "tools/stm32-monitor/tests/",
    "tools/stm32-toolkit/src/stm32_toolkit/",
    "tools/stm32-toolkit/tests/",
    "tools/release/",
)
SKILLS = {
    "setup-stm32-env",
    "migrate-keil",
    "configure-stm32-project",
    "build-firmware",
    "flash-firmware",
    "debug-firmware",
    "read-var",
    "stm32-monitor",
}
FORBIDDEN = (
    "host-target test",
    "diagnostic hypothesis",
    "quality dashboard",
    "annotation bookmark",
    "cross-run comparison",
)
_BINARY_SUFFIXES = {".png", ".ico", ".woff", ".woff2"}


def _read(path: Path) -> object:
    return json.loads(path.read_text("utf-8"))


def _changed_files(rows: object) -> list[dict[str, object]]:
    if not isinstance(rows, list):
        raise SystemExit("inventory JSON must be a list")
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("path"), str):
            raise SystemExit("inventory row is malformed")
    return rows  # type: ignore[return-value]


def scope(args: argparse.Namespace) -> None:
    repo = Path(args.repo).resolve(strict=True)
    rows = _changed_files(_read(Path(args.inventory)))
    active_paths = {row["path"] for row in rows if row["status"] != "D"}
    for row in rows:
        path = row["path"]
        status = row["status"]
        if status not in {"A", "M", "D"}:
            raise SystemExit(f"inventory status is not A/M/D: {path}")
        allowed = (
            path in REQUIRED_ACTIVE
            or path in SPECIAL_ALLOWED
            or path.startswith(PREFIXES)
        )
        if not allowed:
            raise SystemExit(f"out-of-scope changed path: {path}")
    if not REQUIRED_ACTIVE <= active_paths:
        raise SystemExit(
            "required active release surface missing from inventory: "
            + ", ".join(sorted(REQUIRED_ACTIVE - active_paths))
        )
    for row in rows:
        name = row["path"]
        if row["status"] == "D":
            continue
        if not (
            name.startswith("tools/stm32-monitor/src/")
            or name.startswith("tools/stm32-toolkit/src/")
            or name.startswith("tools/stm32-monitor/ui/src/")
            or name.startswith("skills/")
        ):
            continue
        full = repo / name
        if not full.is_file() or Path(name).suffix.casefold() in _BINARY_SUFFIXES:
            continue
        text = full.read_text("utf-8", errors="strict").casefold()
        if any(term in text for term in FORBIDDEN):
            raise SystemExit(f"0.6 implementation term in active product: {name}")


def coverage(args: argparse.Namespace) -> None:
    repo = Path(args.repo).resolve(strict=True)
    rows = _changed_files(_read(Path(args.inventory)))
    documents = [_read(Path(name)) for name in args.coverage]
    records: dict[str, list[object]] = {}
    for document in documents:
        if not isinstance(document, dict) or not isinstance(document.get("files"), dict):
            raise SystemExit("coverage JSON is malformed")
        for name, value in document["files"].items():
            records.setdefault(str(Path(name).resolve()).casefold(), []).append(value)
    changed: list[tuple[Path, str]] = []
    for row in rows:
        path = row["path"]
        if row["status"] != "D" and path.endswith(".py") and (
            path.startswith("tools/stm32-monitor/src/stm32_monitor/")
            or path.startswith("tools/stm32-toolkit/src/stm32_toolkit/")
        ):
            changed.append((repo / path, path))
    if not changed:
        print("coverage: no changed product python files")
        return
    for path, rel in changed:
        found = records.get(str(path.resolve(strict=True)).casefold(), [])
        if len(found) != 1:
            raise SystemExit(
                f"changed product coverage row count is {len(found)}: {rel}"
            )
        summary = found[0].get("summary")
        if not isinstance(summary, dict):
            raise SystemExit(f"coverage summary is missing: {rel}")
        try:
            total = int(summary["num_branches"])
            covered = int(summary["covered_branches"])
        except (KeyError, TypeError, ValueError):
            raise SystemExit(f"coverage branch counts are not integers: {rel}") from None
        if total < 0 or covered < 0 or covered > total:
            raise SystemExit(f"invalid branch counts: {rel}")
        percent = 100.0 if total == 0 else covered * 100.0 / total
        if percent < 90.0:
            raise SystemExit(
                f"changed product branch coverage below 90: {rel} ({percent:.1f}%)"
            )
    print(f"coverage: {len(changed)} changed product file(s) >= 90% branch")


def static(args: argparse.Namespace) -> None:
    repo = Path(args.repo).resolve(strict=True)
    dist = repo / "tools" / "stm32-monitor" / "src" / "stm32_monitor" / "ui_dist"
    manifest_path = dist / ".vite" / "manifest.json"
    if not manifest_path.is_file():
        raise SystemExit("ui_dist .vite/manifest.json is missing")
    manifest = _read(manifest_path)
    wanted = {"index.html", ".vite/manifest.json"}

    def visit(value: object) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key in {"file", "css", "assets"}:
                    visit(item)
                elif key in {"imports", "dynamicImports"}:
                    continue
                elif isinstance(item, (dict, list)):
                    visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)
        elif isinstance(value, str):
            wanted.add(value)

    visit(manifest)
    actual = {path.relative_to(dist).as_posix() for path in dist.rglob("*") if path.is_file()}
    if actual != wanted:
        missing = sorted(wanted - actual)
        extra = sorted(actual - wanted)
        raise SystemExit(
            "static manifest closure differs from tracked assets"
            + (f"; missing={missing}" if missing else "")
            + (f"; extra={extra}" if extra else "")
        )
    active = {path.parent.name for path in (repo / "skills").glob("*/SKILL.md")}
    if active != SKILLS:
        raise SystemExit(
            "active Skill set differs from release contract: "
            + ", ".join(sorted(SKILLS ^ active))
        )
    rows = _changed_files(_read(Path(args.inventory)))
    inventory = {row["path"] for row in rows if row["status"] != "D"}
    if not REQUIRED_ACTIVE <= inventory:
        raise SystemExit("active docs/marketplace are absent from inventory")
    missing_files = sorted(
        path
        for path in REQUIRED_ACTIVE
        if not (repo / path).is_file() or (repo / path).is_symlink()
    )
    if missing_files:
        raise SystemExit(
            "active release surface is missing or not a regular file: "
            + ", ".join(missing_files)
        )
    for path, references in REQUIRED_REFERENCES.items():
        text = (repo / path).read_text("utf-8", errors="strict")
        for reference in references:
            if reference not in text:
                raise SystemExit(
                    f"required release-document reference is missing from {path}: "
                    f"{reference}"
                )
    print("static: manifest closure, eight Skills, and active surfaces OK")


def main() -> None:
    parser = argparse.ArgumentParser(prog="verify_0502_release.py")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("scope")
    p.add_argument("--repo", required=True)
    p.add_argument("--inventory", required=True)
    p.set_defaults(run=scope)
    p = sub.add_parser("coverage")
    p.add_argument("--repo", required=True)
    p.add_argument("--inventory", required=True)
    p.add_argument("--coverage", action="append", required=True)
    p.set_defaults(run=coverage)
    p = sub.add_parser("static")
    p.add_argument("--repo", required=True)
    p.add_argument("--inventory", required=True)
    p.set_defaults(run=static)
    args = parser.parse_args()
    args.run(args)


if __name__ == "__main__":
    try:
        main()
    except SystemExit as exc:
        raise exc
    except Exception as exc:  # pragma: no cover - defensive boundary
        print(f"verify_0502_release.py: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
