# Local Code Review

- Commit: `f2b5ba53cde514e580e9170fa84230da713b61fa`
- Decision: `REQUEST_CHANGES`
- Tests passed: `false`

## Summary

The diff grants the "viewer" role permission to delete projects via `can_delete_project`. This is a privilege escalation: "viewer" is conventionally a read-only role, and delete is a destructive, high-privilege action. The prior code correctly restricted deletion to "admin" only.

## Findings

### 1. CRITICAL — security

- Location: `permissions.py:2`
- Assessment: `confirmed`
- Evidence: The change from `role == "admin"` to `role in {"admin", "viewer"}` grants the "viewer" role delete-project permission. Viewers conventionally have read-only access; allowing them to delete projects is a privilege escalation that violates the principle of least privilege.
- Recommendation: Remove "viewer" from the allowed-role set, reverting to `return role == "admin"`, or add the specific role that actually needs delete access. If viewers genuinely need delete permission, add an explicit comment or docstring explaining why this override is intentional.

## Uncertainties

None recorded.

## Test Commands

- `python -m unittest test_permissions.py`
