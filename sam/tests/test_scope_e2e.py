"""
S5d Task 7.3 — the cross-plane **member-scope E2E** (design § Testing Strategy "E2E (R7.3)",
Properties 2/3).

WHAT THIS IS
------------
A **wired-fakes** end-to-end that exercises the WHOLE s5d chain with REAL code across the
plane seam, faking ONLY the true I/O boundaries. It proves the one contract R7.3 hangs on:
**the ``scopegrant#<email>#region`` row the Flask/MySQL projection WRITES is the exact row
the SAM reader CONSUMES.** There is no live AWS/MySQL in the test pool, so — mirroring the
projection-sync tests (``backend/tests/unit/test_projection_sync.py``'s ``FakeTable``) and
the SAM read tests (``FakeMembersRepository``) — the seams are backed by in-memory fakes,
but every step in between runs the real objects.

THE FOUR-HOP PATH (design Testing Strategy)
-------------------------------------------
1. **Flask/MySQL plane** — the REAL
   :class:`services.user_tenant_scope_service.UserTenantScopeService` (task 5.1) over an
   in-memory ``DatabaseManager`` fake (the ``FakeDB`` shape from
   ``backend/tests/unit/test_user_tenant_scope_service.py``) + a ``ParameterService`` fake
   carrying ``members.scope_dimensions`` (region: Noord/Zuid/Oost/West). Authoring a scope
   writes the ``user_tenant_scope`` row(s) and fires ``enqueue_sync``.
2. **Projection** — the REAL :class:`services.projection_sync.ProjectionSync` (tasks 3.2/3.4/
   3.5): ``sync_administration`` reads that ``user_tenant_scope`` state and, via the REAL
   :func:`services.projection_sync.build_scopegrant_rows`, writes the actual
   ``scopegrant#<email>#region`` row (and the ODx4b diff-delete on clear) into the in-memory
   projection table.
3. **SAM plane read** — the REAL
   :class:`sam.members.repository.projection_config_reader.MembersProjectionReader`
   (``get_scope_config`` + ``get_scope_grants``) reads those rows off the SAME table, and the
   REAL edge :func:`sam.members.handler.app._resolve_scope_access` resolves them to
   ``allowed_scopes = {"region": [...]}`` (via the REAL ``_scope_access_from_grant`` /
   ``resolve_scope_access``).
4. **SAM plane enforce** — the REAL
   :meth:`sam.members.domain.membership_service.MembershipService.list_members` over a
   ``FakeMembersRepository`` (Oost/Zuid/… members carrying ``overlay.region``) returns the
   visible set.

THE THREE TRANSITIONS (Properties 2/3 + ODx4)
---------------------------------------------
- ``region:["Oost"]``  → only Oost members visible (add/scoped).
- ``region:["*"]``     → ALL members visible (update to all-access, ODx4a version bump).
- clear (``{}``)       → NO members visible AND the ``scopegrant#…#region`` row is DELETED
                          from the projection (ODx4b diff-delete + deny-by-default, Property 3).

The KEY assertion at every hop: the sort key the projection writes
(``scopegrant#member-test@example.com#region``) is exactly what the reader keys off — the two
planes share ``services.projection_schema`` (imported by BOTH planes), so a drift in the row
shape would break this test.

Validates: Requirement 7.3 · design Properties 2/3.
"""

from __future__ import annotations

import os
import sys

import pytest

# The SAM suite already puts the repo root on sys.path (sam/tests/conftest.py); this test also
# needs backend/src so the Flask-plane objects (services.*) import in the SAME process as the
# SAM-plane ones — exactly the two-plane wiring R7.3's E2E demonstrates. Mirrors
# test_membership_service_reads.py's path setup.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
_BACKEND_SRC = os.path.join(_REPO_ROOT, "backend", "src")
if _BACKEND_SRC not in sys.path:
    sys.path.insert(0, _BACKEND_SRC)

# ── Flask/MySQL plane (real code) ─────────────────────────────────────────────────────
from services import projection_schema as schema
from services.module_registry import MODULE_REGISTRY
from services.projection_sync import (
    ProjectionSync,
    TenantSource,
)
from services.user_tenant_scope_service import UserTenantScopeService

# ── SAM plane (real code) ──────────────────────────────────────────────────────────────
from sam.members.domain.membership_service import MembershipService
from sam.members.handler import app as members_app
from sam.members.handler.routes import ROUTES
from sam.members.repository.projection_config_reader import MembersProjectionReader

# ── Fixtures for both planes' in-memory fakes ──────────────────────────────────────────
from sam.tests.test_membership_service_reads import FakeMembersRepository


