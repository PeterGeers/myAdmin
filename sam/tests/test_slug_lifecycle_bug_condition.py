"""
Bugfix spec `bugfix-slug-lifecycle` — Task 1: the bug-condition EXPLORATION test (backend facets).

Parent spec: `.kiro/specs/Members/14 - public-pages-multi-tenant-serving` (R1.2, R2.1, R2.3, R4).
Bugfix spec: `.kiro/specs/Members/14 .../bugfix-slug-lifecycle` (bugfix.md / design.md).

WHAT THIS TEST IS
-----------------
This is the EXPLORATION test for Property 1 (Bug Condition) — the broken SAM slug lifecycle
(author -> display -> publish). It ENCODES THE EXPECTED (fixed) behaviour, so on the UNFIXED code
it MUST FAIL — that failure is the counterexample proving the bug exists (bugfix workflow). After
the fix (tasks 3.x) the SAME assertions PASS unchanged, validating the fix.

It is deliberately SCOPED (scoped-PBT) to the concrete verified failing case for tenant `h-dcn`
(SAM `config#fields.slug = NULL`, verified this session in `test_governance_projection`), across
the two BACKEND facets of `isBugCondition` (design Formal Specification):

  * AUTHOR               — is there a client-reachable SAM write that validates+claims+persists the
                           form slug on `config#fields.slug`?  (defect B)
  * PUBLISH_REACHABILITY — for a tenant with `config#fields.slug=None`, publish is refused at the
                           readiness gate (`PublishNotReady(NO_SLUG)`) and — ON UNFIXED CODE — no
                           SAM path exists to clear that precondition.  (defect B consequence)

The DISPLAY facet is the frontend half of this exploration test and lives in the vitest sibling
`frontend/src/components/TenantAdmin/MembersConfig/__tests__/ApplicationFormBuilder.slugLifecycle.bug.test.tsx`.

NO live AWS: the backend facets are pure structural / in-memory-seam assertions (steering 39 —
the domain services are storage-agnostic; the dispatch accessors resolve lazily, so importing
touches no AWS).

Validates (bugfix): Requirements 1.1, 1.2, 1.3, 1.4
"""

from __future__ import annotations

import inspect
import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
_BACKEND_SRC = os.path.join(_REPO_ROOT, "backend", "src")
if _BACKEND_SRC not in sys.path:
    sys.path.insert(0, _BACKEND_SRC)

from sam.members.domain.application_publish import (
    ApplicationPublishService,
    PublishNotReady,
    PublishNotReadyReason,
)
from sam.members.domain.application_readiness import StaticMailReadinessProvider
from sam.members.domain.config_fields_crud_service import ConfigFieldsCrudService
from sam.members.handler import _dispatch_services as dispatch_services
from sam.members.handler.routes import ROUTES, RouteGroup

#: The verified real-data tenant whose SAM `config#fields.slug` is NULL (bugfix.md Examples).
_TENANT = "h-dcn"

#: The ONE canonical vocabulary of op names the `config#fields` Change-Op authority exposes today
#: (used to detect whether a slug-author op has been ADDED by the fix). A slug op would be a NEW
#: public method whose name mentions "slug".
_EXISTING_CRUD_OPS = {
    "set_field",
    "set_field_application",
    "reset_field",
    "delete_field",
    "set_group",
    "delete_group",
    "remove_legacy_choices",
    "remove_inline_options",
}


# ── Small helpers for the AUTHOR facet (introspect the SAM write surface) ──────────────


def _crud_slug_ops() -> list[str]:
    """Public `ConfigFieldsCrudService` methods that author/change the FORM SLUG.

    A slug-author op is a NEW public method (not one of the existing disjoint field/group ops)
    whose name mentions ``slug``. On UNFIXED code this is EMPTY (the Change-Op authority has no
    slug op — design "What EXISTS vs what is MISSING"); the fix (task 3.1) adds one.
    """
    ops = []
    for name, member in inspect.getmembers(
        ConfigFieldsCrudService, predicate=inspect.isfunction
    ):
        if name.startswith("_"):
            continue
        if name in _EXISTING_CRUD_OPS:
            continue
        if "slug" in name.lower():
            ops.append(name)
    return ops


