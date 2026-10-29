# PYOCD046-HID: one-file SDK-origin portability correction

Status **AUTHORIZED / ONE EDIT CALL PENDING** on2026-10-29.
The human explicitly approved this single-file correction and separate offline
verification. No other file is writable; errors/scope deviations stop, no retry.
Accepted origin62bede1d55a513f3dfd8d634b2d3116b0de41890;
reviewed CodeHead3e19dd55af87655326f29b85a5bf92a392ded68d.
Primary owns requirements/orchestration/complete-diff review/acceptance. Local
Claude Code CLI owns code/tests using the unchanged configured route. Both
authorized edit calls A/B completed normally and are consumed; the new explicit
single-file authority is separate and does not renew those allowances.

Sole proposed write: tools/stm32-toolkit/tests/test_pyocd_hid_timeout.py.
SELECTED_SITE_MARKER and the collection assertion at lines39,61–65 require the
literal directory name candidate-site. A correct0.46.0 wheel under normal
.venv/Lib/site-packages fails before tests run. Current502/502 passes and8
independent passes used the prepared directory with that name; they cannot
waive this source finding.

Replace the temporary-directory convention with actual distribution metadata
version and loaded SDK package/module-origin correspondence. Preserve exact
policy pins/installed0.46.0 checks, the Windows contract,10000ms finite timeout
and four real-SDK/fake-device behaviors. No copied SDK read function, weakened
identity, version/backend fallback, SDK change or new installation. Standard
library importlib.metadata distribution.version/locate_file are available;
Primary reviewed the actual implementation and selected paths offline.

Add focused guard coverage: a consistent synthetic ordinary site-packages path
is admitted; module/distribution mismatch is rejected. This is metadata-only
guard testing; original cases still call real HidApiUSB.read with fake device,
without hardware APIs. Clarify the docstring's import versus hardware-I/O claim.
Preserve every other file and the four behavioral assertions.

One edit call through shared dispatch.py; only this file is writable and reads
stay within this isolated repository. Primary supplies current exact clean HEAD,
verified EXISTING target and applicable instructions/API facts. No new-file
discovery or expired absence/Edit-context exception. No shell/tests/install/
hardware/remote action during edit. Errors/refusals/scope violations stop; no
automatic retry or Codex implementation fallback.

After native write audit, freeze CodeHead and review the complete base-to-head
diff in a clean tree. Separate exact-command verification runs every changed
HID/guard case; Primary independently verifies the relevant risks. Preserve the
502-case evidence at its original commit/owner. Reuse only checks with exact
unchanged relevant source/SDK/test/environment and no unresolved dependency
concern; otherwise rerun the affected check. Fresh/reused evidence stays separate,
with no relabeling of old execution as later-head execution.

No existing-runtime replacement, new SDK installation, physical operation,
packaging, push or publishing. SDK10s versus service5s remains disclosed;
physical responsiveness and the ordered goal are still pending.