TENANT = "h-dcn"
MODULE = "MEMBERS"
EMAIL = "member-test@example.com"


# ---------------------------------------------------------------------------
# Fakes — the TRUE I/O boundaries only (MySQL, ParameterService, DynamoDB table)
# ---------------------------------------------------------------------------


class FakeDB:
    """In-memory ``DatabaseManager`` stand-in for ``user_tenant_scope`` (Flask plane).

    Models the SELECT / INSERT..ON DUPLICATE KEY UPDATE / DELETE the
    :class:`UserTenantScopeService` issues, keyed on the table's UNIQUE
    ``(email, administration, module)``, PLUS the projection sync's read
    ``SELECT email, module, scopes, updated_at FROM user_tenant_scope WHERE administration``
    so the SAME store feeds BOTH the authoring service and the projection source-provider.
    Copied in spirit from ``backend/tests/unit/test_user_tenant_scope_service.py``'s FakeDB.
    """

    def __init__(self):
        # (email, administration, module) -> scopes-json (str)
        self.rows: dict[tuple[str, str, str], str] = {}
        # Per-row monotonic version, standing in for the table's ON UPDATE CURRENT_TIMESTAMP.
        self._versions: dict[tuple[str, str, str], int] = {}
        self._clock = 0

    def execute_query(self, query, params=None, fetch=False, commit=False):
        params = tuple(params or ())
        q = " ".join(query.split()).upper()

        # Authoring-service reads: single (email, admin, module) row.
        if q.startswith("SELECT SCOPES FROM USER_TENANT_SCOPE"):
            email, admin, module = params
            key = (email, admin, module)
            return [{"scopes": self.rows[key]}] if key in self.rows else []

        # Projection source-provider read: all rows for a tenant (the s5d grant source).
        if q.startswith("SELECT EMAIL, MODULE, SCOPES, UPDATED_AT FROM USER_TENANT_SCOPE"):
            admin = params[0] if params else None
            out = []
            for (email, a, module), scopes_json in self.rows.items():
                if a == admin:
                    out.append(
                        {
                            "email": email,
                            "module": module,
                            "scopes": scopes_json,
                            # A per-row freshness signal advances on every write so an
                            # UPDATED grant supersedes the stored scopegrant row (ODx4a).
                            "updated_at": self._version_of(email, a, module),
                        }
                    )
            return out

        if q.startswith("INSERT INTO USER_TENANT_SCOPE"):
            email, admin, module, scopes_json, _created_by = params
            self._clock += 1
            self.rows[(email, admin, module)] = scopes_json
            self._versions[(email, admin, module)] = self._clock
            return None

        if q.startswith("DELETE FROM USER_TENANT_SCOPE"):
            email, admin, module = params
            self.rows.pop((email, admin, module), None)
            self._versions.pop((email, admin, module), None)
            return None

        raise AssertionError(f"Unexpected query: {query}")

    def _version_of(self, email, admin, module):
        return self._versions.get((email, admin, module), 0)


class FakeParameterService:
    """Read-only ``members.scope_dimensions`` provider shared by BOTH planes.

    The authoring service (validation) and the projection builder read the SAME
    ``(members, scope_dimensions, tenant)`` param, so wiring one fake proves both planes
    agree on the dimension vocabulary (D4 — the single source of truth).
    """

    def __init__(self, dimensions_by_tenant):
        self._dims = dimensions_by_tenant

    def get_param(self, namespace, key, tenant=None, role=None, user=None):
        # The authoring service + the scopegrant builder read (members, scope_dimensions);
        # the projection also builds config#fields / config#views (members.field_overlay /
        # members.view_contexts) — those are un-authored here → None (empty-is-valid).
        if namespace == "members" and key == "scope_dimensions":
            return self._dims.get(tenant)
        return None


