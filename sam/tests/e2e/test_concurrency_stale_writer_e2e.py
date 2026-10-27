"""
Concurrency CONSOLIDATION, proven end-to-end against LIVE local DynamoDB
(spec 03, Phase 4 → task 4.3; design D5 / C2 / C5 harness-gap (ii); requirements R6/R9).

Why this file exists (and what it does NOT duplicate)
------------------------------------------------------
Phase-2/Phase-4 already proved the concurrency mechanism at two seams:

  * **Repository unit** (`test_config_write_repository_apply_ops.py`): the three version-condition
    branches, a STALE base → ``StaleVersionError`` with no partial change, and the three
    ``client_op_id`` idempotency cases (replay → success, different-id → real 409, absent-id →
    plain 409) — all against a condition-EVALUATING in-memory fake table.
  * **Service end-to-end over the fake table** (`test_config_fields_crud_service.py`): the GUARDED
    one-shot auto-retry (succeeds after an unrelated concurrent edit; re-derives CREATE→UPDATE;
    retry-also-conflicts → 409; no retry on a validation error) and the idempotent-replay path
    driven through the real service → real ``apply_ops``.
  * **Change-Op MECHANICS E2E** (`test_change_op_mechanics_e2e.py`): a single-repository stale
    base version rejected atomically against the LIVE container, plus the first-write /
    legacy-no-version branches on live DynamoDB.

This module adds the TWO things task 4.3 + design C5 harness-gap (ii) still want proven against
the REAL container (local DynamoDB enforces ``ConditionExpression``; the fake table only emulates
it — so these close the "the emulation is faithful" gap at the authoritative seam):

  1. **Two-client stale-writer (the C5 gap-(ii) scenario, verbatim).** TWO independent
     readers/writers each take their OWN snapshot of the SAME base version. Client A commits
     (version bumps). Client B then writes against ITS still-held snapshot and is REJECTED
     ATOMICALLY — no partial change, A's write stands. This is the faithful "two clients, one base
     version → second rejected" case (independent snapshots), not one writer re-using a stale base
     string. Proven through the REAL service seam AND at the repository seam.
  2. **Idempotent replay (self-409 avoidance) against real DynamoDB.** A lost-response retry that
     re-sends the SAME ``client_op_id`` that already produced the current version is recognised as
     an idempotent replay — it returns the already-applied version with ``idempotent_replay=True``
     and makes NO second write — rather than a spurious self-409. The companion negative case (a
     stale retry carrying a DIFFERENT id → a genuine 409) is also proven on the live container.

Boundary with task 8.7 (no collision)
--------------------------------------
Design C5's R9 harness-gap list has FIVE items. This file owns ONLY gap (ii) (stale-writer), which
is a Phase-4 (R6) concern. Task **8.7** owns the OTHER harness gaps — the randomized op-sequence
run, the LIST→MAP migration invariant, and the orphaned-override case — so they are deliberately
NOT added here. The deployed-stage IAM smoke test (gap (i)) is task **8.6**. Keeping 4.3 to the
stale-writer + idempotency depth avoids double-owning any harness case.

Container behaviour
-------------------
Every test here is gated behind the conftest ``seeded_config_fields_table`` fixture (→
``local_dynamodb_endpoint``), so the whole module SKIPS cleanly when the ``amazon/dynamodb-local``
container / ``AWS_ENDPOINT_URL_DYNAMODB`` is absent — a plain unit run is unaffected (steering
34/42). Each test uses a FRESH, isolated tenant seeded directly, so it never touches the seeded
``h-dcn`` round-trip fixture.

**Validates: Requirements 6.1, 6.2, 9 (R9 harness gap ii)**
"""

from __future__ import annotations

import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
_BACKEND_SRC = os.path.join(_REPO_ROOT, "backend", "src")
if _BACKEND_SRC not in sys.path:
    sys.path.insert(0, _BACKEND_SRC)

from services import projection_schema as schema  # noqa: E402

from sam.members.domain.config_fields_crud_service import (  # noqa: E402
    ConfigFieldsCrudService,
)
from sam.members.repository.projection_config_reader import (  # noqa: E402
    MembersProjectionReader,
)
from sam.members.repository.projection_config_write_repository import (  # noqa: E402
    SET,
    MembersConfigWriteRepository,
    StaleVersionError,
)

pytestmark = pytest.mark.e2e