def _slug_author_routes() -> list[str]:
    """SAM routes that author/change the FORM slug (a write whose path/name mentions ``slug``).

    EXCLUDES the publish route (``publish_application_form`` / ``.../publish``): publish CLAIMS an
    already-stored slug, it does NOT author one (design defect B). On UNFIXED code this is EMPTY;
    the fix (task 3.1) adds a ``members:admin``-gated author route.
    """
    out = []
    for spec in ROUTES:
        if spec.name == "publish_application_form":
            continue
        if "publish" in spec.path:
            continue
        mentions_slug = "slug" in spec.name.lower() or "slug" in spec.path.lower()
        if mentions_slug:
            out.append(spec.name)
    return out


# ══════════════════════════════════════════════════════════════════════════════════════
# FACET: AUTHOR — defect B (design isBugCondition: NO SAM author path that validates-prefix
# AND claims-marker AND persists config#fields.slug).  (bugfix R1.3, Expected 2.3)
#
# These assertions ENCODE THE EXPECTED behaviour (a client-reachable SAM slug-author path must
# exist), so they FAIL on the UNFIXED code — the failure IS the counterexample. The generic
# whole-object config door excludes `fields`, and the Change-Op authority exposes no slug op, so
# there is NOTHING that authors + claims + persists `config#fields.slug` from a client today.
# ══════════════════════════════════════════════════════════════════════════════════════


def test_author_generic_config_write_door_still_rejects_configId_fields():
    # VERIFIED ROOT-CAUSE FACT (not the fix target): the generic `PUT /members/config/{configId}`
    # whole-object door deliberately EXCLUDES `fields` — `config#fields` is Change-Op-only (spec 03
    # Task 7.1). This is UNCHANGED by the bugfix (the fix adds a SEPARATE slug-author path, it does
    # NOT re-open the whole-object door). Pinning it documents the counterexample's root cause and
    # stays green before AND after the fix.
    assert "fields" not in dispatch_services._WRITABLE_CONFIG_IDS
    assert "scope" in dispatch_services._WRITABLE_CONFIG_IDS
    assert "mail" in dispatch_services._WRITABLE_CONFIG_IDS


def test_author_config_fields_crud_exposes_a_slug_author_op():
    # EXPECTED (fixed) behaviour: the `config#fields` Change-Op authority exposes a client-reachable
    # slug-author op (task 3.1 adds a `members:admin` op that validates format+prefix, claims
    # `_slugs/{slug}`, and persists `config#fields.slug` via an identity Change-Op).
    #
    # UNFIXED: `_crud_slug_ops()` is EMPTY → this FAILS. That emptiness is the counterexample:
    #   "h-dcn: ConfigFieldsCrudService has no slug op — the slug cannot be authored on the SAM
    #    plane." (bugfix R1.3)
    slug_ops = _crud_slug_ops()
    assert slug_ops, (
        "BUG (AUTHOR facet): ConfigFieldsCrudService exposes NO form-slug author op "
        f"(only {sorted(_EXISTING_CRUD_OPS)}). There is no client-reachable SAM write that "
        "persists config#fields.slug + claims _slugs/{slug}. Counterexample: h-dcn "
        "(config#fields.slug=NULL) cannot author a slug on the SAM plane."
    )


