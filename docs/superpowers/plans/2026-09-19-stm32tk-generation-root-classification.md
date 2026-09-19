# Generation root classification implementation plan

Specification: `../specs/2026-09-19-stm32tk-generation-root-classification.md`.
Accepted base: `0a6bf2a6c591e5e89c6451050de3087168b77eb4`; existing Project test
candidate: `e22d858494cdc8135052f8ac066d8ee370f8c0a4`.

1. Reuse `_canonical_root` before mutation-lock acquisition in the public apply
   wrapper; retain its existing under-lock call. Luna/max changes only the
   specified source/test/report files on the existing Project branch.
2. Strengthen the existing two root variants to prove no lock entry and no writes.
   Preserve the valid-root lock-failure and successful apply tests unchanged.
3. Return a code head and separate report commit. Prepare a direct copy of the
   accepted selected-node launcher, selecting the complete changed generation
   test file and four previously unrun regeneration functions, with native branch
   data retained. Do not execute or invent a new launcher.
4. Primary reviews complete diff and entry, then runs the one serial batch.
   Any failure is classified before revision; two nonconverging rounds return
   to the contract. Integrate locally only after actual results.
5. Reconcile native data with old configure.py arcs removed from copies and new
   matching-source data included. Independently verify exact native arc union,
   unchanged originals and full denominator. Keep the release unmet if required
   coverage or other gates remain unmet.
