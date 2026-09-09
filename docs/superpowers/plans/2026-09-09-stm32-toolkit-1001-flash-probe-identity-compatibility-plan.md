# STM32TK-1001 flash probe identity compatibility plan

Accepted base: `a69c5e0a794ba6dab71bb316182abb0ec165611a`

Implementation owner: one GPT-5.6-luna/max agent in a clean D-drive isolated worktree. Independent review owner: GPT-5.6-sol in a separate clean D-drive worktree.

1. Update `probe/handoff.py:_validate_flash` to compare the stored probe identity against the exact two-member set derived from the public selector.
2. Revert the a69 pre-hash in `debug/firmware.py`; all `_validate_flash` callers then share the public-selector input domain.
3. Extend existing tests only as needed to prove genuine generic raw and Physical Target hashed records through binding and one debug read/revalidation seam. Prove a wrong selector, another selector's digest, an arbitrary identity, and an old workspace fail before attach/read. A focused shared-validator or handoff regression is sufficient for fault/handoff consumers because their source calls the same validator with the public binding/config selector.
4. Run focused affected tests with all temporary/cache output in a short run-owned D-drive path. GPT-5.6-sol reviews the complete base-to-CodeHead diff, runs only necessary independent focused verification, records the reviewed CodeHead in a short report, and fast-forwards the existing local branch. No deployment, hardware or remote action is authorized.
