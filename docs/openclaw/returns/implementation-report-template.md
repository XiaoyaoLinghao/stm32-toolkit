# MODULE-ID ATTEMPT Implementation Report

Copy this file to `docs/openclaw/returns/{MODULE-ID}/{ATTEMPT}-implementation-report.md` and replace every instructional value before returning work.

Status: `IMPLEMENTED` or `BLOCKED`
Branch: `openclaw/{MODULE-ID}/{ATTEMPT}`
Base commit: full 40-character commit
Head commit: full 40-character commit
PR/compare URL: GitHub URL
Work order: exact repository-relative path

## 1. Outcome

- Implemented user-visible result: exact observed result
- Scope completed: complete item list
- Known limitations: `NONE` or an explicit list
- Deviations from work order: `NONE` or an explicit list with reason

## 2. Complete changed-path inventory

| Status | Path | Work-order section | Purpose |
|---|---|---|---|
| A/M/D/R | exact repository-relative path | section number | purpose |

The table must reconcile with `git diff --name-status {BASE}..{HEAD}`.

## 3. Public contracts delivered

- Types/signatures: exact list
- Commands/events/configuration/schemas: exact list
- External interfaces: exact list or `NONE`

## 4. Verification evidence

| Command | Environment | Exit code | Observed result |
|---|---|---:|---|
| exact command | OS/runtime/version | numeric exit code | test count and result |

### Manual verification

| Step | Observed result | Evidence path |
|---|---|---|
| exact step | observed result | repository-relative path or `N/A` |

### Artifacts

| Artifact | Path | Size/checksum |
|---|---|---|
| exact name | repository-relative or external artifact path | value |

## 5. Security, privacy, performance, and compatibility

- Security checks: commands and results
- Privacy/redaction checks: results
- Performance measurements: method, result, and budget
- Accessibility/input checks: results or `NOT_APPLICABLE` with reason
- Compatibility checks: targets and results

## 6. Blockers or risks

- Blockers: `NONE` or exact evidence
- Residual risks: `NONE` or exact list
- Follow-up recommendation: `NONE` or an out-of-scope recommendation; do not implement it silently

## 7. Author checklist

- [ ] Report matches the returned head commit and complete diff.
- [ ] Every required test command is recorded with observed output.
- [ ] No credentials, private data, caches, build output, or unredacted diagnostics are committed.
- [ ] No unrelated file, agent instruction, approved work order, or remote policy changed.
- [ ] Every instructional value in this report is replaced with actual evidence.
