"""
S5 Task 4.2 — tests for the h-dcn **Lidmaatschap Beheer catalog seed** (dry-run first, tenant DATA).

Three layers, none of which touch live AWS (per the task constraints):

- **The seed DATA** (``HDCN_MEMBERSHIP_TYPES``): every entry validates, is active + owned by
  ``h-dcn``, carries real nl/en labels + a sensible order, and its ``type_code`` set COVERS
  every code the task-4.1 backfill can emit (``BACKFILL_EMITTABLE_CODES``, derived from the
  SAME mapper) — so a backfilled member can never reference an unseeded type (C8).
- **The pure planner** (``build_seed_plan``): diffs the seed against a repository's current
  catalog into create / update / unchanged, non-destructively.
- **The runner** (``scripts/aws/seed-hdcn-catalog.py``): dry-run writes NOTHING and emits a
  plan; ``--apply`` upserts via ``save_membership_type`` on a fake repository; a re-seed is
  idempotent (all unchanged, nothing written).

DynamoDB is faked with the same in-memory ``FakeDynamoTable`` / ``FakeDynamoClient`` used by
``test_members_repository.py`` — no moto, no live AWS — so the repository's real catalog
read/write path (``list_membership_types`` / ``save_membership_type``) is genuinely exercised.

Validates: Requirements R2.4, R4.1 (design C8 Lidmaatschap Beheer catalog; Property 5 —
the generic core stays tenant-agnostic, h-dcn's types live as seed DATA)
"""

from __future__ import annotations

import importlib.util
import os
import sys

import pytest

# repo root + backend/src on sys.path (mirrors sam/conftest.py + the other sam tests).
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
_BACKEND_SRC = os.path.join(_REPO_ROOT, "backend", "src")
if _BACKEND_SRC not in sys.path:
    sys.path.insert(0, _BACKEND_SRC)

from sam.members.domain.membership_type_catalog import MembershipTypeEntry
from sam.members.migration.hdcn_backfill import (
    HDCN_TENANT_ID,
    MembershipTypeMapper,
    map_hdcn_row,
)
from sam.members.migration.hdcn_catalog_seed import (
    BACKFILL_EMITTABLE_CODES,
    HDCN_MEMBERSHIP_TYPES,
    build_seed_plan,
)
from sam.members.repository import table_design as td
from sam.members.repository.members_repository import DynamoDbMembersRepository

# Reuse the faithful in-memory DynamoDB fakes from the repository tests.
_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)

from test_members_repository import FakeDynamoTable  # noqa: E402


# ---------------------------------------------------------------------------
# The seed DATA — well-formed + aligned with the 4.1 backfill mapping
# ---------------------------------------------------------------------------


class TestSeedData:
    def test_every_seed_entry_validates(self):
        for entry in HDCN_MEMBERSHIP_TYPES:
            entry.validate()  # raises MembershipTypeValidationError on a bad entry

    def test_all_entries_owned_by_the_pilot_tenant(self):
        assert all(e.tenant_id == HDCN_TENANT_ID == "h-dcn" for e in HDCN_MEMBERSHIP_TYPES)

    def test_all_entries_seeded_active(self):
        # Seeding sets active=True; retiring later is a soft-delete (not this task).
        assert all(e.active is True for e in HDCN_MEMBERSHIP_TYPES)

    def test_type_codes_are_unique(self):
        codes = [e.type_code for e in HDCN_MEMBERSHIP_TYPES]
        assert len(codes) == len(set(codes))

    def test_labels_carry_nl_and_en(self):
        for e in HDCN_MEMBERSHIP_TYPES:
            assert e.label.get("nl", "").strip()
            assert e.label.get("en", "").strip()

    def test_orders_are_distinct_integers(self):
        orders = [e.order for e in HDCN_MEMBERSHIP_TYPES]
        assert all(isinstance(o, int) and not isinstance(o, bool) for o in orders)
        assert len(orders) == len(set(orders))  # a stable, unambiguous presentation order

    def test_expected_hdcn_types_present(self):
        by_code = {e.type_code: e for e in HDCN_MEMBERSHIP_TYPES}
        assert by_code["erelid"].label["nl"] == "Erelid"
        assert by_code["donateur"].label["nl"] == "Donateur"
        assert by_code["sponsor"].label["nl"] == "Sponsor"
        assert by_code["gewoon_lid"].label["nl"] == "Gewoon lid"


