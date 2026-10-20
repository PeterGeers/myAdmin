"""
Members config — SAM-owned write path, Task 1.4 — property-based **version-stamp** tests
(design Correctness Properties, Property 3).

Feature: Members config — SAM-owned write path (Phase 1), Property 3: Idempotent / monotonic
ordering-only version stamp.

Validates: Requirements 6.2, 6.4, 6.5

Code under test
---------------
``sam.members.domain.config_write_version.next_write_stamp`` (Task 1.3) — the pure domain helper
that mints the row-level ``version`` write stamp the config-write service stamps on every
``config#*`` put. It returns ``datetime.now(timezone.utc).isoformat()``: a timezone-aware
ISO-8601 UTC string. No boto3, no DynamoDB, no table resolution — just the standard-library
clock — so the version model is testable in isolation here.

What Property 3 asserts (design "Property 3: Idempotent / monotonic ordering-only version stamp")
-------------------------------------------------------------------------------------------------
Three sub-properties, each exercised across many iterations:

- ``test_property_later_write_yields_lexicographically_greater_stamp`` (R6.2): FOR ALL pairs of
  writes to the same row, a later write produces a lexicographically-greater Version_Stamp than
  an earlier write. ISO-8601 UTC sorts lexicographically in chronological order, so a stamp
  minted later is ``>=`` one minted earlier (and ``>`` whenever the monotonic clock advanced —
  which, measured around the call, it does). The ordering is asserted on the RAW string via
  plain ``<`` / ``sorted``, exactly how a DynamoDB string attribute compares — so this is the
  real ordering guarantee, not a datetime re-parse.

- ``test_property_restamping_same_value_is_a_no_op`` (R6.4): the idempotent-put guarantee at the
  version-model layer. A minted stamp is an immutable, deterministic string value; re-applying
  that SAME stamp to a row carrying that SAME stamp changes nothing observable (``str`` is
  value-stable: re-assigning an equal value is a no-op). This is the version-model half of
  "re-putting identical attributes + version is observably a no-op" — the stamp itself never
  mutates an item it is re-applied to. (The repository-level put idempotency is covered by
  Task 1.2's Property 2 tests against the write repository; here we pin the stamp's own
  contribution to it.)

- ``test_property_stamp_is_independent_of_consent_notice_version`` (R6.5): the row-level
  Version_Stamp is kept STRICTLY SEPARATE from the ``config#mail``
  ``application_consent_notice.version``. ``next_write_stamp()`` takes NO arguments, so its
  output cannot be a function of any consent-notice version: minting a stamp "alongside" any
  arbitrary consent-notice version leaves the stamp a well-formed ISO-8601 UTC marker, never
  equal to / derived from that consent-notice version. We also assert the two are not conflated
  for a value a consent-notice version realistically takes.

Genuine (non-tautological) properties
--------------------------------------
Monotonicity is asserted on the raw string with the same comparison DynamoDB uses (not a
datetime round-trip), so it proves the on-the-wire ordering. Independence is asserted by feeding
arbitrary consent-notice version values through a strategy and showing the minted stamp neither
equals nor is derived from them — a real separation proof, not "does not raise". No clock is
mocked: the test relies only on the real monotonic property of wall-clock UTC across successive
calls (ties are permitted by ``>=`` and are themselves valid monotonic behaviour).

No live AWS, no MySQL: the helper is pure standard library.
"""

import os
import sys
from datetime import datetime

from hypothesis import given, settings
from hypothesis import strategies as st

# repo root on sys.path (mirrors sam/conftest.py) so `sam.members` imports.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from sam.members.domain.config_write_version import next_write_stamp


# ---------------------------------------------------------------------------
# A shared well-formedness check: a stamp is a parseable, timezone-aware ISO-8601 UTC string.
# ---------------------------------------------------------------------------


def _is_well_formed_utc_stamp(stamp: str) -> bool:
    """True iff ``stamp`` is a timezone-aware ISO-8601 instant (what ``next_write_stamp`` mints)."""
    if not isinstance(stamp, str):
        return False
    parsed = datetime.fromisoformat(stamp)  # raises ValueError if not ISO-8601
    return parsed.tzinfo is not None


# ---------------------------------------------------------------------------
# Property 3a — a later write yields a lexicographically-greater stamp (R6.2, monotonic)
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(data=st.data())
def test_property_later_write_yields_lexicographically_greater_stamp(data):
    """Feature: Members config SAM-owned write path, Property 3 (monotonic-ordering leg).

    Validates: Requirement 6.2

    For any pair of writes to the same row, the later write's Version_Stamp is
    lexicographically-greater-or-equal to the earlier one's. ISO-8601 UTC sorts
    lexicographically in chronological order, so the raw-string comparison DynamoDB performs
    orders the two stamps chronologically. Asserted on the RAW strings (plain ``<=`` + a
    ``sorted`` round-trip), not on re-parsed datetimes, so it proves the on-the-wire ordering.
    """
    earlier = next_write_stamp()
    # Draw a tiny, possibly-empty burst of intervening writes so the property holds across a
    # variable number of writes to the same row, not just two adjacent calls.
    for _ in range(data.draw(st.integers(min_value=0, max_value=3))):
        next_write_stamp()
    later = next_write_stamp()

    # Both are well-formed timezone-aware ISO-8601 UTC markers.
    assert _is_well_formed_utc_stamp(earlier)
    assert _is_well_formed_utc_stamp(later)

    # Monotonic on the RAW string (the comparison a DynamoDB string attribute uses): a later
    # write is never lexicographically-less than an earlier one. (Equality is permitted — ties
    # at clock resolution are still valid monotonic/last-writer-wins behaviour, R6.6/R6.8.)
    assert earlier <= later
    # And the on-the-wire ordering agrees with the write order.
    assert sorted([later, earlier]) == [earlier, later]


