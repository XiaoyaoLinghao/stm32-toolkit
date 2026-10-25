# Diagnostic-tail bounded plan

Governing design: ../specs/2026-10-25-diagnostic-tail-design.md. Accepted base `99c93ccfb63b104aeb58ce23f8a78b9d98ddb932`. Ownership and boundaries follow design and AGENTS.md.

1. Claude reconciles skills/{migrate-keil,configure-stm32-project,build-firmware,setup-stm32-env}/SKILL.md and docs/user-guide.md at the affected paragraphs only. No production Python/parser/schema or global Skill changes. Preserve full diagnostics and authorization/provenance boundaries.
2. Add only missing public-behavior regressions in tools/stm32-toolkit/tests/test_keil_preflight.py and test_vscode_configuration.py; existing test_ai_call_guidance.py may be adjusted only for genuine changed guide contracts. No regex/prose-mirror-only new tests.
3. Coordinator commits product/tests to freeze CodeHead. Native PowerShell exact-command author verification is separate from file-only edits. Primary reviews entire base-to-CodeHead diff in clean independent tree and runs proportionate verification. Return corrections to Claude on this branch.
4. Validate four Skills and fresh read-only AI consumer decisions on doctor collection versus readiness, blocker PLAN/APPLY, invocation-scoped binding, scoped authorization, reserved linker prefix and managed/imported routes. No live tools or hardware in simulation. Record results and limitations; then integrate for whole-source regression/VS Code/release work.

Required suites: test_keil_preflight.py, test_vscode_configuration.py, test_ai_call_guidance.py, relevant doctor tests if guidance assertions depend on exact fields. Report any discovered source defect for a bounded scope amendment rather than changing it here. Reports record CodeHead before report commit. Do not claim acceptance for your own diff.
