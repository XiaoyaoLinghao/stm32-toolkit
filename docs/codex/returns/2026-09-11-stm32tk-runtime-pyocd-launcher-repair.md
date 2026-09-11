# PyOCD final-path launcher repair

Status: **ACCEPTED (installer correction and offline local repair)**. T9, T10 and VS10-A remain incomplete; no new hardware or IDE retry occurred.

Accepted base: `cdeee36261ff6977dcb07971a583d1f44a1e732f`. Luna/max implementation: `9a8ac0cccd8890864712401fdc5fb4a0fd40372c`; final test coverage head: `f722c0dec8ca2d435eae52522ffdc89d98cd84ee`. Integrated code head before this report: `b6fadba2c809889645c4729c5e7e4392733f6736`. Primary independently reviewed the complete base-to-final diff in a clean worktree at the exact returned head. Deployment/SOP documentation and its version-range clarification were independently accepted by the separate reviewer.

## Cause and correction

The old setup created PyOCD's executable in staging, moved that venv, then regenerated only Toolkit/Monitor launchers. Both final launcher records and healthy checks omitted PyOCD. The configured real pyocd.exe retained a missing staging interpreter at byte offset 108032 and failed `--version`; final Python's module invocation succeeded. This is a deployment artifact defect, not evidence of a target-board defect. The original IDE child stderr/time chain remains unavailable; see the [T9 failure record](2026-09-11-stm32tk-1001-t9-ide-attempt-06.md).

Only `bin/setup-stm32-env.ps1` and its existing setup test module changed as product implementation. The existing verified wheel selection now includes pinned PyOCD, and finalization regenerates its launcher before healthy state publication. Final-path binding and real executable version checks cover PyOCD. Bootstrap/Repair require the release pin; Check preserves the supported installed-module range and requires the executable version to agree with it. Existing rollback, integrity checks and no-index/no-deps behavior remain in place.

## Evidence

- Owner regression RED reproduced the stale PyOCD binding; focused GREEN and six affected regressions passed. The complete setup module passed 35 tests, exit 0, at `9a8ac0cc`. The final test-only increment parameterized the existing stale launcher Check test for Toolkit/PyOCD: two cases passed, exit 0, including unchanged DataRoot/ProjectRoot snapshots. The unchanged 35-case evidence is reused; no second full-module run is claimed.
- Owner PowerShell parse, Python compile and diff checks passed. Primary full diff and diff check passed; the existing production binding function independently rejected the actual broken runtime with `pyocd launcher is not bound to the final runtime interpreter` before repair.
- Test evidence: `D:\codex-tmp\stm32tk-pyocd-launcher-fix-20260911`. Disposable owner basetemp/cache/pycache outputs were cleaned; concise RED/GREEN/module logs retained.

## Bounded local repair

User authorization was “开始修正吧”. No active Python/PyOCD/GDB runtime consumer was present immediately before mutation. The current runtime's retained PyOCD wheel was checked against the manifest whose hash matches runtime-state, including exact version, size and SHA256 `bf3f35d62620f8a0838cd1b2d8c6555308073165093684663c4c1921dae73b30`. A package/metadata/launcher rollback copy was saved first.

Using the reviewed script's existing bounded process function, final runtime Python performed one offline, no-deps, no-cache, force reinstall of that same PyOCD wheel only. No Toolkit/Monitor reinstallation, full Repair, candidate rebuild or runtime-state rewrite occurred. Both PyOCD wheel launchers now bind to final Python with no staging reference; only the main pyocd.exe version entry was executed, not legacy gdbserver or any hardware command.

Real pyocd.exe and `python -I -m pyocd --version` both returned 0 / `0.45.1`. Main launcher SHA256 changed from `02751dac411be2c3b89d8f6607a6d3c742208bc2f7be3194cc8461bfd022698d` to `a1363c96f19841e6c7991ce6188baa434e8f9ea1497f19a8290fdcf643eb2d70`. All 344 existing PyOCD Python source files matched their pre-repair hashes, as did runtime-state, ELF, flash receipt, handoff state and registry reservation. Product source remains `5f036363383e6c85cc87426da1b4a1c20dfe7acc`; this local correction is not a newly packaged product deployment.

Live evidence: `D:\codex-tmp\stm32tk-pyocd-launcher-live-repair-20260911` (`before.json`, wheel/manifest pins, `backup.json`, `review-before-binding.json`, `reinstall-result.json`, `after.json`). Rollback and minimum diagnosis evidence remain retained. Original IDE attempt 07 remains terminally stopped and externally-owned; no duplicate begin, end/reacquire, flash, read or hardware retry occurred.

Cleanup of this live-repair run's `tmp` directory was rejected by automatic approval with `blocked by policy` and no more specific reason. The directory is retained, recorded in `cleanup.json`; no alternate deletion method was attempted. This does not invalidate the completed offline verification.

## Deployment handoff

The [maintained deployment and IDE preflight](../../testing/windows-deployment-and-ide-preflight.md) consolidates the real launcher, cwd, task, CLI argument, IDE startup, archive EOL and build-wheelhouse failures with evidence limits and preventive checks. README, setup skill and standard test procedure link it. Future distributions must be built from reviewed corrected source under the existing release/version contract: old extracted bundles do not update themselves. Original generated IDE configuration compatibility and real attach/detach/reacquire acceptance remain open; neither this software verdict nor the offline repair closes them.
