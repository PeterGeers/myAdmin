"""
S5c Task 3.5 — tests for the task-3.4 **generic-placeholder view-contexts seed**
(``sam/members/domain/seed_view_contexts.py``; design C-VIEW, R5.1 / R4.5 / Property 7).

Feature: s5c-members-runnable-in-spa, Property 7 (view-context reference resolution — seed leg).

Validates: Requirements 5.1, 5.1a

What this asserts
-----------------
Task 3.4 ships an ILLUSTRATIVE onboarding starter for ``members.view_contexts`` as DATA. The
close-out of Phase 3 (task 3.5) pins three things about that seed — the parts a renderer's
"skip unresolvable key" path (Property 7) and the empty-is-valid default depend on:

1. **Property 7 (seed leg) — every seed ``field_key`` resolves against the generic field set.**
   The platform seed must reference ONLY keys that resolve in the *generic* field set the
   platform ships: the Fixed fields ⊕ the Calculated fields ⊕ the two task-1.4 generic-
   placeholder overlay fields (``field_a`` / ``field_b``). So no seed context's ``columns`` /
   ``filterable_columns`` / ``default_sort.field`` can ever be silently dropped by the render-
   time skip — the whole context always renders. This is the concrete, non-crashing side of
   Property 7 for the shipped seed.

2. **Tenant-agnostic (R4.5).** The seed references no real tenant's field list (no ``iban`` /
   ``motor_type`` / ``region`` etc.) and carries no ``if tenant == "h-dcn"`` vocabulary — it
   uses only platform-generic / placeholder keys.

3. **Seed round-trips the provider/reader path + is well-formed.** ``build_seed_view_contexts``
   consumes the same projection-shaped list a real tenant's data flows through, so the seed and
   the JSON stay in lock-step; and a :class:`StaticViewContextsProvider` seeded with it yields
   exactly those contexts (never collapsing to the empty-is-valid default), while a tenant that
   authored NONE still gets exactly one default context.

The generic field set is built with the REAL domain resolver over the REAL task-1.4 seed
overlay (``FieldResolver(StaticOverlayProvider({t: build_seed_overlay()})).resolve(t)``) — no
mocks, so the "resolves" assertion is a genuine cross-check between the two task-3.4 / task-1.4
seeds, not a restatement of a hardcoded list.

No live AWS, no MySQL: the seed and the resolver are pure domain logic.
"""

import os
import sys

# repo root on sys.path (mirrors sam/conftest.py) so `sam.members` imports when run
# directly / from within sam/.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from sam.members.domain.field_resolver import (
    FieldResolver,
    StaticOverlayProvider,
)
from sam.members.domain.seed_overlay import build_seed_overlay
from sam.members.domain.seed_view_contexts import (
    SEED_VIEW_CONTEXTS,
    build_seed_view_contexts,
    seed_view_contexts_list,
)
from sam.members.domain.view_contexts import (
    DEFAULT_CONTEXT_KEY,
    ViewContext,
    StaticViewContextsProvider,
)

_TENANT_ID = "seed-tenant"


def _generic_field_keys() -> frozenset[str]:
    """The generic field-set keys a seed reference may resolve against.

    Built with the REAL resolver over the REAL task-1.4 generic-placeholder overlay: the Fixed
    base ⊕ Calculated fields ⊕ the two seeded overlay fields (``field_a`` / ``field_b``). Uses
    the short ``ResolvedField.key`` — the exact key form the served ``field-config`` ``fields``
    list carries and the renderer resolves view-context columns against.
    """
    provider = StaticOverlayProvider({_TENANT_ID: build_seed_overlay()})
    config = FieldResolver(provider).resolve(_TENANT_ID)
    return frozenset(f.key for f in config.fields)


def _seed_referenced_keys(ctx: dict) -> set[str]:
    """Every ``field_key`` a single seed context references (columns + filterable + sort)."""
    keys: set[str] = set()
    keys.update(ctx.get("columns") or ())
    keys.update(ctx.get("filterable_columns") or ())
    default_sort = ctx.get("default_sort")
    if isinstance(default_sort, dict) and default_sort.get("field"):
        keys.add(default_sort["field"])
    return keys


# ── Property 7 (seed leg): every seed field_key resolves ──────────────────────────────