class ProjectionFakeTable:
    """In-memory projection table serving BOTH the Flask WRITER and the SAM READER.

    The single table both planes share. It satisfies:

    - :class:`ProjectionSync` (the WRITER): ``get_item`` / ``put_item`` (with the
      conditional-version guarantee a real table enforces) + the ODx4b reconcile's
      ``query`` (``#pk = :pk AND begins_with(#sk, :sk_prefix)``) / ``delete_item``.
    - :class:`MembersProjectionReader` (the READER): ``query`` with a boto3
      ``Key(tenant_id).eq(...)`` ``KeyConditionExpression`` object.

    Both ``query`` shapes are handled so the exact rows the sync writes are the exact rows
    the reader consumes — the cross-plane contract R7.3 validates. Semantics mirror
    ``backend/tests/unit/test_projection_sync.py``'s ``FakeTable``.
    """

    def __init__(self):
        self.store: dict[tuple, dict] = {}

    class _Meta:
        class _Client:
            pass

        client = _Client()

    meta = _Meta()

    def _key_tuple(self, key_or_item):
        return (key_or_item[schema.PARTITION_KEY_ATTR], key_or_item[schema.SORT_KEY_ATTR])

    def get_item(self, Key):
        item = self.store.get(self._key_tuple(Key))
        return {"Item": dict(item)} if item is not None else {}

    def put_item(
        self,
        Item,
        ConditionExpression=None,
        ExpressionAttributeNames=None,
        ExpressionAttributeValues=None,
    ):
        if ConditionExpression is not None:
            existing = self.store.get(self._key_tuple(Item))
            incoming = (ExpressionAttributeValues or {}).get(":incoming")
            if existing is not None:
                stored_version = existing.get(schema.VERSION_ATTR)
                if stored_version is not None and not (stored_version < incoming):
                    raise _conditional_check_failed()
        self.store[self._key_tuple(Item)] = dict(Item)
        return {}

    def delete_item(self, Key):
        self.store.pop(self._key_tuple(Key), None)
        return {}

    def query(
        self,
        KeyConditionExpression=None,
        ExpressionAttributeNames=None,
        ExpressionAttributeValues=None,
        ExclusiveStartKey=None,
    ):
        pk, sk_prefix = self._resolve_key_condition(
            KeyConditionExpression, ExpressionAttributeValues
        )
        items = []
        for (tenant_id, sk), stored in self.store.items():
            if tenant_id != pk:
                continue
            if sk_prefix is not None and not sk.startswith(sk_prefix):
                continue
            items.append(dict(stored))
        return {"Items": items}

    @staticmethod
    def _resolve_key_condition(key_condition_expression, expression_attribute_values):
        """Resolve (partition, sk_prefix) from EITHER call shape.

        - The Flask sync's reconcile passes a raw ``#pk = :pk AND begins_with(#sk, :sk_prefix)``
          string + ``ExpressionAttributeValues`` (``:pk`` / ``:sk_prefix``).
        - The SAM reader passes a boto3 ``Key(tenant_id).eq(tenant)`` condition object (no
          values dict); its ``.get_expression()`` carries the tenant in ``values[1]``.
        """
        values = expression_attribute_values or {}
        if ":pk" in values:
            return values.get(":pk"), values.get(":sk_prefix")
        # boto3 ConditionBase (the reader's Key(...).eq(tenant) — partition only, no prefix).
        get_expression = getattr(key_condition_expression, "get_expression", None)
        if get_expression is not None:
            expr = get_expression()
            return expr["values"][1], None
        return None, None


def _conditional_check_failed():
    err = Exception("The conditional request failed")
    err.response = {"Error": {"Code": "ConditionalCheckFailedException"}}
    return err


# ---------------------------------------------------------------------------
# The authored dimension config + members (shared vocabulary, D4)
# ---------------------------------------------------------------------------


def _region_dimension():
    """h-dcn's ``region`` dimension as authored ``members.scope_dimensions`` data (s5d shape).

    No ``Regio_*`` / ``multi_valued`` (clean break, R2.2/R8.1); binds to the member ``region``
    field and declares the canonical value set the authoring service + projection validate
    against.
    """
    return {
        "key": "region",
        "field": "region",
        "label": {"nl": "Regio", "en": "Region"},
        "enabled": True,
        "values": ["Noord", "Zuid", "Oost", "West"],
        "required_for": ["Members_CRUD"],
    }


@pytest.fixture
def params():
    return FakeParameterService({TENANT: [_region_dimension()]})


@pytest.fixture
def db():
    return FakeDB()


@pytest.fixture
def projection_table():
    return ProjectionFakeTable()


@pytest.fixture
def members_repo():
    """A tenant of members across four regions (each carrying the plain ``overlay.region``)."""
    from sam.tests.test_membership_service_reads import _member

    repo = FakeMembersRepository()
    repo.add_member(TENANT, _member("M-OOST", region="Oost", name="Oost Person"))
    repo.add_member(TENANT, _member("M-ZUID", region="Zuid", name="Zuid Person"))
    repo.add_member(TENANT, _member("M-NOORD", region="Noord", name="Noord Person"))
    repo.add_member(TENANT, _member("M-WEST", region="West", name="West Person"))
    # A different tenant — must never be visible to h-dcn (structural isolation).
    repo.add_member("other", _member("M-OTHER", region="Oost", name="Other Tenant"))
    return repo