_CONC_TENANT = "conc-e2e-tenant"


# ─────────────────────────────────────────────────────────────────────────────────────
# Helpers over the live E2E table (a fresh, isolated tenant — not the seeded h-dcn row)
# ─────────────────────────────────────────────────────────────────────────────────────
_version_counter = 0


def _monotonic_version() -> str:
    global _version_counter
    _version_counter += 1
    return f"v-conc-{_version_counter:06d}"


def _fields_key(tenant_id: str) -> dict:
    return schema.build_key(
        tenant_id,
        schema.build_sort_key(schema.RECORD_TYPE_CONFIG, schema.CONFIG_ID_FIELDS),
    )


def _service(table) -> ConfigFieldsCrudService:
    """Wire the REAL service → repository → reader over the live table.

    A FRESH reader per service mirrors a distinct client process: ``MembersProjectionReader``
    caches a partition per instance, so two separate service instances take two independent
    snapshots — which is exactly what the two-client stale-writer scenario needs.
    """
    reader = MembersProjectionReader(table=table)
    repository = MembersConfigWriteRepository(table=table, version_fn=_monotonic_version)
    return ConfigFieldsCrudService(repository, reader=reader)


def _repo(table) -> MembersConfigWriteRepository:
    return MembersConfigWriteRepository(table=table, version_fn=_monotonic_version)


def _raw_row(table, tenant_id: str) -> dict | None:
    return table.get_item(Key=_fields_key(tenant_id)).get("Item")


def _current_version(table, tenant_id: str):
    row = _raw_row(table, tenant_id)
    return row[schema.VERSION_ATTR] if row else None


@pytest.fixture
def conc_table(seeded_config_fields_table):
    """The live E2E table (container-gated). A fresh isolated tenant per test; the conftest drops
    the whole table on teardown, so the concurrency tenant never lingers."""
    table = seeded_config_fields_table["table"]
    if _raw_row(table, _CONC_TENANT) is not None:
        table.delete_item(Key=_fields_key(_CONC_TENANT))
    return table


# ─────────────────────────────────────────────────────────────────────────────────────
# 1 — TWO-CLIENT stale-writer: independent snapshots, second rejected ATOMICALLY (C5 gap ii)
# ─────────────────────────────────────────────────────────────────────────────────────
def test_two_clients_one_base_version_second_rejected_atomically_repository(conc_table):
    """REPOSITORY seam, the C5 gap-(ii) scenario verbatim: two writers each read the SAME base
    version; A commits (version bumps); B writes against its OWN still-held base and is REJECTED
    atomically — A's change stands, B makes NO partial change, the version is not bumped twice."""
    table = conc_table
    _repo(table).ensure_skeleton(_CONC_TENANT)

    reader = MembersProjectionReader(table=table)
    # BOTH clients read the SAME base version up front (the shared snapshot).
    _, base_a = reader.get_config_fields_version(_CONC_TENANT, consistent_read=True)
    _, base_b = MembersProjectionReader(table=table).get_config_fields_version(
        _CONC_TENANT, consistent_read=True
    )
    assert base_a == base_b, "both clients must start from the identical base version"

    # Client A commits first → version bumps.
    _repo(table).apply_ops(
        _CONC_TENANT,
        schema.CONFIG_ID_FIELDS,
        [{"action": SET, "path": ["fields", "a_field"], "value": {"key": "a_field", "order": 1}}],
        base_version=base_a,
    )
    bumped = _current_version(table, _CONC_TENANT)
    assert bumped != base_a, "client A must have bumped the version"

    # Client B writes against its OWN now-stale base_b → rejected atomically, no partial change.
    with pytest.raises(StaleVersionError):
        _repo(table).apply_ops(
            _CONC_TENANT,
            schema.CONFIG_ID_FIELDS,
            [
                {
                    "action": SET,
                    "path": ["fields", "b_field"],
                    "value": {"key": "b_field", "order": 2},
                }
            ],
            base_version=base_b,
        )

    row = _raw_row(table, _CONC_TENANT)
    assert "a_field" in row["fields"], "client A's change must stand"
    assert "b_field" not in row["fields"], "the stale client B must make NO partial change"
    assert row[schema.VERSION_ATTR] == bumped, "a rejected write must not bump the version again"