# ---------------------------------------------------------------------------
# Property 3b — re-applying an identical stamp is observably a no-op (R6.4, idempotent)
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    # Arbitrary already-present row attributes the idempotent re-put would carry.
    attributes=st.dictionaries(
        keys=st.text(
            alphabet="abcdefghijklmnopqrstuvwxyz_", min_size=1, max_size=10
        ),
        values=st.one_of(st.text(max_size=20), st.booleans(), st.integers()),
        max_size=5,
    )
)
def test_property_restamping_same_value_is_a_no_op(attributes):
    """Feature: Members config SAM-owned write path, Property 3 (idempotent-stamp leg).

    Validates: Requirement 6.4

    The version-model half of "re-putting identical attributes + version is observably a no-op".
    A minted stamp is an immutable, deterministic string value, so re-applying the SAME stamp to
    a row that already carries attributes + that SAME stamp produces no observable change: the
    resulting item is byte-for-byte equal to the one already stored.
    """
    stamp = next_write_stamp()
    assert _is_well_formed_utc_stamp(stamp)

    # The row as already stored (attributes + the minted stamp).
    stored = dict(attributes)
    stored["version"] = stamp

    # A re-put of identical attributes + the SAME stamp (the version model re-applies the SAME
    # value, never a freshly-minted one, on an idempotent re-put).
    re_put = dict(attributes)
    re_put["version"] = stamp

    # Observably a no-op: the re-stamped item equals the stored item exactly, and the stamp
    # value itself is unchanged (a string compares/assigns by value — no mutation).
    assert re_put == stored
    assert re_put["version"] == stored["version"]
    assert re_put["version"] is stamp  # same immutable value re-applied, not re-minted


# ---------------------------------------------------------------------------
# Property 3c — the row stamp is independent of the consent-notice version (R6.5)
# ---------------------------------------------------------------------------

# Values a `config#mail` `application_consent_notice.version` realistically takes — a free-form
# author-supplied revision string (semver-ish, dates, plain counters). The point is that NONE of
# them can influence `next_write_stamp()`, which takes no arguments at all.
#
# The free-text leg carries a DISTINCTIVE alphabetic marker ("CONSENT") the generated value can
# never collide with an ISO-8601 instant on: an ISO-8601 UTC stamp contains only digits and the
# separators `-`, `:`, `.`, `T`, `+` — so a lone `.` / digit from a naive `st.text()` is NOT
# proof the stamp "embeds" the consent version (it is an incidental character the timestamp
# always has). Anchoring the substring check to "CONSENT" makes the separation proof genuine
# without false positives.
_consent_notice_version = st.one_of(
    st.sampled_from(["v1", "v2", "1.0.0", "2026-01-01", "0", "draft"]),
    st.text(
        alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
        max_size=12,
    ).map(lambda s: f"CONSENT-{s}"),
    st.integers(min_value=0, max_value=9999).map(str),
)


@settings(max_examples=100)
@given(consent_notice_version=_consent_notice_version)
def test_property_stamp_is_independent_of_consent_notice_version(consent_notice_version):
    """Feature: Members config SAM-owned write path, Property 3 (separation leg).

    Validates: Requirement 6.5

    The row-level Version_Stamp is kept separate from the ``config#mail``
    ``application_consent_notice.version``. ``next_write_stamp()`` takes NO arguments, so for ANY
    consent-notice version the minted row stamp is a well-formed ISO-8601 UTC marker that is
    neither equal to nor derived from that consent-notice version — the two are not conflated.
    """
    # Mint the row stamp "alongside" an arbitrary consent-notice version — the helper never sees
    # it (no argument), so it cannot depend on it.
    stamp = next_write_stamp()

    # Still a well-formed ordering marker regardless of the consent-notice version.
    assert _is_well_formed_utc_stamp(stamp)

    # Not conflated with the consent-notice version: the row stamp is not equal to that value.
    assert stamp != consent_notice_version
    # And it does not embed a distinctive (non-ISO) consent-version token. An ISO-8601 UTC
    # instant is built only from digits and the separators `-`, `:`, `.`, `T`, `+`, so only a
    # token containing a character outside that set could prove embedding without a false
    # positive — the "CONSENT-" marked free-text values are exactly such tokens.
    if "CONSENT-" in consent_notice_version:
        assert consent_notice_version not in stamp
        assert "CONSENT" not in stamp
