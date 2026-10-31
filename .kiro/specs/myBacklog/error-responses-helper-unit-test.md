# Unit test for routes/error_responses.py helper
Task 4 of security-assessment-2026-10-19 added backend/src/routes/error_responses.py
(error_response / error_payload) but no dedicated unit test — it is currently covered
only indirectly via converted route tests. Add backend/tests/unit/test_error_responses.py
asserting: generic client_message returned, non-empty error_id, str(exc) never in body,
status passthrough, include_success=False shape, and full-exception server-side logging
(caplog + exc_info). Mechanical; the helper is stable.
