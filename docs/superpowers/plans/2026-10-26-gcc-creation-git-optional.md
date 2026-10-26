# Git-optional project creation

Accepted base: `ae259981c5a0b25c213d47e50f64d558c1be32ac`. Governing specification: 2026-10-26-gcc-delivery-contract.md. Primary owns design/review, Claude Code CLI owns implementation/tests. This independent small slice can be implemented while content-identity work proceeds; combined GCC build/flash acceptance remains at integration.

Remove the Git HEAD prerequisite from prepare_creation_workflow. A project-less workspace without .git, an unborn repository and a committed repository use the same existing plan -> prepare -> authorized apply behavior. Source/request/destination/expiry/environment digest, single-use capability, native generation/configuration/build/activation safeguards remain unchanged. Missing real tool prerequisites still diagnose accurately before authorization is persisted; Git is not one of those prerequisites. No new command or flag is needed.

Allowed code: creation_workflows.py; relevant test_creation_workflows.py, test_creation_apply.py and test_creation_authorization.py. Add offline regression for no-Git and unborn prepare, and a no-Git public apply using the existing fake generation adapter and existing contract helpers. Preserve tests for plan mismatch, invalid environment, destination collision and consumed capability. Do not claim native CubeMX, real GCC or physical flash based on fake adapters; those integration checks have separate owners.

Evidence: author executes the three existing test files against committed head; primary reviews every changed line in a clean exact-head tree and independently runs the public workflow tests. Do not edit original projects, tools/runtimes/global configuration, release versions or remote Git. This plan does not authorize hardware.
