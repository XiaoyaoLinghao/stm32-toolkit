"""POST134-C: post-migration debug guidance on the public delivery routes.

The Keil delivery PLAN and a successful APPLY expose the same
``debugConfiguration`` object the read-only preflight already publishes, and
the readable ``followUp`` string is derived from that same helper.  These
tests use disposable synthetic fixtures only: no Git requirement, compiler,
probe, hardware, installation or external project is involved.
"""

from __future__ import annotations

import json
from pathlib import Path

from stm32_toolkit.cli import main as cli_main
from stm32_toolkit.debug_configuration import post_migration_debug_configuration
from stm32_toolkit.keil import inspect_keil
from stm32_toolkit.migration import plan_keil_delivery
from stm32_toolkit.workflows import preflight_keil_workflow

from test_independent_migration_workflow import (
    _destination,
    _registered_call,
    _source,
)

CONFIGURE_PLAN_COMMAND = (
    "stm32-toolkit project configure --project <project> "
    "--debug-backend pyocd --debug-target <pyocd-target> --dry-run --json"
)


def _assert_shared_debug(debug: object) -> None:
    """Assert the shared post-migration description on any public exposure."""
    expected = post_migration_debug_configuration()
    assert debug == expected
    assert debug["phase"] == "post-migration"
    assert debug["blocking"] is False
    assert debug["status"] == "needs-user-input"
    assert debug["missingFields"] == ["debug.backend", "debug.target"]
    assert debug["targetSupport"] == "not-checked"
    assert debug["hardwareVerified"] is False
    # No backend or target is inferred from the Keil project/device.
    assert debug["backend"] is None and debug["target"] is None

    joined = " ".join(debug["nextSteps"])
    # The existing paired configure PLAN command stays verbatim, then its
    # exact-plan APPLY.
    assert CONFIGURE_PLAN_COMMAND in joined
    assert "stm32_project_configure" in joined
    assert "--apply --json --plan-id <data.plan_id> --authorized" in joined
    # Bind the destination root first; the debug pair is recorded before any
    # build/flash identity exists.
    assert "outputRoot" in joined
    assert "before establishing build or flash identities" in joined
    # The empty launch.json is explained by the real handoff flow.
    assert "data.cortexDebugLaunch.configuration" in joined
    assert "launch.json" in joined
    assert "handoff-end" in joined


def _assert_derived_follow_up(debug: dict, follow_up: object) -> None:
    """The readable string stays a string and carries the same next steps."""
    assert isinstance(follow_up, str)
    assert follow_up
    for step in debug["nextSteps"]:
        assert step in follow_up


def test_preflight_and_delivery_expose_the_same_derived_guidance(
    tmp_path: Path,
) -> None:
    source = _source(tmp_path)
    destination = _destination(tmp_path)

    preflight = preflight_keil_workflow(source)
    assert preflight.ok is True, preflight.to_dict()
    preflight_debug = preflight.data["debugConfiguration"]
    _assert_shared_debug(preflight_debug)

    plan = plan_keil_delivery(source, destination, inspect_keil(source))
    preview = plan.to_dict()
    assert preview["debugConfiguration"] == preflight_debug
    _assert_shared_debug(preview["debugConfiguration"])
    _assert_derived_follow_up(preview["debugConfiguration"], preview["followUp"])
    # Presentation only: no plan-owned state changes.
    assert preview["configured"] is False
    assert preview["built"] is False
    assert preview["flashed"] is False
    assert not destination.exists()


def test_cli_plan_and_apply_propagate_the_shared_guidance(
    tmp_path: Path, capsys
) -> None:
    source = _source(tmp_path)
    destination = _destination(tmp_path)

    planned = cli_main([
        "keil", "convert", "--project", str(source),
        "--destination", str(destination), "--dry-run", "--json",
    ])
    assert planned == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["ok"] is True
    assert plan["data"]["built"] is False
    _assert_shared_debug(plan["data"]["debugConfiguration"])
    _assert_derived_follow_up(
        plan["data"]["debugConfiguration"], plan["data"]["followUp"]
    )

    applied = cli_main([
        "keil", "convert", "--project", str(source),
        "--destination", str(destination), "--apply",
        "--plan-id", plan["data"]["planId"], "--authorized", "--json",
    ])
    assert applied == 0
    result = json.loads(capsys.readouterr().out)
    assert result["ok"] is True
    assert result["data"]["configured"] is True
    assert result["data"]["built"] is False
    assert result["data"]["flashed"] is False
    _assert_shared_debug(result["data"]["debugConfiguration"])
    _assert_derived_follow_up(
        result["data"]["debugConfiguration"], result["data"]["followUp"]
    )
    # Both exposures send the identical derived object.
    assert result["data"]["debugConfiguration"] == plan["data"]["debugConfiguration"]


def test_registered_mcp_plan_and_apply_propagate_the_shared_guidance(
    tmp_path: Path,
) -> None:
    source = _source(tmp_path)
    destination = _destination(tmp_path)
    data_root = tmp_path / "plugin-data"

    plan = _registered_call(
        source,
        data_root,
        "stm32_keil_convert",
        {"destination": str(destination), "authorized": False},
    )
    assert plan["ok"] is True
    _assert_shared_debug(plan["data"]["debugConfiguration"])
    _assert_derived_follow_up(
        plan["data"]["debugConfiguration"], plan["data"]["followUp"]
    )

    applied = _registered_call(
        source,
        data_root,
        "stm32_keil_convert",
        {
            "destination": str(destination),
            "planId": plan["data"]["planId"],
            "authorized": True,
        },
    )
    assert applied["ok"] is True
    assert applied["data"]["outputRoot"] == str(destination)
    assert applied["data"]["built"] is False
    _assert_shared_debug(applied["data"]["debugConfiguration"])
    _assert_derived_follow_up(
        applied["data"]["debugConfiguration"], applied["data"]["followUp"]
    )
    assert (
        applied["data"]["debugConfiguration"]
        == plan["data"]["debugConfiguration"]
    )
