"""Compatibility owner for the original 0502 release-helper test path.

The final release rewrite expanded the helper into the fail-closed controller
suite in ``test_0502_release_gate_controller.py``.  Keep the original audited
path committed and prove that the renamed suite still owns its required static,
recording, fail-fast, inventory, and support-integrity contracts.  Pytest also
collects that controller module independently in the same Toolkit inventory.
"""

from __future__ import annotations

import ast
from pathlib import Path


CONTROLLER_TEST = Path(__file__).with_name("test_0502_release_gate_controller.py")


def test_original_release_helper_contract_is_owned_by_the_controller_suite() -> None:
    tree = ast.parse(CONTROLLER_TEST.read_text(encoding="utf-8"))
    test_names = {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    }
    assert {
        "test_controller_parses_and_declares_exact_parameters",
        "test_controller_has_no_ambient_tool_or_remote_verbs",
        "test_full_success_path_recording",
        "test_fail_fast_stops_at_first_failure",
        "test_authoritative_0502_document_set_is_required",
        "test_support_reverified_before_after_copy_each_npm_phase_and_final",
    } <= test_names


def test_original_release_helper_path_points_at_the_committed_controller() -> None:
    assert CONTROLLER_TEST.is_file()
    source = CONTROLLER_TEST.read_text(encoding="utf-8")
    assert "run_0502_windows_gates.ps1" in source
    assert "STM32_0502_TEST_POWERSHELL" in source