class TestSeedAlignsWithBackfill:
    def test_seed_covers_every_backfill_emittable_code(self):
        # The core referential-integrity guarantee: no backfilled member references a type the
        # seed did not create. Codes come from the SAME mapper the backfill uses.
        seeded = {e.type_code for e in HDCN_MEMBERSHIP_TYPES}
        assert BACKFILL_EMITTABLE_CODES <= seeded

    def test_backfill_codes_derive_from_the_mapper_default_aliases(self):
        # Single source of truth: the expected set IS the mapper's alias codomain.
        assert BACKFILL_EMITTABLE_CODES == frozenset(
            MembershipTypeMapper.DEFAULT_ALIASES.values()
        )

    @pytest.mark.parametrize(
        "raw_label",
        ["Erelid", "Donateur", "Sponsor", "Gewoon lid", "honorary member", "lid"],
    )
    def test_backfilled_member_type_resolves_to_a_seeded_active_entry(self, raw_label):
        # End-to-end: a backfill row's membership_type maps to a code that IS an active seed
        # entry — the dropdown/reference check would resolve it (C8).
        row = {
            "member_id": "M-1",
            "lidnummer": "1001",
            "naam": "Alex de Vries",
            "email": "alex@example.com",
            "status": "actief",
            "lidmaatschapstype": raw_label,
            "ingangsdatum": "2010-01-01",
            "regio": "Noord",
        }
        code = map_hdcn_row(row)["membership"]["membership_type"]
        seeded = {e.type_code: e for e in HDCN_MEMBERSHIP_TYPES}
        assert code in seeded
        assert seeded[code].active is True


# ---------------------------------------------------------------------------
# The pure planner — build_seed_plan (non-destructive diff)
# ---------------------------------------------------------------------------


class TestBuildSeedPlan:
    def test_empty_catalog_all_create(self):
        plan = build_seed_plan([])
        assert len(plan.to_create) == len(HDCN_MEMBERSHIP_TYPES)
        assert plan.to_update == []
        assert plan.unchanged == []
        assert plan.tenant_id == "h-dcn"

    def test_full_catalog_all_unchanged(self):
        plan = build_seed_plan(list(HDCN_MEMBERSHIP_TYPES))
        assert plan.to_create == []
        assert plan.to_update == []
        assert len(plan.unchanged) == len(HDCN_MEMBERSHIP_TYPES)
        assert plan.to_write == []  # a re-seed writes nothing

    def test_changed_entry_is_an_update(self):
        existing = list(HDCN_MEMBERSHIP_TYPES)
        # Same code, different label → update (not create, not unchanged).
        idx = next(i for i, e in enumerate(existing) if e.type_code == "erelid")
        existing[idx] = MembershipTypeEntry(
            tenant_id="h-dcn", type_code="erelid", label={"nl": "OUD", "en": "OLD"}, order=99
        )
        plan = build_seed_plan(existing)
        assert [e.type_code for e in plan.to_update] == ["erelid"]

    def test_partial_catalog_creates_the_missing(self):
        existing = [e for e in HDCN_MEMBERSHIP_TYPES if e.type_code == "erelid"]
        plan = build_seed_plan(existing)
        created = {e.type_code for e in plan.to_create}
        assert "erelid" not in created
        assert {"donateur", "sponsor", "gewoon_lid"} <= created

    def test_existing_non_seed_entry_is_untouched(self):
        # A tenant-added type not in the seed is never reported for delete/deactivate.
        extra = MembershipTypeEntry(
            tenant_id="h-dcn", type_code="jeugdlid", label={"nl": "Jeugdlid"}, order=50
        )
        plan = build_seed_plan([extra])
        all_codes = {i.entry.type_code for i in plan.items}
        assert "jeugdlid" not in all_codes  # the plan only concerns the seed set


# ---------------------------------------------------------------------------
# The runner script — dry-run / --apply / idempotency
# ---------------------------------------------------------------------------


