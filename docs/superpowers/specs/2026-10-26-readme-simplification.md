# Bilingual README simplification

Accepted base: `ae53ac0ffb8db0a4c798d9bcaddca443e9e842d1`.
Owner/reviewer: primary. Implementer: local Claude Code CLI, existing provider.
The user requests current English/Chinese READMEs and removal of excessive detail.

Both READMEs become concise recipient landing pages: purpose, a few concrete
features, actual v1.3.2 download/checksum links, platform prerequisites, a short
first-install path and a matching absolute CLI example, with links to detailed
installation, AI/VS Code guidance and release notes. Aim for 60–90 lines each.
Preserve safe, accurate setup ordering and actual parameters; do not claim native
Keil builds, fresh hardware validation or a completed user installation.

Remove duplicated historical release recipes, internal qualification decisions,
commit IDs, implementation matrices and exhaustive guard/field descriptions from
the landing pages. Their authoritative detailed documents remain accessible.
Do not weaken runtime or hardware contracts. Existing README assertions may be
updated only to reflect this user-requested navigation/content contract.

Publication facts: v1.3.2 Release 423877513 is Latest, published 2026-10-26;
all 13 anonymous downloads match the verified frozen candidate. The user's
candidate exception and remaining validation are documented in the Release.
This docs/test update does not rebuild or retag the package.
