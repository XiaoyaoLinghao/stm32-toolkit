# Memory margin implementation plan

Governing design: ../specs/2026-10-25-memory-margin-design.md. Accepted base: 1b16a38181770569cf1d0f533a73e94690231a32. Source/ownership and boundaries as design.

1. Implement a small typed summary helper integrated with build model, identity schema/semantic validator, runner evidence and existing current-build admission. Review all identity readers; preserve optional old contracts.
2. Add focused tests in tools/stm32-toolkit/tests/test_memory_margin.py plus necessary existing affected tests. No production wrappers/CI/automation added.
3. Update user guide and build-firmware Skill with warning consumption and limitations. Do not update history or claim release complete.
4. Coordinator freezes CodeHead; author CLI runs focused and relevant regression commands supplied exactly; primary independently reviews and verifies at exact clean CodeHead. Correct issues on same branch and recheck only affected checks. Record test result/environment/source identity and limitations under docs/codex/returns/MEMORY-MARGIN. Commit report separately.

Allowed source: tools/stm32-toolkit/src/stm32_toolkit/build/{model.py,identity.py,runner.py,memory_margin.py}, schemas/firmware-identity.schema.json and packaged copy; existing current-build verification in probe/flash.py only if required by summary validation; test_memory_margin.py and genuinely affected build/map/identity tests; docs/user-guide.md; skills/build-firmware/SKILL.md. Request coordinator scope repair before unrelated edits. Do not edit this design/plan, AGENTS.md, version/release policy, original firmware or hardware drivers.

## Overall next phases

After acceptance: audit diagnostic tails against VS Code blind-test findings (including newlib specs and route guidance); fix actual remaining issues via separately bounded Claude slices. Then clean-head full software/coverage/UI/isolated VS Code checks with honest platform and hardware status; unify v1.3.1 versions, construct two reproducible release builds and isolated installation checks, review release evidence/assets, publish user-requested v1.3.1 only under applicable qualification/explicit exception. No inherited v1.2 exception. Primary owns final acceptance and source/artifact identity. User original project remains untouched.
