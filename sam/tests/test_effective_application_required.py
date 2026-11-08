"""Task 19.2: the public form's `required` shares ONE authority with the engine.

Behavioural parity (rendered required set == engine-rejected set) is proven against the
h-dcn fixture in ``test_published_form_submit_round5_bug_condition.py``; this guards the
no-duplicated-literal-lists wiring.
"""

from __future__ import annotations

from sam.members.domain._membership_writes_application import ApplicationWritesMixin
from sam.members.domain._membership_writes_validation import (
    APPLICATION_REQUIRED_IDENTITY_KEYS,
    APPLICATION_SERVER_SET_MEMBERSHIP_KEYS,
    ValidationMixin,
)
from sam.members.domain.fixed_fields import field_by_key


def test_engine_and_helper_share_the_same_constants():
    assert (
        ValidationMixin._APPLICATION_REQUIRED_IDENTITY_KEYS
        is APPLICATION_REQUIRED_IDENTITY_KEYS
    )
    assert (
        ApplicationWritesMixin._APPLICATION_PRIVILEGED_MEMBERSHIP_KEYS
        is APPLICATION_SERVER_SET_MEMBERSHIP_KEYS
    )


def test_identity_keys_exist_in_the_fixed_registry():
    assert all(field_by_key(k) is not None for k in APPLICATION_REQUIRED_IDENTITY_KEYS)
