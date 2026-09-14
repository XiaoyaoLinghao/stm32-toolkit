# D3 before-fixture physical observation passed

User authorized one 30-second, 100 ms Monitor observation with "开始进行" after the explicit bounded request. The primary executed the existing reviewed entry once, without firmware edits, building, deployment, programming or retry. Existing implementation evidence was reused. No remote action occurred.

PID 30088 completed in 71,813 ms, exit 0, below the 120-second outer budget. The actual sampling window was 30,000.6378 ms by the monotonic clock. Functional and existing performance gates both returned PASS.

| Evidence | Actual result |
| --- | --- |
| Complete correlated batches | 300; invalid 0; 10.0 Hz |
| testtime | 300 successful typed reads; 102 distinct values |
| GPIOE.ODR PE3 / D3 | 300 successful samples; values {0}, expected held-on active-low fixture |
| GPIOE.ODR PE4 / D4 | 300 successful samples; values {0,1} |
| Adjacent capture intervals | P95 101.8052 ms; P99 103.5901 ms; maximum 155.7186 ms |
| Deadline/history/service/subscriber drops | All zero |
| Scheduled-to-captured delay | P95 26.9295 ms; maximum 80.0607 ms |
| Cleanup | sampling stopped, probe released, runtime stopped; released registry; owned process and debugger consumers absent |

This supports running timer/D4 activity with PE3 held low during the current observation window. It complements the user's prior D3-on/D4-blinking observation. It does not reconstruct which branch of the earlier combined `timer-or-pe3` assertion failed, prove every interval was exactly 100 ms, or complete T10/VS10-A. Continuous sampling used the unchanged accepted OBSERVE path; connection lifecycle and sampling are separate. No additional post-close CPU read was performed. User post-window LED confirmation has been requested and is pending.

## Identity and retained evidence

- Toolkit runtime source `6250ef14035c053caa5ddc98c072c4be5b5e3650`; explicit candidate Python at `D:\stm32tk-data\fault-controlled-20260911\candidates\lockup-20260914\runtime\0.9.0\Scripts\python.exe`; original business DataRoot retained.
- Firmware HEAD `8755ba8fd0c678f32d7d23e7d827e84317026429`, build `96e92552c24c1351588d44df5a97f6402b2740294366b8a49f1d879a053f71ea`, ELF `52b8e8a0bf474186d2d279efc416c944737d2931e2a859740f3b0d23ed254dff`; source snapshot `97b4eef84dbbbe5a1f36dae26f2dd7988ba813079b41f7eec80000bd6ac6e6bc`.
- Workspace `d7b137149685154d159f2f0ded85852248e4a2de1fe2813a788aa9bb54c2fd74`; observation and flash session `vs10a-t10-d3-20260914-01`; actual lease `lease-8adfb28e758f48759ce46b91594d85f6` is released.
- Monitor run `6a8508ee-95ec-43f0-a638-73d37d7038c5`; group `591320e7-f85f-4d60-bab7-c9d3f869fd1a`, revision 1; original sequences [0,300), untrimmed, publication reference READY. READY is not a completed T10 publication or FixVerification.
- Result `D:\codex-tmp\t10-d3-20260914\entries\failed-before\result.json`, SHA256 `826d75ca3b76aefaacc44382137122e390e9372859b47e0b2be2baee98c66da6`.
- Original JSONL export alongside result: `history-8fba7bd0-50b4-46b0-96ed-7b9c51d63361.jsonl`, 962,273 bytes, SHA256 `c7fd97d0a80ac8d1e921aa3d37345159d10ec73f2651162659d05af9c48c9056`.
- Invocation card, argv, stdout/stderr, PID, exit/timing and before/after registry/consumer snapshots: `D:\codex-tmp\t10-d3-lineage-20260914`. Preserve the consumed marker and original data for later acceptance; run temp is empty.

The existing failed physical TestRun and Diagnostic from the [offline continuation](2026-09-14-stm32tk-t10-d3-diagnostic-lineage.md) remain unchanged. Next is the approved exact P4 source correction, matching rebuild and separately authorized physical verification, followed by Diagnostic/FixVerification and acceptance lineage completion. No fresh expiring attempt was started to wait on that work. Historical accepted evidence remains valid within its original scope.
