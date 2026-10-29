# FLASH-DEFAULT-100KHZ — ordinary flashing policy

Accepted base: `4fe1be23d7b2c8a282757e1b8b45f73ee3484043`.
User explicitly authorizes normal flash default 100 kHz, removal of 1 MHz as a
flash requirement/acceptance gate, and corresponding design/guidance/tests, with
local Claude Code CLI implementation and Primary independent review. Primary
owns this specification, orchestration and acceptance. Branch:
`codex/v135-flash-default-100k`. No hardware, installation, packaging, version bump,
remote mutation or publication is authorized. Planned release remains Unreleased
v1.3.5; existing source version metadata remains 1.3.4 until release alignment.

## Public behavior and scope

1. Set the shared production `ProbeWorkerConfig` and direct `PyOCDBackend`
   constructor defaults to exactly `100_000` Hz. This ensures normal managed
   flash, normal imported flash and normal Target programming do not inherit the
   former faster default. Shared callers also inherit this lower default; no
   connection policy or control behavior changes. Existing Monitor/observation
   and under-reset profiles already select 100 kHz and retain their policies.
2. Omitted CLI `--frequency` and MCP `frequencyHz` remain represented as None/null.
   Omission preserves an explicitly supplied private worker configuration; the
   production default configuration is now 100 kHz. Do not replace deliberate
   injected configurations or mutate shared objects. Keep strict integer range
   100000..50000000, existing precedence, duplicate/type/range errors and explicit
   frequency overrides. A user may explicitly choose a supported faster value;
   1 MHz is an optional configuration, never a mandatory physical gate.
3. Normal 100 kHz remains normal: no under-reset selection, recovery fallback,
   reconnect, retry or additional enumeration/read/control is introduced. Keep
   normal SYSRESETREQ pre-program reset-and-halt and HALTED confirmation;
   recovery reuses its connect reset. Preserve first-failure stop, sector erase,
   keep-unwritten, no auto-unlock, identity/admission/authorization/readback,
   unknown post-flash state and all existing diagnostics/cleanup/native deadlines.
4. RequestedFrequencyHz remains null when omitted; configuredFrequencyHz reports
   100000 for production omission. Existing explicit configuration is reported
   accurately. Selected frequency remains configuration, not measured clock or
   evidence that attachment/programming occurred. Keep receipt/schema/tool counts.
5. Update actual CLI help and both registered MCP tool descriptions, user guide,
   repository flash Skill and Unreleased Changelog. State default 100 kHz and no
   1 MHz acceptance requirement, normal/recovery separation and optional overrides.
   This candidate behavior does not retroactively change published/installed
   v1.3.4 or earlier bytes. Where using an older runtime with frequency support,
   explicitly request 100000 if that value is needed; do not infer this policy
   from unchanged candidate version metadata or a VS Code restart.
6. Primary updates current architecture, procedure and affected governing designs
   to supersede the old default/qualification wording. Preserve historical failed
   run records and immutable Git evidence as history; do not change recorded
   1 MHz attempts into 100 kHz or erase absence of physical success. Historical
   references cannot be treated as current requirements. Do not alter unrelated
   1_000_000 time-unit, size, address or explicit-frequency test data.

## Evidence and acceptance

Before tests, read standard-test-procedure/current checkpoint/latest report.
Claude edits product/tests/guidance only through the stable dispatcher in edit
mode; required test execution is a separate verify invocation with fresh actual
native PowerShell inventory, harmless smoke and exact commands. No retries of
failed/denied invocations are granted. Read/Grep/Glob are allowed in declared
related modules; exact write list remains bounded. Keep configured model route,
provider/auth/permissions. No Codex implementation fallback.

Required offline evidence: production omitted managed/imported selection reaches
the actual captured worker config at 100 kHz, reports null/100000, normal policy,
one operation and no recovery; worker/direct-backend defaults and fake Session
options; explicit custom-frequency preservation and source-config immutability;
unchanged fixed recovery/observation policy and conflict/refusal behavior; CLI
parser/help and actual registered MCP schema/description/forwarding; guides and
Skill do not claim the old default/mandatory 1 MHz or install source changes.
Update affected default assertions without removing safety assertions or coverage.

Claude and Primary each run the final flash-frequency module and required changed
backend/worker/physical-Target cases against the recorded CodeHead. Author runs
the related full backend, partitioned worker, flash, pre-program preparation,
public hardware, Target runner/physical workflow, imported workflow and relevant
guide/CLI/IDE tests. Partition Windows spawn-heavy modules to stay within native
foreground limits. Primary independently reviews the complete base-to-CodeHead
diff in a clean exact-head tree and repeats the complete frequency/new cases plus
affected backend/worker/Target assertions and guidance. Fresh JUnit, exact argv,
real subprocess exit, unchanged-source hashes and native matched events are
reconciled by Primary; do not add overlapping owners/reruns to unique counts.

This is slice software acceptance, not hardware performance, frequency measurement,
fix efficacy or release coverage qualification. Existing Session-construction/USB
attach timeout and original IPSR=3 cause remain unresolved; the new pre-program
reset/halt has not been reached by the recent failed physical attempts. Slower
wire transfer may affect physical elapsed time; finite budgets remain unchanged,
and a later separately authorized ordinary 100 kHz run must validate them rather
than marking performance PASS offline. Existing named platform gates remain
assigned to their later release qualification owner/environment.
