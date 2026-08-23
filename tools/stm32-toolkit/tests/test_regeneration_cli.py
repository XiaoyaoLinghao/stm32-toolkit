from __future__ import annotations

from stm32_toolkit.cli import _build_parser, _validate_cli_modes


def test_regeneration_cli_commands_have_closed_arguments():
    parser = _build_parser()
    plan = parser.parse_args(["project", "regenerate-plan", "--project-root", ".", "--destination", "generated", "--json"])
    assert plan.project_command == "regenerate-plan"
    prepare = parser.parse_args([
        "project", "regenerate-prepare", "--project-root", ".", "--destination", "generated",
        "--plan-id", "a" * 64, "--action-digest", "b" * 64, "--authorized", "--json",
    ])
    assert prepare.authorized is True
    apply = parser.parse_args([
        "project", "regenerate-apply", "--project-root", ".", "--authorization-digest", "c" * 64,
        "--authorized", "--json",
    ])
    assert apply.project_command == "regenerate-apply"