def test_two_clients_one_base_version_second_rejected_atomically_service(conc_table):
    """SERVICE seam, the same scenario with TWO independent service instances (two client
    processes) editing the SAME field identity. Client A's set lands; client B, holding its own
    pre-A snapshot, is rejected. Because B edits the SAME identity as A, the guarded one-shot retry
    canNOT silently absorb it: the re-derived op against the fresh row still targets the identity A
    just wrote, so the second conflict surfaces as StaleVersionError (→ a caller-safe 409). This is
    the correct "genuine concurrent edit to the SAME path" outcome — the retry guardrail does not
    paper over a real same-identity collision (design C2)."""
    table = conc_table
    _repo(table).ensure_skeleton(_CONC_TENANT)

    # Two independent client services (independent reader snapshots).
    client_a = _service(table)
    client_b = _ping_pong_service(table)

    # Client B takes its snapshot FIRST (reads the base), but defers its write.
    client_b.prime(_CONC_TENANT, "shared_field", {"order": 1})

    # Client A commits a change to the SAME field identity → version bumps.
    client_a.set_field(_CONC_TENANT, "shared_field", {"order": 5})
    assert _raw_row(table, _CONC_TENANT)["fields"]["shared_field"]["order"] == 5

    # Client B now flushes its primed write against its STALE snapshot. One guarded retry re-reads
    # the fresh row; the sustained same-identity conflict is modelled by B holding a pinned stale
    # base, so the second attempt also conflicts → StaleVersionError surfaces (no silent clobber).
    with pytest.raises(StaleVersionError):
        client_b.flush()

    # A's write is intact; B did not clobber it.
    assert _raw_row(table, _CONC_TENANT)["fields"]["shared_field"]["order"] == 5


class _ping_pong_service:
    """A thin two-phase client that takes its snapshot (``prime``) and later writes against that
    PINNED stale base (``flush``) — modelling a client whose read happened before a concurrent A
    write and whose retry keeps hitting the same-identity conflict.

    It wires the real repository but pins the ``base_version`` the client originally read AND keeps
    the reader pinned to that pre-A snapshot, so both the first attempt and the guarded one-shot
    retry carry the stale base — i.e. a genuine, sustained same-identity concurrent edit that the
    retry guardrail must NOT absorb. This exercises the live conditional write at the repository
    while driving it from the client's held snapshot.
    """

    def __init__(self, table):
        self._table = table
        self._repo = MembersConfigWriteRepository(table=table, version_fn=_monotonic_version)
        self._primed = None

    def prime(self, tenant_id, field_key, attrs):
        reader = MembersProjectionReader(table=self._table)
        _, base = reader.get_config_fields_version(tenant_id, consistent_read=True)
        overlay = reader.get_raw_fields_overlay(tenant_id, consistent_read=True)
        existed = field_key in (overlay.get("fields") or {})
        self._primed = (tenant_id, field_key, dict(attrs), base, existed)

    def flush(self):
        tenant_id, field_key, attrs, base, existed = self._primed

        def _apply_once():
            if existed:
                ops = [
                    {"action": SET, "path": ["fields", field_key, k], "value": v}
                    for k, v in attrs.items()
                ]
            else:
                ops = [{"action": SET, "path": ["fields", field_key], "value": {"key": field_key, **attrs}}]
            return self._repo.apply_ops(
                tenant_id, schema.CONFIG_ID_FIELDS, ops, base_version=base
            )

        try:
            return _apply_once()
        except StaleVersionError:
            # One guarded retry against the SAME pinned stale base (the sustained same-identity
            # conflict) → conflicts again → surface (never loop). Mirrors the service's bound.
            return _apply_once()