def test_author_a_members_admin_slug_author_route_is_client_reachable():
    # EXPECTED (fixed) behaviour: a `members:admin`-gated SAM route exists to author/change the
    # form slug (task 3.1). It must NOT be the publish route (publish claims an existing slug, it
    # does not author one).
    #
    # UNFIXED: `_slug_author_routes()` is EMPTY → this FAILS. Counterexample: "h-dcn admin wants to
    #   set the SAM slug — there is no SAM control or endpoint to do it." (bugfix R1.3)
    routes = _slug_author_routes()
    assert routes, (
        "BUG (AUTHOR facet): no client-reachable SAM route authors the form slug "
        "(the only slug-touching route is publish_application_form, which CLAIMS an already-"
        "stored slug, never authors one). Counterexample: h-dcn has no SAM slug-author endpoint."
    )
    # Whatever the author route is named, it must be an admin-gated write, never self-service
    # (authoring a tenant's public address is an administrative concern — steering 30/39).
    by_name = {spec.name: spec for spec in ROUTES}
    for name in routes:
        spec = by_name[name]
        assert spec.self_service is False
        caps = set((spec.capability,) if spec.capability else ()) | set(
            spec.capabilities_any
        )
        assert "members:admin" in caps, (
            f"slug-author route {name!r} must be gated by members:admin (got {sorted(caps)})"
        )
        assert spec.group is RouteGroup.MEMBER


# ══════════════════════════════════════════════════════════════════════════════════════
# FACET: PUBLISH_REACHABILITY — defect B consequence (design isBugCondition: sam_slug IS None
# AND NO SAM author path → publish permanently unreachable).  (bugfix R1.4, Expected 2.4)
# ══════════════════════════════════════════════════════════════════════════════════════


class _FakeSlugReader:
    """In-memory `FormSlugReader` — returns the configured slug (None = no SAM slug, like h-dcn)."""

    def __init__(self, slug):
        self._slug = slug

    def get_form_slug(self, tenant_id):
        return self._slug


class _FakeFieldConfigReader:
    """In-memory `PublicFieldConfigReader` — a schema with `n` on-form fields (gate's 3rd check)."""

    def __init__(self, on_form_field_count):
        self._n = on_form_field_count

    def get_public_field_config(self, tenant_id):
        return {
            "tenant_id": tenant_id,
            "fields": [{"key": f"f{i}"} for i in range(self._n)],
            "locales": ["nl", "en"],
        }


def _publish_service_no_slug():
    """A publish service for a tenant with `config#fields.slug=None` (the h-dcn state).

    Certified sender + an on-form field are present, so the ONLY unmet precondition is the slug —
    isolating the `NO_SLUG` dead-end the missing author path can never clear on unfixed code.
    """
    return ApplicationPublishService(
        slug_reader=_FakeSlugReader(None),
        readiness_provider=StaticMailReadinessProvider({_TENANT: (True, "h-dcn.nl")}),
        field_config_reader=_FakeFieldConfigReader(1),
    )


def test_publish_reachability_no_sam_slug_is_refused_no_slug():
    # VERIFIED FACT (preserved by the fix, bugfix R3.1): for a tenant with `config#fields.slug=None`
    # the publish gate correctly refuses with the typed NO_SLUG reason. This is the dead-end the
    # broken lifecycle leaves h-dcn stuck at.
    svc = _publish_service_no_slug()
    with pytest.raises(PublishNotReady) as exc:
        svc.publish(_TENANT)
    assert exc.value.reason is PublishNotReadyReason.NO_SLUG


def test_publish_reachability_there_is_a_sam_path_to_clear_the_no_slug_gate():
    # EXPECTED (fixed) behaviour (bugfix R2.4): once the SAM slug-author path exists, the NO_SLUG
    # precondition is clearable from the SAM plane — i.e. a SAM author op/route EXISTS that, by
    # persisting `config#fields.slug`, makes publish reachable.
    #
    # UNFIXED: there is NO author op AND NO author route → publish is permanently unreachable for a
    #   no-SAM-slug tenant → this FAILS. Counterexample: "h-dcn: publish stuck no_slug, and no SAM
    #   path clears it." (bugfix R1.4)
    exists_author_path = bool(_crud_slug_ops()) and bool(_slug_author_routes())
    assert exists_author_path, (
        "BUG (PUBLISH_REACHABILITY facet): config#fields.slug is None for h-dcn and there is NO "
        "SAM author path (no ConfigFieldsCrudService slug op AND no slug-author route) to persist "
        "it — so the publish NO_SLUG refusal can NEVER be cleared from the SAM plane. "
        "Counterexample: h-dcn publish is permanently unreachable."
    )