def _load_runner_module():
    """Import the hyphen-named runner script by path (not a valid module name)."""
    path = os.path.join(_REPO_ROOT, "scripts", "aws", "seed-hdcn-catalog.py")
    spec = importlib.util.spec_from_file_location("seed_hdcn_catalog", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runner = _load_runner_module()


@pytest.fixture()
def members_env(monkeypatch):
    """MEMBERS_TABLE + region set (fail-fast resolution passes); no endpoint (irrelevant here)."""
    monkeypatch.setenv(td.MEMBERS_TABLE_ENV_VAR, "sam-members-test")
    monkeypatch.setenv("AWS_REGION", "eu-west-1")
    monkeypatch.delenv("AWS_ENDPOINT_URL_DYNAMODB", raising=False)
    return monkeypatch


@pytest.fixture()
def fake_repo():
    """A real DynamoDbMembersRepository backed by the in-memory FakeDynamoTable."""
    table = FakeDynamoTable()
    return DynamoDbMembersRepository(table=table, client=table.meta.client)


class TestRunnerDryRun:
    def test_dry_run_writes_nothing(self, members_env, fake_repo):
        rc = runner.seed(region="eu-west-1", apply=False, repo=fake_repo)
        assert rc == 0
        # Nothing persisted — the tenant's catalog is still empty.
        assert list(fake_repo.list_membership_types("h-dcn")) == []

    def test_dry_run_emits_a_plan(self, members_env, fake_repo, capsys):
        runner.seed(region="eu-west-1", apply=False, repo=fake_repo)
        out = capsys.readouterr().out
        assert "seed plan" in out
        assert "DRY-RUN" in out
        assert "sam-members-test" in out              # resolved target table
        assert f"to create     : {len(HDCN_MEMBERSHIP_TYPES)}" in out
        assert "erelid" in out and "donateur" in out  # entries listed

    def test_apply_is_the_only_write_flag(self, members_env, fake_repo):
        # The argparse default for --apply is False, so a CLI run with no flag is dry-run.
        args = runner.build_parser().parse_args([])
        assert args.apply is False

    def test_fail_fast_when_members_table_missing(self, monkeypatch):
        # main([]) resolves MEMBERS_TABLE fail-fast BEFORE any write; a missing var → exit 1.
        monkeypatch.delenv(td.MEMBERS_TABLE_ENV_VAR, raising=False)
        monkeypatch.setenv("AWS_REGION", "eu-west-1")
        rc = runner.main([])
        assert rc == 1  # DynamoDBConfigError surfaced as exit 1


class TestRunnerApply:
    def test_apply_seeds_every_type(self, members_env, fake_repo, capsys):
        rc = runner.seed(region="eu-west-1", apply=True, repo=fake_repo)
        assert rc == 0
        stored = {e.type_code: e for e in fake_repo.list_membership_types("h-dcn")}
        assert set(stored) == {e.type_code for e in HDCN_MEMBERSHIP_TYPES}
        # Labels + active landed intact.
        assert stored["erelid"].label == {"nl": "Erelid", "en": "Honorary member"}
        assert all(e.active for e in stored.values())
        out = capsys.readouterr().out
        assert f"created   : {len(HDCN_MEMBERSHIP_TYPES)}" in out

    def test_apply_covers_all_backfill_codes(self, members_env, fake_repo):
        runner.seed(region="eu-west-1", apply=True, repo=fake_repo)
        active_codes = {
            e.type_code for e in fake_repo.list_membership_types("h-dcn", active_only=True)
        }
        # No backfilled member can reference a type that isn't a LIVE seeded entry (C8).
        assert BACKFILL_EMITTABLE_CODES <= active_codes

    def test_apply_is_idempotent_reseed_writes_nothing(self, members_env, fake_repo, capsys):
        assert runner.seed(region="eu-west-1", apply=True, repo=fake_repo) == 0
        capsys.readouterr()  # drain
        # Re-seed the SAME set — everything is already present + identical.
        assert runner.seed(region="eu-west-1", apply=True, repo=fake_repo) == 0
        out = capsys.readouterr().out
        assert "created   : 0" in out
        assert "updated   : 0" in out
        assert f"unchanged : {len(HDCN_MEMBERSHIP_TYPES)}" in out
        # Still exactly one entry per type (upsert, not duplicated).
        assert len(fake_repo.list_membership_types("h-dcn")) == len(HDCN_MEMBERSHIP_TYPES)

    def test_apply_never_deactivates_or_deletes(self, members_env, fake_repo):
        runner.seed(region="eu-west-1", apply=True, repo=fake_repo)
        # A pre-existing tenant-added type stays present + active after a re-seed.
        extra = MembershipTypeEntry(
            tenant_id="h-dcn", type_code="jeugdlid", label={"nl": "Jeugdlid"}, order=50
        )
        fake_repo.save_membership_type("h-dcn", extra)
        runner.seed(region="eu-west-1", apply=True, repo=fake_repo)
        got = fake_repo.get_membership_type("h-dcn", "jeugdlid")
        assert got is not None and got.active is True
