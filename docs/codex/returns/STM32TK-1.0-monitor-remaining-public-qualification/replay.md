# Replay persisted-authority qualification

This return records the bounded Replay persisted-authority test preparation at
the approved Monitor qualification baseline. Production source, schemas,
dependencies, fixtures, and coverage configuration were unchanged. The
physical-publication cases use offline software fixtures and do not claim
hardware evidence.

## Ledger

- Accepted design/plan base: `a3609e92acce1d8efdedef68b1a26af950426ebd`
- Full implementation baseline: `87699308535bd36431c2e44be8bf131e245d460d`
- Test CodeHead before this report commit: `98ce299e67d1e41ca650d69faf973658a1d61f27`
- Branch: `codex/STM32TK-1.0-replay-authority-qualification`
- Implementer: `/root/monitor_replay_authority_impl` (bounded Luna/max test owner)
- Owned paths: `tools/stm32-monitor/tests/test_replay.py`,
  `tools/stm32-monitor/tests/test_physical_publication.py`, and this report

## Residual public variants

| Missing arc | Public trigger | Expected public result | State assertion |
| --- | --- | --- | --- |
| `replay.py:985-987`; malformed persisted `monitor-run-ref` root | `ingest_monitor_replay` reloads a stored root containing `{}` | `MonitorReplayError.code == EVIDENCE_INTEGRITY_FAILURE` | projected History and transcript root stay unchanged; malformed reference-root bytes remain the injected state |
| `replay.py:1110-1111`; transcript envelope differs from the expected envelope | `ingest_monitor_replay` reloads through an EvidenceStore envelope provider returning contradictory parents | `EVIDENCE_INTEGRITY_FAILURE` | History, transcript root bytes, and reference root bytes remain unchanged |
| `replay.py:1118-1119`; transcript artifact bytes differ from the authoritative raw transcript | `ingest_monitor_replay` reloads through an EvidenceStore artifact provider returning canonical bytes without the stored final LF | `EVIDENCE_INTEGRITY_FAILURE` | History and both authoritative root files remain unchanged |
| `replay.py:1209-1210`; transcript artifact descriptor differs from the expected digest | `ingest_monitor_replay` receives a provider `ArtifactRef` with a contradictory digest during transcript publication | `EVIDENCE_INTEGRITY_FAILURE` | no transcript/reference roots or History are adopted |
| `replay.py:1282-1283`; reference artifact descriptor differs from the expected digest | `ingest_monitor_replay` receives a contradictory provider `ArtifactRef` during reference publication | `EVIDENCE_INTEGRITY_FAILURE` | the valid transcript root may remain as the publication prefix; no reference root or History is adopted |
| `replay.py:2241-2242`; reloaded physical reference artifact names another operation | `load_monitor_run_reference` receives canonical provider bytes with a valid but different operation and recomputed digest | `EVIDENCE_INTEGRITY_FAILURE` | persisted transcript/reference root bytes remain unchanged |
| `replay.py:2243-2244`; persisted physical reference-root metadata contradicts the authenticated reference | `load_monitor_run_reference` reads a root whose `run_ref_sha256` metadata is changed on disk | `EVIDENCE_INTEGRITY_FAILURE` | the injected reference-root bytes and untouched transcript-root bytes remain present |
| `replay.py:2253-2258`; physical transcript envelope structure contradicts the persisted graph | `load_monitor_run_reference` receives a provider envelope with an unexpected parent | `EVIDENCE_INTEGRITY_FAILURE` | both persisted root files remain unchanged |

The additions deliberately do not repeat accepted retry, cursor, History
window, race, or direct provider-I/O failure variants. No coverage gain or
release acceptance is claimed before the primary-owned selected-node run.

## Verification

Status: `NOT_RUN`.

The specified Python performed AST parsing only for both owned test files and
returned `AST_OK`. `git diff --check` also passed. Pytest, collect-only,
package imports, builds, installers, hardware access, cleanup, and remote
actions were not performed in this wave.