class TestSeedFieldKeysResolve:
    def test_every_seed_field_key_resolves_against_the_generic_field_set(self):
        """Feature: s5c-members-runnable-in-spa, Property 7 (seed leg).

        Validates: Requirements 5.1, 5.1a

        Every ``columns`` / ``filterable_columns`` / ``default_sort.field`` entry in EVERY
        seeded context is a key that resolves in the fixed ⊕ calculated ⊕ task-1.4 overlay
        field set, so the render-time "skip unresolvable key" (Property 7) never silently drops
        a seeded column — the shipped starter always renders in full.
        """
        resolvable = _generic_field_keys()

        dangling: dict[str, set[str]] = {}
        for ctx in seed_view_contexts_list():
            missing = _seed_referenced_keys(ctx) - resolvable
            if missing:
                dangling[ctx["key"]] = missing

        assert not dangling, (
            "seed view contexts reference field keys that do NOT resolve in the generic "
            f"field set (Property 7 would silently drop them): {dangling}. "
            f"resolvable keys = {sorted(resolvable)}"
        )

    def test_seed_references_a_calculated_and_an_overlay_placeholder_key(self):
        """The seed is a MEANINGFUL cross-check: it exercises non-fixed key kinds.

        Guards against the resolve test degenerating into "fixed keys only" — the seed
        references at least one Calculated field (``display_name``) and at least one task-1.4
        generic-placeholder overlay field (``field_a`` / ``field_b``), the exact kinds a
        parameter-driven config must be able to reference with no code change (Property 7).
        """
        referenced: set[str] = set()
        for ctx in seed_view_contexts_list():
            referenced |= _seed_referenced_keys(ctx)

        assert "display_name" in referenced  # a Calculated field
        assert referenced & {"field_a", "field_b"}  # a task-1.4 overlay placeholder


# ── Tenant-agnostic (R4.5) ─────────────────────────────────────────────────────────────


class TestSeedIsTenantAgnostic:
    def test_seed_references_no_real_tenant_field_vocabulary(self):
        """R4.5: the platform seed uses generic placeholders, never a real tenant's field list."""
        # h-dcn's real overlay vocabulary (authored as DATA at onboarding) must NOT leak into
        # the platform seed.
        forbidden = {
            "iban",
            "payment_method",
            "motor_brand",
            "motor_type",
            "build_year",
            "license_plate",
            "guardian_name",
            "region",
            "signature_date",
        }
        referenced: set[str] = set()
        for ctx in seed_view_contexts_list():
            referenced |= _seed_referenced_keys(ctx)

        assert not (referenced & forbidden), (
            "seed leaks real-tenant field vocabulary (R4.5): "
            f"{sorted(referenced & forbidden)}"
        )

    def test_no_context_key_uses_the_reserved_default_sentinel(self):
        """A seeded context is always an AUTHORED context, never the empty-is-valid default."""
        keys = [ctx["key"] for ctx in seed_view_contexts_list()]
        assert DEFAULT_CONTEXT_KEY not in keys


# ── Seed round-trips the provider path + is well-formed ──────────────────────────────


class TestSeedRoundTripsAndShape:
    def test_build_seed_view_contexts_matches_the_list_in_lockstep(self):
        """``build_seed_view_contexts`` is built FROM ``seed_view_contexts_list`` (lock-step)."""
        contexts = build_seed_view_contexts()
        raw = seed_view_contexts_list()

        assert all(isinstance(c, ViewContext) for c in contexts)
        assert [c.key for c in contexts] == [r["key"] for r in raw]
        # Every projection-shaped field survives the domain-object build unchanged.
        for c, r in zip(contexts, raw):
            assert dict(c.label) == r["label"]
            assert list(c.permission_roles) == r["permission_roles"]
            assert list(c.columns) == r["columns"]
            assert list(c.filterable_columns) == r["filterable_columns"]
            assert c.default_sort == r["default_sort"]
            assert c.page_size == r["page_size"]

    def test_seed_has_an_overview_and_a_role_restricted_specialized_context(self):
        """The seed models the "overview + one specialized" pattern the renderer tests use."""
        contexts = {c.key: c for c in build_seed_view_contexts()}
        assert "overview" in contexts
        # overview is broadly visible to both member roles (view-convenience gate).
        assert set(contexts["overview"].permission_roles) == {"Members_Read", "Members_CRUD"}

        # Exactly one specialized context, and it is role-restricted (Members_CRUD only) — so a
        # Members_Read-only user is gated out of it in the dropdown (matches the 3.3 renderer).
        specialized = [c for k, c in contexts.items() if k != "overview"]
        assert len(specialized) == 1
        assert tuple(specialized[0].permission_roles) == ("Members_CRUD",)

    def test_static_provider_seeded_with_the_seed_yields_exactly_it(self):
        """A provider seeded with the starter yields those contexts (no default collapse)."""
        provider = StaticViewContextsProvider(
            {_TENANT_ID: list(build_seed_view_contexts())}
        )
        resolved = provider.get_view_contexts(_TENANT_ID)

        assert [c.key for c in resolved] == [c["key"] for c in seed_view_contexts_list()]
        assert all(c.key != DEFAULT_CONTEXT_KEY for c in resolved)

    def test_tenant_without_the_seed_collapses_to_one_default_context(self):
        """Empty-is-valid: a tenant that authored NO contexts still gets exactly one default."""
        provider = StaticViewContextsProvider({})  # nobody seeded
        resolved = provider.get_view_contexts("some-other-tenant")

        assert len(resolved) == 1
        assert resolved[0].key == DEFAULT_CONTEXT_KEY
        assert resolved[0].is_default is True

    def test_seed_list_and_constant_are_consistent(self):
        """The projection-shaped list is derived from the ``SEED_VIEW_CONTEXTS`` constant 1:1."""
        assert [c["key"] for c in seed_view_contexts_list()] == [
            c["key"] for c in SEED_VIEW_CONTEXTS
        ]
