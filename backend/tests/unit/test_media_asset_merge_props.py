"""
Property-based tests for MediaAssetService.merge_duplicates.

Bug 1 — POST /api/media-assets/merge-duplicates returns 500
Feature: tenant-admin-storage-and-merge-500s

These property tests encode two distinct design properties, split so a
"valid group" is never conflated with a "transient DB error":

  * Property 1 (healthy success) — a well-formed group that merges cleanly
    (re-attach succeeds) returns success:true with kept == keep_asset_id:

        FOR ALL X WHERE isHealthyMerge(X) DO
          result := merge_duplicates(X.tenant, X.keep_asset_id, X.duplicate_asset_ids)
          ASSERT result.success = true AND result.kept = X.keep_asset_id
        END FOR

  * Property 2 (propagate) — a transient, non-IntegrityError DatabaseError on
    the re-attach INSERT propagates out of the service (Option A). The route
    maps it to a generic 500 with a correlation error_id; it is NEVER swallowed
    into success:true. IntegrityError is the ONE tolerated re-attach error
    (duplicate-key collision, skipped — see the preservation property); every
    OTHER DatabaseError propagates.

Validates: Requirements 2.1, 2.5
Reference: .kiro/specs/tenant-admin-storage-and-merge-500s/design.md (Property 1, Property 2)
"""

import os
import sys

import pytest
from unittest.mock import MagicMock, patch
from hypothesis import given, strategies as st, settings, HealthCheck

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from db_exceptions import DatabaseError
from services.media_asset_service import MediaAssetService


# ---------------------------------------------------------------------------
# Strategies — well-formed duplicate groups (the bug-condition input space)
# ---------------------------------------------------------------------------

_tenant_st = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="_-"),
    min_size=1,
    max_size=30,
)

# Asset IDs shaped like the real ast_<ULID> identifiers.
_ulid_char_st = st.text(
    alphabet="0123456789ABCDEFGHJKMNPQRSTVWXYZ", min_size=26, max_size=26
)
_asset_id_st = _ulid_char_st.map(lambda u: f"ast_{u}")


@st.composite
def well_formed_group(draw):
    """A valid merge request: keep asset present, non-empty duplicate list,
    all IDs tenant-owned and distinct from the keep ID."""
    tenant = draw(_tenant_st)
    keep_id = draw(_asset_id_st)
    dups = draw(
        st.lists(
            _asset_id_st.filter(lambda a: a != keep_id),
            min_size=1,
            max_size=4,
            unique=True,
        )
    )
    return tenant, keep_id, dups


def _make_service():
    mock_db = MagicMock()
    with patch("services.media_asset_service.ParameterService"):
        service = MediaAssetService(mock_db)
    return service, mock_db


def _wire_healthy_merge(mock_db, keep_id, reattach_raises=None):
    """Wire the mock DB so a well-formed group merges cleanly.

    If reattach_raises is set, the re-attach INSERT raises that exception —
    reproducing the bug condition (a non-IntegrityError DatabaseError).
    """
    mock_db.execute_query.return_value = [{"id": keep_id, "content_hash": "hash123"}]

    cursor = MagicMock()
    # Each duplicate exists for the tenant...
    cursor.fetchone.return_value = {
        "id": "dup",
        "s3_key": "TenantX/invoices/dup_doc.pdf",
        "bucket": "test-bucket",
    }
    # ...and carries a single reference to re-home.
    cursor.fetchall.return_value = [
        {"id": "ref_1", "entity_type": "invoice", "entity_id": "inv_1"}
    ]

    if reattach_raises is not None:

        def execute_side_effect(sql, params=None):
            if "INSERT INTO s3_asset_references" in sql:
                raise reattach_raises
            return None

        cursor.execute.side_effect = execute_side_effect

    conn = MagicMock()
    mock_db.transaction.return_value.__enter__ = MagicMock(return_value=(cursor, conn))
    mock_db.transaction.return_value.__exit__ = MagicMock(return_value=False)
    return cursor


# ---------------------------------------------------------------------------
# Property 1 (Fix Checking) — a HEALTHY valid group returns success
# ---------------------------------------------------------------------------


@settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(group=well_formed_group())
def test_merge_duplicates_healthy_group_returns_success(group):
    """For any well-formed duplicate group that merges cleanly (re-attach
    succeeds — no transient DB error), the merge returns success:true with
    kept == keep_asset_id and no unhandled exception.

    This is the genuine positive property: a HEALTHY merge, with NO injected
    re-attach error. It must not conflate "valid group" with "transient DB
    error" — the latter is covered by the propagation property below.

    **Validates: Requirements 2.1 (design Property 1 — healthy success)**
    """
    tenant, keep_id, dups = group

    with (
        patch.dict(
            os.environ,
            {
                "S3_SHARED_BUCKET": "test-shared-bucket",
                "LANDING_PAGES_BUCKET": "test-public-pages-bucket",
            },
        ),
        patch("services.media_asset_service.boto3.client", return_value=MagicMock()),
    ):
        service, mock_db = _make_service()
        # No reattach_raises — the re-attach INSERT succeeds (healthy merge).
        _wire_healthy_merge(mock_db, keep_id)

        with patch.object(service, "_delete_raw", return_value=True):
            result = service.merge_duplicates(tenant, keep_id, dups)

    assert isinstance(result, dict)
    assert result["success"] is True
    assert result["kept"] == keep_id


# ---------------------------------------------------------------------------
# Property 2 (Propagate) — a transient, non-IntegrityError DatabaseError on the
# re-attach INSERT propagates out of the service (Option A). The route maps it
# to a generic 500; it is NEVER swallowed into success:true. IntegrityError is
# the ONE tolerated re-attach error (covered by the preservation property
# below); every OTHER DatabaseError propagates.
# ---------------------------------------------------------------------------


@settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(group=well_formed_group())
def test_merge_duplicates_reattach_transient_dberror_propagates(group):
    """For any well-formed duplicate group whose re-attach INSERT hits a
    transient, non-IntegrityError DatabaseError (e.g. a lock-wait timeout), the
    error must PROPAGATE out of merge_duplicates — not be swallowed into a
    success result. The route's try/except converts it to a generic 500 with a
    correlation error_id.

    **Validates: Requirements 2.5 (design Property 2 — propagate)**
    """
    tenant, keep_id, dups = group

    with (
        patch.dict(
            os.environ,
            {
                "S3_SHARED_BUCKET": "test-shared-bucket",
                "LANDING_PAGES_BUCKET": "test-public-pages-bucket",
            },
        ),
        patch("services.media_asset_service.boto3.client", return_value=MagicMock()),
    ):
        service, mock_db = _make_service()
        _wire_healthy_merge(
            mock_db,
            keep_id,
            reattach_raises=DatabaseError(
                "Lock wait timeout exceeded", error_code=1205
            ),
        )

        with patch.object(service, "_delete_raw", return_value=True):
            with pytest.raises(DatabaseError):
                service.merge_duplicates(tenant, keep_id, dups)


# ===========================================================================
# Preservation properties (Task 2) — invariant skip / tolerance semantics.
#
# These encode the Preservation Checking property from the design doc:
#
#     FOR ALL X WHERE NOT isBugCondition_merge(X) DO
#       ASSERT merge_duplicates(X) behaves as the preserved baseline
#     END FOR
#
# They MUST PASS on the current (UNFIXED) code — they capture the behavior to
# preserve for non-bug-condition inputs: self-references and wrong-tenant /
# non-existent duplicate IDs are skipped (never raised), an empty duplicate
# list is a no-op success, and an already-present reference (IntegrityError on
# re-attach) is tolerated with the merge still succeeding.
#
# Validates: Requirements 2.3, 2.4, 3.2, 3.3 (design Property 2)
# Reference: .kiro/specs/tenant-admin-storage-and-merge-500s/design.md (Property 2)
# ===========================================================================

from db_exceptions import IntegrityError


def _wire_keep_and_cursor(mock_db, keep_id, cursor):
    """Keep-asset existence check passes; transaction yields `cursor`."""
    mock_db.execute_query.return_value = [{"id": keep_id, "content_hash": "h"}]
    conn = MagicMock()
    mock_db.transaction.return_value.__enter__ = MagicMock(return_value=(cursor, conn))
    mock_db.transaction.return_value.__exit__ = MagicMock(return_value=False)


@settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(tenant=_tenant_st, keep_id=_asset_id_st)
def test_merge_duplicates_self_reference_only_is_noop_success(tenant, keep_id):
    """A duplicate list containing only the keep ID (any number of repeats) is
    skipped entirely: no transaction is opened and the merge is a no-op success
    with deleted == 0.

    Preservation (3.2) — PASSES on unfixed code.
    """
    with (
        patch.dict(
            os.environ,
            {
                "S3_SHARED_BUCKET": "test-shared-bucket",
                "LANDING_PAGES_BUCKET": "test-public-pages-bucket",
            },
        ),
        patch("services.media_asset_service.boto3.client", return_value=MagicMock()),
    ):
        service, mock_db = _make_service()
        mock_db.execute_query.return_value = [{"id": keep_id, "content_hash": "h"}]

        with patch.object(service, "_delete_raw", return_value=True):
            result = service.merge_duplicates(tenant, keep_id, [keep_id, keep_id])

    assert result["success"] is True
    assert result["deleted"] == 0
    # Self-reference only → the per-duplicate transaction is never entered.
    mock_db.transaction.assert_not_called()


@settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(tenant=_tenant_st, keep_id=_asset_id_st)
def test_merge_duplicates_empty_duplicate_list_is_noop_success(tenant, keep_id):
    """An empty duplicate list never iterates: no transaction, success with
    merged == 0 and deleted == 0.

    Preservation (2.4-adjacent) — PASSES on unfixed code.
    """
    with (
        patch.dict(
            os.environ,
            {
                "S3_SHARED_BUCKET": "test-shared-bucket",
                "LANDING_PAGES_BUCKET": "test-public-pages-bucket",
            },
        ),
        patch("services.media_asset_service.boto3.client", return_value=MagicMock()),
    ):
        service, mock_db = _make_service()
        mock_db.execute_query.return_value = [{"id": keep_id, "content_hash": "h"}]

        with patch.object(service, "_delete_raw", return_value=True):
            result = service.merge_duplicates(tenant, keep_id, [])

    assert result["success"] is True
    assert result["merged"] == 0
    assert result["deleted"] == 0
    mock_db.transaction.assert_not_called()


@settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(group=well_formed_group())
def test_merge_duplicates_wrong_tenant_duplicates_skipped(group):
    """When every duplicate's tenant-scoped lookup returns no row (non-existent
    or wrong-tenant), each is skipped (not raised) and the merge returns
    success with merged == 0 and deleted == 0.

    Preservation (2.3) — PASSES on unfixed code.
    """
    tenant, keep_id, dups = group

    with (
        patch.dict(
            os.environ,
            {
                "S3_SHARED_BUCKET": "test-shared-bucket",
                "LANDING_PAGES_BUCKET": "test-public-pages-bucket",
            },
        ),
        patch("services.media_asset_service.boto3.client", return_value=MagicMock()),
    ):
        service, mock_db = _make_service()
        cursor = MagicMock()
        cursor.fetchone.return_value = None  # duplicate not found for this tenant
        _wire_keep_and_cursor(mock_db, keep_id, cursor)

        with patch.object(service, "_delete_raw", return_value=True):
            result = service.merge_duplicates(tenant, keep_id, dups)

    assert result["success"] is True
    assert result["merged"] == 0
    assert result["deleted"] == 0
    # No s3_assets row is ever deleted for a skipped duplicate.
    executed = " ".join(str(c[0][0]) for c in cursor.execute.call_args_list)
    assert "DELETE FROM s3_assets" not in executed


@settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(group=well_formed_group())
def test_merge_duplicates_reattach_integrityerror_tolerated(group):
    """An already-present reference raises IntegrityError on the re-attach
    INSERT; it is tolerated (that reference skipped) and the merge still
    succeeds with kept == keep_id.

    Preservation (3.3) — PASSES on unfixed code: the existing
    `except IntegrityError` already handles the unique-collision case.
    """
    tenant, keep_id, dups = group

    with (
        patch.dict(
            os.environ,
            {
                "S3_SHARED_BUCKET": "test-shared-bucket",
                "LANDING_PAGES_BUCKET": "test-public-pages-bucket",
            },
        ),
        patch("services.media_asset_service.boto3.client", return_value=MagicMock()),
    ):
        service, mock_db = _make_service()
        cursor = MagicMock()
        cursor.fetchone.return_value = {
            "id": "dup",
            "s3_key": "T/invoices/dup.pdf",
            "bucket": "b",
        }
        cursor.fetchall.return_value = [
            {"id": "ref_1", "entity_type": "invoice", "entity_id": "inv_1"}
        ]

        def execute_side_effect(sql, params=None):
            if "INSERT INTO s3_asset_references" in sql:
                raise IntegrityError("Duplicate entry", error_code=1062)
            return None

        cursor.execute.side_effect = execute_side_effect
        _wire_keep_and_cursor(mock_db, keep_id, cursor)

        with patch.object(service, "_delete_raw", return_value=True):
            result = service.merge_duplicates(tenant, keep_id, dups)

    assert result["success"] is True
    assert result["kept"] == keep_id
