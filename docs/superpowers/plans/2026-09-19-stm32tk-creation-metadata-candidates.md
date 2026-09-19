# Creation package metadata candidate correction plan

Accepted base: `ab2fd448a73a319b026a5a6da700b31c2535975f`.
Specification: `../specs/2026-09-19-stm32tk-creation-metadata-candidates.md`.

1. Primary preserves run2 logs, JUnit and raw data under r10/e/n95/p/run2 and
   records PRODUCT_METADATA_CANDIDATE_SHORT_CIRCUIT. No repeat at failed bytes.
2. Existing Luna/max Project owner continues c96p from executed 52068273,
   cherry-picks this specification/plan commit, and owns only
   creation_environment.py plus its existing test file. Do not amend executed
   commits, modify other owners, run hardware, or change dependencies/scopes.
3. Add narrow missing-lstat continuation and explicit no-metadata refusal.
   Keep existing corrupt/read-error fail-closed behavior and priority. Implement
   meaningful public cases with existing fixtures; return exact selectors.
4. Primary independently reviews the complete accepted-base-to-final diff in a
   clean review checkout and verifies both candidate precedence and error scope.
   Primary serial executor runs the affected environment file plus the remaining
   unrun creation authorization/apply/regeneration functions, budget 300 seconds,
   first failure stop, D-drive roots and native coverage finally-save entry.
5. Integrate the accepted correction locally. Final union purges only the old
   creation_environment.py from copied Toolkit inputs and uses current-source
   arcs for that file; Monitor denominator/sources remain unchanged. Report real
   coverage and any remaining requirements. No package/deploy/hardware rerun is
   justified solely by this pre-generation metadata discovery correction.
