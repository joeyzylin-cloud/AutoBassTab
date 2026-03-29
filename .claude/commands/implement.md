---
description: Implement a stub function with full logic
---

# /implement $ARGUMENTS

You are implementing the function `$ARGUMENTS` in the AutoBassTab project.

## Steps

1. **Read the stub**: Find the function `$ARGUMENTS` in `src/`. Read the file to understand the signature, docstring, and surrounding context.
2. **Read models.py**: Understand the data structures used by this function.
3. **Implement**: Replace the `raise NotImplementedError(...)` with a complete implementation that:
   - Follows existing type hints and docstring contract
   - Uses loguru for logging (no bare print)
   - Uses Path objects for file paths
   - Raises the module's custom Exception on errors
4. **Run tests**: Execute `pytest tests/ -v` to verify nothing is broken.
5. **Fix failures**: If any test fails, read the failure output, fix the implementation, and re-run until all tests pass.

## Important
- Do NOT change function signatures or docstrings.
- Do NOT add new dependencies without asking.
- Keep the implementation minimal and correct.