@pytest.fixture
def sam_module(monkeypatch):
    """Register MEMBERS as a SAM-backed module so the sync builds the C2 config rows.

    ``sync_administration`` only builds the Members ``config#scope`` / ``scopegrant#…`` rows
    when the tenant has a SAM-backed module enabled. Mirrors ``test_projection_sync.py``'s
    ``sam_module`` fixture (a temporary registry entry, so the shipped registry is untouched).
    """
    entry = {
        "description": "Members module (E2E)",
        "required_params": {},
        "required_tax_rates": [],
        "required_roles": ["Members_CRUD"],
        "backing": {
            "kind": "sam",
            "api_base_env": "MEMBERS_API_BASE",
            "data_namespace": "members",
        },
    }
    monkeypatch.setitem(MODULE_REGISTRY, MODULE, entry)
    return MODULE


# ---------------------------------------------------------------------------
# The wiring — real objects across the seam
# ---------------------------------------------------------------------------


class ScopeE2E:
    """Wires the two planes over the shared fakes and drives the four-hop chain.

    Holds the REAL :class:`UserTenantScopeService` (author), the REAL
    :class:`ProjectionSync` (project), and the REAL :class:`MembershipService` (enforce) over
    a REAL :class:`MembersProjectionReader` — only the MySQL / param / DynamoDB boundaries are
    faked.
    """

    def __init__(self, db, params, projection_table, members_repo, module_name):
        self._db = db
        self._params = params
        self._table = projection_table
        self._module_name = module_name

        # Hop 1 — authoring service (real). enqueue_sync is wired straight to hop 2 so a
        # write triggers a real projection sync, exactly like production's on-change trigger.
        self.author = UserTenantScopeService(
            db, params, enqueue_sync=self._resync
        )

        # Hop 2 — projection sync (real) over an in-memory source that reads the SAME FakeDB.
        self._sync = ProjectionSync(
            _E2ESourceProvider(db, module_name),
            table=projection_table,
            parameter_service=params,
        )

        # Hop 3 — the SAM projection reader (real) over the SAME table. One instance is fine
        # per resolve; scope reads build a fresh reader (fresh per-invocation cache) like the
        # edge does in production.
        self._members_repo = members_repo

    def _resync(self, administration):
        """The on-change trigger: run a real full re-projection for the tenant (add/update/
        remove all propagate — ODx4a version bump + ODx4b diff-delete)."""
        self._sync.sync_administration(administration)

    # -- hop 1: author a scope (drives 1 -> 2 via enqueue_sync) -----------------------
    def set_scope(self, scopes):
        return self.author.set_scope(EMAIL, TENANT, MODULE, scopes)

    # -- hop 3: resolve allowed_scopes at the REAL edge from the projected rows -------
    def resolve_allowed_scopes(self):
        reader = MembersProjectionReader(table=self._table)
        # Use the REAL shipped list_members route spec (the edge passes it through to the
        # scope seam; the resolution is data-driven off the projected config, not the spec).
        spec = next(s for s in ROUTES if s.name == "list_members")
        claims = {"email": EMAIL}
        return members_app._resolve_scope_access(
            spec,
            TENANT,
            claims,
            config_provider=reader,
            grants_reader=reader,
        )

    # -- hop 4: enforce — REAL list_members narrowed by the resolved scope ------------
    def visible_member_ids(self):
        allowed = self.resolve_allowed_scopes()
        service = MembershipService(self._members_repo)
        members = service.list_members(TENANT, allowed)
        return sorted(m["member_id"] for m in members)

    # -- projection introspection (the cross-plane contract) --------------------------
    def scopegrant_sort_key(self):
        return schema.build_sort_key(schema.RECORD_TYPE_SCOPEGRANT, EMAIL, "region")

    def scopegrant_row(self):
        return self._table.store.get((TENANT, self.scopegrant_sort_key()))


