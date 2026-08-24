from __future__ import annotations

from types import MappingProxyType
from typing import Final

from stm32_toolkit import __version__


TOOLKIT_VERSION: Final = __version__
REQUIRED_PYTHON: Final = ">=3.12,<3.13"
SUPPORTED_PYTHON: Final = (3, 12)

MCP_TOOL_NAMES = MappingProxyType(
    {
        "doctor": "stm32_doctor",
        "project_detect": "stm32_project_detect",
        "project_context": "stm32_project_context",
        "project_create_plan": "stm32_project_create_plan",
        "project_create_prepare": "stm32_project_create_prepare",
        "project_create_apply": "stm32_project_create_apply",
        "project_regenerate_plan": "stm32_project_regenerate_plan",
        "project_regenerate_prepare": "stm32_project_regenerate_prepare",
        "project_regenerate_apply": "stm32_project_regenerate_apply",
        "keil_inspect": "stm32_keil_inspect",
        "keil_convert": "stm32_keil_convert",
        "project_configure": "stm32_project_configure",
        "build": "stm32_build",
        "probe_list": "stm32_probe_list",
        "flash": "stm32_flash",
        "debug_handoff_begin": "stm32_debug_handoff_begin",
        "debug_handoff_end": "stm32_debug_handoff_end",
        "variable_read": "stm32_variable_read",
        "variable_sample": "stm32_variable_sample",
        "register_read": "stm32_register_read",
        "fault_analyze": "stm32_fault_analyze",
        "diagnostic_start": "stm32_diagnostic_start",
        "diagnostic_show": "stm32_diagnostic_show",
        "diagnostic_begin": "stm32_diagnostic_begin",
        "diagnostic_hypothesis_add": "stm32_diagnostic_hypothesis_add",
        "diagnostic_hypothesis_assess": "stm32_diagnostic_hypothesis_assess",
        "diagnostic_plan_add": "stm32_diagnostic_plan_add",
        "diagnostic_plan_run": "stm32_diagnostic_plan_run",
        "test_target_replay": "stm32_test_target_replay",
        "diagnostic_source_change_declare": "stm32_diagnostic_source_change_declare",
        "diagnostic_verification_plan_add": "stm32_diagnostic_verification_plan_add",
        "diagnostic_verification_start": "stm32_diagnostic_verification_start",
        "diagnostic_marker_attach": "stm32_diagnostic_marker_attach",
        "diagnostic_verification_complete": "stm32_diagnostic_verification_complete",
        "diagnostic_verification_show": "stm32_diagnostic_verification_show",
        "test_host_discover": "stm32_test_host_discover",
        "test_host_run": "stm32_test_host_run",
        "test_show": "stm32_test_show",
        "test_target_prepare": "stm32_test_target_prepare",
        "test_target_execute": "stm32_test_target_execute",
        "acceptance_scenario_describe": "stm32_acceptance_scenario_describe",
        "acceptance_scenario_record": "stm32_acceptance_scenario_record",
        "acceptance_scenario_show": "stm32_acceptance_scenario_show",
        "acceptance_attempt_begin": "stm32_acceptance_attempt_begin",
        "acceptance_attempt_checkpoint": "stm32_acceptance_attempt_checkpoint",
        "acceptance_attempt_authorize_source_change": "stm32_acceptance_attempt_authorize_source_change",
        "acceptance_attempt_show": "stm32_acceptance_attempt_show",
        "acceptance_attempt_resume": "stm32_acceptance_attempt_resume",
    }
)

SKILL_NAMES: Final = (
    "setup-stm32-env",
    "migrate-keil",
    "configure-stm32-project",
    "build-firmware",
    "flash-firmware",
    "debug-firmware",
    "read-var",
    "stm32-monitor",
)
