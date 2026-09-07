# STM32TK-1001 GNU MAP Exact-Width Section Design

**Module / phase:** STM32 Toolkit 1.0 VS10-A, Task 8 P2 build validation correction  
**Accepted correction base:** `69b7f2e2fdc45a6052adb1680d778b7e54f125d6`  
**Specification/review owner:** GPT-5.6-sol primary  
**Implementation owner:** the existing single GPT-5.6-luna/max Task 8 implementer  
**Authority:** user approved continuing approach A and the bounded repair; no hardware or remote authority

## Problem

The real GNU ld MAP wraps the exact 16-character output-section name `.stm32tk_mailbox` onto a
name-only line followed by an indented address/size line. `map_file.py` documents a 16-column GNU
field, but `_WRAPPED_SECTION_NAME_RE` matches one leading character plus at least sixteen more
characters. It therefore accepts total length 17 or greater and rejects the valid total-length-16
boundary. ELF validation sees the alloc section while MAP parsing omits it, so reconciliation fails
closed with `BUILD_MAP_INVALID`, `rule=missing`.

## Public behavior

1. A syntactically valid total-length-16 GNU output-section name followed immediately by the exact
   existing continuation format is parsed and reconciled with ELF evidence.
2. Existing total-length-17-or-greater wrapped names, inline rows, load-address accounting,
   duplicate rejection, malformed continuation rejection, bounds, region equality, and ELF/MAP
   address/size/alloc matching remain unchanged.
3. A name shorter than sixteen characters on a name-only line is not newly accepted as a wrapped
   section.

## Implementation boundary

Change only the wrapped-name length boundary in
`tools/stm32-toolkit/src/stm32_toolkit/build/map_file.py` and add focused boundary regressions in
`tools/stm32-toolkit/tests/test_build_map.py`. No project-specific section-name special case, parser
rewrite, schema change, error-code change, backend/runtime/controller, or relaxed continuation is
allowed.

## Verification

TDD first demonstrates that a 16-character wrapped section with matching ELF evidence fails at the
accepted base. GREEN must pass that case, preserve a 15-character rejection case, and pass the
existing wrapped/duplicate/malformed/MAP suite. After independent Sol review, rebuild the same
campaign 0.9 runtime from the accepted code and rerun the project public build; the project build is
integration evidence, not a substitute for the parser regression.

No probe, attach, read, reset, flash, Target execute, remote operation, release, or VS10-B action is
part of this correction.