class _E2ESourceProvider:
    """A projection ``SourceProvider`` reading the SAME FakeDB the authoring service writes.

    Returns a :class:`TenantSource` whose ``user_tenant_scope`` is the tenant's rows straight
    out of the shared FakeDB — so the projection's grant source is literally what hop 1 wrote,
    not a separate copy. Only the one tenant the E2E drives is known.
    """

    def __init__(self, db, module_name):
        self._db = db
        self._module_name = module_name

    def list_administrations(self):
        return [TENANT]

    def get_tenant_source(self, administration):
        if administration != TENANT:
            return None
        scope_rows = self._db.execute_query(
            "SELECT email, module, scopes, updated_at FROM user_tenant_scope "
            "WHERE administration = %s",
            (administration,),
            fetch=True,
        )
        return TenantSource(
            tenant={"administration": administration, "display_name": "h-dcn", "version": 1},
            tenant_modules=[
                {"module_name": self._module_name, "is_active": True, "version": 1}
            ],
            user_tenant_roles=[],
            user_tenant_scope=scope_rows,
        )


@pytest.fixture
def e2e(db, params, projection_table, members_repo, sam_module):
    return ScopeE2E(db, params, projection_table, members_repo, sam_module)


# ---------------------------------------------------------------------------
# The E2E — the three transitions (Properties 2/3, ODx4)
# ---------------------------------------------------------------------------


def test_scope_oost_projects_scopegrant_and_lists_only_oost(e2e):
    """Transition 1: Tenant-Admin sets region:["Oost"] → projection carries
    scopegrant#…#region=["Oost"] → list_members returns ONLY Oost members (R7.3, Property 2)."""
    e2e.set_scope({"region": ["Oost"]})

    # Hop 2 contract: the projection WROTE the scopegrant row the SAM reader keys off.
    row = e2e.scopegrant_row()
    assert row is not None, "the projection must carry the scopegrant row after authoring"
    assert row[schema.SORT_KEY_ATTR] == "scopegrant#member-test@example.com#region"
    assert row["dimension"] == "region"
    assert row["values"] == ["Oost"]

    # Hop 3 contract: the REAL edge resolves that row to the per-dimension allowed_scopes map.
    assert e2e.resolve_allowed_scopes() == {"region": ["Oost"]}

    # Hop 4 contract: list_members returns ONLY the Oost member (and never the other tenant).
    assert e2e.visible_member_ids() == ["M-OOST"]


def test_scope_wildcard_lists_all_members(e2e):
    """Transition 2: changing the grant to ["*"] returns ALL members (all-access, ODx4a)."""
    e2e.set_scope({"region": ["Oost"]})
    assert e2e.visible_member_ids() == ["M-OOST"]

    # Update to all-access. The per-row version bump (ODx4a) supersedes the stored row.
    e2e.set_scope({"region": ["*"]})

    row = e2e.scopegrant_row()
    assert row is not None and row["values"] == ["*"], "the grant must project as all-access"
    assert e2e.resolve_allowed_scopes() == {"region": ["*"]}
    # Every h-dcn member is visible; the other tenant's member is still structurally invisible.
    assert e2e.visible_member_ids() == ["M-NOORD", "M-OOST", "M-WEST", "M-ZUID"]


def test_clear_deletes_scopegrant_and_lists_none(e2e):
    """Transition 3: clearing the grant DELETES the scopegrant row (ODx4b) → NO members
    visible (deny-by-default, Property 3)."""
    e2e.set_scope({"region": ["Oost"]})
    assert e2e.scopegrant_row() is not None

    # Clear all selections → the authoring service deletes the user_tenant_scope row and the
    # projection's diff-and-delete removes the now-obsolete scopegrant row (ODx4b).
    e2e.set_scope({})

    assert e2e.scopegrant_row() is None, "the obsolete scopegrant row must be deleted (ODx4b)"
    # Deny-by-default: an absent grant → empty allowed_scopes for the dimension → sees nothing.
    assert e2e.resolve_allowed_scopes() == {"region": []}
    assert e2e.visible_member_ids() == []


def test_full_add_update_remove_lifecycle_over_one_projection(e2e):
    """The whole ODx4 lifecycle over ONE shared projection table: add → update → remove all
    propagate through the SAME real chain (proves the on-change trigger is correct end-to-end)."""
    # add (scoped)
    e2e.set_scope({"region": ["Oost"]})
    assert e2e.visible_member_ids() == ["M-OOST"]

    # update (all-access)
    e2e.set_scope({"region": ["*"]})
    assert e2e.visible_member_ids() == ["M-NOORD", "M-OOST", "M-WEST", "M-ZUID"]

    # downgrade (a different single region — proves an UPDATE supersedes, not just widens)
    e2e.set_scope({"region": ["Zuid"]})
    assert e2e.scopegrant_row()["values"] == ["Zuid"]
    assert e2e.visible_member_ids() == ["M-ZUID"]

    # remove (clear → deny)
    e2e.set_scope({})
    assert e2e.scopegrant_row() is None
    assert e2e.visible_member_ids() == []
