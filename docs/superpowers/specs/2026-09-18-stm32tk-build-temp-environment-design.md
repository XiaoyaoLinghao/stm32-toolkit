# Release build child temporary environment

Accepted base: `822b705b53da958aca4fa4420c6fdc39b21f7c60`. Primary owns this bounded prerequisite to final VS10-A deployment; Luna/max implements, primary independently reviews. Current user goal authorizes related local repairs and deployment. No remote action.

Two runnable scenarios: when the release caller sets `TMPDIR`, `TEMP` and `TMP` to its approved run directory, the product-wheel subprocess receives their exact values; when any variable is absent, the subprocess does not invent a replacement for it. Existing `PATH`, `PYTHONNOUSERSITE=1` and `SOURCE_DATE_EPOCH` behavior remains intact.

Verified cause: `tools/release/build_0900_artifacts.py:_build_wheel` passes an explicit three-key environment to `_process`, which passes that mapping directly to subprocess.run. The temporary variables configured by the caller are therefore dropped before pip wheel. This is a child-environment propagation defect; the current final build stopped earlier at missing closed build-backend input, before dispatching that wheel process. Prior spill attribution remains unproven.

Only extend that subprocess environment with the three temporary variables when present in the caller. Update the frozen utility SHA in `bin/setup-stm32-env.ps1` to the exact committed utility bytes. Reuse existing release artifact test seams to capture the production `_build_wheel` subprocess environment, covering present and absent variables and unchanged build flags. No dependency upgrades, new command, generic process wrapper, installer behavior change, public schema or hardware change. Do not edit the release policy hash.

Verification: meaningful RED/GREEN for child environment propagation, existing archive trust-anchor checks, and the already planned one final bundle/Bootstrap/Check. Do not run a release matrix or hardware retest solely for this change. Build inputs must separately use the existing complete closed wheelhouse; process-scoped Git `core.autocrlf=false` and `core.eol=lf` prevent the independently identified archive-line-ending mismatch.