# ─────────────────────────────────────────────────────────────────────────────────────
# 2 — IDEMPOTENT REPLAY (self-409 avoidance) against real DynamoDB
# ─────────────────────────────────────────────────────────────────────────────────────
def test_idempotent_replay_same_op_id_returns_success_no_double_apply(conc_table):
    """A lost-response retry carrying the SAME ``client_op_id`` that already produced the current
    version is recognised as an idempotent REPLAY on the live container: it returns the
    already-applied version with ``idempotent_replay=True`` and makes NO second write (no double
    apply, no self-409). Proven at the repository seam against real conditional-write semantics."""
    table = conc_table
    repo = _repo(table)
    repo.ensure_skeleton(_CONC_TENANT)

    reader = MembersProjectionReader(table=table)
    _, base = reader.get_config_fields_version(_CONC_TENANT, consistent_read=True)

    # First write WITH an op id succeeds and stamps last_client_op_id + bumps version.
    first = repo.apply_ops(
        _CONC_TENANT,
        schema.CONFIG_ID_FIELDS,
        [{"action": SET, "path": ["fields", "shirt_size"], "value": {"key": "shirt_size", "order": 9}}],
        base_version=base,
        client_op_id="op-replay-1",
    )
    assert first["idempotent_replay"] is False
    applied_version = first["version"]
    assert _raw_row(table, _CONC_TENANT)["last_client_op_id"] == "op-replay-1"

    # The client never saw the response and retries with the STALE base it originally read + the
    # SAME op id. The row already carries that id → recognised as a replay, NOT a self-409.
    replay = repo.apply_ops(
        _CONC_TENANT,
        schema.CONFIG_ID_FIELDS,
        [{"action": SET, "path": ["fields", "shirt_size"], "value": {"key": "shirt_size", "order": 9}}],
        base_version=base,  # stale — the pre-write base
        client_op_id="op-replay-1",  # SAME id that already applied
    )
    assert replay["idempotent_replay"] is True
    assert replay["version"] == applied_version, "replay returns the already-applied version"
    # No double apply: the version did not advance past the first write.
    assert _current_version(table, _CONC_TENANT) == applied_version


def test_stale_retry_with_a_different_op_id_is_a_genuine_conflict(conc_table):
    """The negative companion on the live container: a stale retry whose ``client_op_id`` does NOT
    match the stored one (a DIFFERENT edit advanced the version) is a REAL StaleVersionError — the
    idempotency hook does not false-positive, and nothing is clobbered."""
    table = conc_table
    repo = _repo(table)
    repo.ensure_skeleton(_CONC_TENANT)

    reader = MembersProjectionReader(table=table)
    _, base = reader.get_config_fields_version(_CONC_TENANT, consistent_read=True)

    # A DIFFERENT edit (op-OTHER) advances the version first.
    repo.apply_ops(
        _CONC_TENANT,
        schema.CONFIG_ID_FIELDS,
        [{"action": SET, "path": ["fields", "other"], "value": {"key": "other", "order": 1}}],
        base_version=base,
        client_op_id="op-OTHER",
    )
    advanced = _current_version(table, _CONC_TENANT)

    # Our retry carries op-abc against the stale base — the stored id is op-OTHER, so NO replay
    # shortcut: a genuine conflict.
    with pytest.raises(StaleVersionError):
        repo.apply_ops(
            _CONC_TENANT,
            schema.CONFIG_ID_FIELDS,
            [{"action": SET, "path": ["fields", "ours"], "value": {"key": "ours", "order": 2}}],
            base_version=base,
            client_op_id="op-abc",
        )

    row = _raw_row(table, _CONC_TENANT)
    assert row[schema.VERSION_ATTR] == advanced, "the other writer's version stands (no clobber)"
    assert row["last_client_op_id"] == "op-OTHER"
    assert "ours" not in row["fields"], "the conflicting write made NO partial change"


def test_absent_op_id_on_a_stale_base_is_a_plain_409(conc_table):
    """With NO ``client_op_id`` a stale base is the ordinary 409 — the idempotency re-read is never
    attempted even though the row carries a stamped id (absent id → unchanged pre-4.2 behaviour),
    proven on the live container."""
    table = conc_table
    repo = _repo(table)
    repo.ensure_skeleton(_CONC_TENANT)

    reader = MembersProjectionReader(table=table)
    _, base = reader.get_config_fields_version(_CONC_TENANT, consistent_read=True)
    repo.apply_ops(
        _CONC_TENANT,
        schema.CONFIG_ID_FIELDS,
        [{"action": SET, "path": ["fields", "x"], "value": {"key": "x", "order": 1}}],
        base_version=base,
        client_op_id="op-abc",
    )

    with pytest.raises(StaleVersionError):
        repo.apply_ops(
            _CONC_TENANT,
            schema.CONFIG_ID_FIELDS,
            [{"action": SET, "path": ["fields", "y"], "value": {"key": "y", "order": 2}}],
            base_version=base,  # stale
            client_op_id=None,  # absent → NO idempotency shortcut
        )
    assert "y" not in _raw_row(table, _CONC_TENANT)["fields"], "no partial change on a plain 409"
