---
description: Add tests for a module with focus on edge cases
---

# /add-test $ARGUMENTS

You are adding tests for the module `$ARGUMENTS` in the AutoBassTab project.

## Steps

1. **Read the module**: Read `src/$ARGUMENTS.py` and understand all public functions.
2. **Read existing tests**: Check `tests/test_$ARGUMENTS.py` for existing coverage.
3. **Identify edge cases**: Think about:
   - Boundary values (empty input, single element, max fret, out-of-range MIDI)
   - Error conditions (invalid input, missing files)
   - Strategy-specific behavior for tab_engine
4. **Write tests**: Add new test functions to `tests/test_$ARGUMENTS.py` using pytest:
   - Use descriptive names: `test_<function>_<scenario>`
   - Use hand-constructed data (NoteEvent, FretPosition) — no audio files needed
   - Each test should assert ONE specific behavior
5. **Run tests**: Execute `pytest tests/ -v` and ensure all tests pass.
6. **Fix failures**: If any test fails due to a bug in the implementation, fix the implementation — not the test (unless the test expectation is wrong).
