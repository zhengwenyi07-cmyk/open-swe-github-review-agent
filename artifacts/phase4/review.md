# Local Code Review

- Commit: `df96cd3e49b65e09ec1891cc419e0753e0583958`
- Decision: `REQUEST_CHANGES`
- Test status: `NOT_RUN_READ_ONLY`
- Tests passed: `false`

## Summary

The new `average` function divides by `len(values) - 1` instead of `len(values)`, producing an incorrect arithmetic mean. For any input the result will be systematically too large (e.g., `average([1, 2, 3])` returns 3.0 instead of the correct 2.0).

## Findings

### 1. HIGH — correctness

- Location: `examples/phase4_average.py:7`
- Assessment: `confirmed`
- Evidence: Line 7: `return sum(values) / (len(values) - 1)` — the arithmetic mean formula requires dividing by the count of elements (`len(values)`), not one fewer. For input `[1, 2, 3]` this returns 6/2 = 3.0 instead of the correct 6/3 = 2.0.
- Recommendation: Change the divisor from `len(values) - 1` to `len(values)`:
`return sum(values) / len(values)`

## Uncertainties

- `examples/phase4_average.py:7` — Is this an intentional defect planted for Phase 4 testing? The PR body mentions 'an intentionally reviewable arithmetic defect', which suggests this bug is deliberate. If so, it should still be flagged and fixed before any merge.
  Evidence needed: PR body explicitly states the defect is intentional for testing purposes.

## Test Commands

No commands executed in GitHub read-only mode.
