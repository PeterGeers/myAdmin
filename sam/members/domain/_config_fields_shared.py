"""Shared constants, wire-key vocabulary and error types.

Part of ConfigFieldsCrudService (code-quality-fixes-2026-11-12 task 4).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

#: The producer identity the slug-author op writes into the ``_slugs/{slug}`` marker BODY —
#: IDENTICAL to the publish path's owner (``application_publish.FORM_OWNER_*``) so an authored
#: slug and a published slug are the SAME owner (a publish of an authored slug is an idempotent
#: same-owner re-claim, never a clobber conflict). The application form is a ``sam``-plane
#: producer of ``kind="application_form"`` whose ``resource_ref`` back-points at its own
#: ``config#fields`` row. Ownership (idempotent re-author vs clobber backstop) is decided from
#: THESE body fields, never by parsing the slug string (slug_marker_store Property 2).
SLUG_OWNER_PLANE = "sam"
SLUG_OWNER_KIND = "application_form"
SLUG_RESOURCE_REF = "config#fields"

# ── The DISJOINT attribute surfaces (design C1; design-review Must-fix #3) ──────────────

#: Field DEFINITION attributes — the ONLY attrs :meth:`set_field` may write. Deliberately EXCLUDES
#: every ``application_*`` attr and ``format`` (those live on :data:`FIELD_APPLICATION_ATTRS`), so
#: a definition op is structurally unable to touch application-form config.
#:
#: ``choices`` was RETIRED (spec 03a, C2): the write surface now accepts ONLY the one canonical
#: ``options`` vocabulary. ``choices`` is no longer an accepted definition attribute, so a write
#: carrying it is rejected out-of-surface (:class:`ConfigFieldsCrudError`) — there is one
#: vocabulary model end-to-end (R2.1, R3.3). The storage key stays ``overrides``, served under the
#: wire key ``fixed_overrides`` (the one-key contract is unchanged); the write remains a Change-Op
#: on a single path (no whole-row replace).
FIELD_DEFINITION_ATTRS = frozenset(
    {
        "type",
        "label",
        "order",
        "required",
        "visible",
        "options",
        "scope",
        "functional_group",
    }
)

#: The FOUR application attributes — the ONLY attrs :meth:`set_field_application` may write. Fully
#: qualified so they never collide with the definition ``visible``/``required``/``choices`` names;
#: this is the structural barrier the application-form builder writes behind (D3(A)).
FIELD_APPLICATION_ATTRS = frozenset(
    {
        "application_visible",
        "application_required",
        "application_choices",
        "format",
    }
)

#: Group attributes — the ONLY attrs :meth:`set_group` may write.
GROUP_ATTRS = frozenset({"label", "order"})

#: The three parent maps on the ``config#fields`` row (the row-skeleton contract, design C6). Used
#: only to NAME the outer path segment; the service never writes a whole parent map. ``overrides``
#: is the STORAGE key the ops write to (and the resolver's canonical read key) — the write path
#: addresses ``overrides.<dotted>`` at rest; the reader serves that SAME map under the authoring
#: WIRE key ``fixed_overrides`` (the one-key contract in ``get_raw_fields_overlay``).
_FIELDS_MAP = "fields"
_OVERRIDES_MAP = "overrides"
_GROUPS_MAP = "functional_groups"

#: The DISTINCT presentation slice (spec 15 — SAM Page Look-and-Feel, DD-2 / Layer 1). It is the
#: application-form PAGE's look-and-feel — the attribute VALUES only, never generated CSS — a
#: parent map on the SAME ``config#fields`` row the slug / publish-state ops already address, but
#: SEPARATE from the member field-config slices ``fields`` / ``overrides`` / ``functional_groups``.
#: Seeded empty by the C6 row skeleton (``FIELDS_SKELETON_PARENTS``) so a child
#: ``SET look_and_feel.<attr>`` addresses a pre-existing parent map. The Layer-1 look-and-feel
#: writer adapter (:meth:`ConfigFieldsCrudService.set_look_and_feel` /
#: :meth:`remove_look_and_feel` / :meth:`copy_look_and_feel`) writes ONLY into this map, so a
#: look-and-feel write can never disturb the member field config (by construction, steering 39).
_LOOK_AND_FEEL_MAP = "look_and_feel"

#: Map a STORAGE map name to the key it is served under in the reader's WIRE overlay shape. Only
#: ``overrides`` differs (served as ``fixed_overrides``); ``fields`` / ``functional_groups`` keep
#: their names. Used by :meth:`ConfigFieldsCrudService._entry_exists` to look an entry up in the
#: consistent snapshot by the key the reader actually serves it under.
_MAP_TO_WIRE_KEY = {
    _OVERRIDES_MAP: "fixed_overrides",
    _FIELDS_MAP: "fields",
    _GROUPS_MAP: "functional_groups",
}

#: The reader's wire-overlay container keys inspected for emptiness when deciding "no row yet"
#: vs "legacy row with no version" (base_version case ii vs iii).
_WIRE_CONTAINER_KEYS = ("fields", "fixed_overrides", "functional_groups")

#: The ``config#fields`` id the ops target (one SAM-owned config row).
_CONFIG_ID_FIELDS = "fields"


def _snapshot_is_empty(snapshot: Mapping[str, Any]) -> bool:
    """True when the wire overlay is the empty/never-authored shape (all containers empty).

    The reader returns ``{"fields": {}, "fixed_overrides": {}, "functional_groups": {}}`` for a
    tenant with no ``config#fields`` row (empty-is-valid). That shape must be read as "no row yet"
    (base_version ``None``), not as a legacy versionless row — so a first write onto the C6
    skeleton uses the ``attribute_not_exists(sk)`` condition, not a spurious legacy lock.
    """
    for key in _WIRE_CONTAINER_KEYS:
        container = snapshot.get(key)
        if isinstance(container, Mapping) and container:
            return False
    return True


class ConfigFieldsCrudError(ValueError):
    """A deliberate, caller-safe rejection of a malformed / out-of-surface CRUD request.

    Raised BEFORE any repository call (steering 35/39 — no raw internals) when an op is asked to
    write an attribute outside its disjoint surface (e.g. an ``application_*`` key handed to
    :meth:`set_field`, or a definition key handed to :meth:`set_field_application`), or when an
    identity / attrs payload is malformed. Subclasses :class:`ValueError` so existing
    ``except ValueError`` edges keep working.
    """


class SlugAuthorRejected(ConfigFieldsCrudError):
    """The authored slug is malformed/reserved or violates the SEC-4 prefix-ownership rule.

    Raised by :meth:`ConfigFieldsCrudService.set_form_slug` BEFORE any marker claim or write when
    the slug fails the shared format/reserved contract (:func:`form_slug.validate_slug_format`) or
    the SEC-4 prefix-ownership rule (:func:`form_slug.validate_slug_prefix_ownership`) — so no
    marker is claimed and ``config#fields.slug`` is never persisted for an unownable slug. Carries
    a caller-safe ``detail`` (the validator's own no-internals message) the admin-facing edge
    surfaces on a 422 validation envelope (steering 30/37). A :class:`ConfigFieldsCrudError`
    subclass so a generic ``except ConfigFieldsCrudError`` still catches it, but the slug-author
    dispatch maps it to a 422.
    """

    def __init__(self, detail: str):
        self.detail = detail
        super().__init__(detail)


class SlugAuthorConflict(Exception):
    """The authored slug is already claimed by a FOREIGN owner (clobber backstop, R4.4).

    Raised by :meth:`ConfigFieldsCrudService.set_form_slug` when the atomic
    :meth:`S3SlugMarkerStore.claim` reports the ``_slugs/{slug}`` marker is owned by a DIFFERENT
    owner (a different plane / kind / tenant — :class:`SlugTaken`). The op NEVER overwrites a
    foreign marker and persists NOTHING: it surfaces a caller-safe conflict the edge maps to a 409
    carrying a GENERIC, no-internals message — never the raw :class:`SlugTaken` / ``str(e)``. A
    same-owner re-author is idempotent (``claim`` succeeds silently for a matching body) and never
    reaches this path. Deliberately NOT a :class:`ConfigFieldsCrudError` so the edge catches it on
    its OWN 409 branch, distinct from the 422 validation rejection.
    """

    def __init__(self, slug: str):
        self.slug = slug
        super().__init__(f"slug '{slug}' is already claimed by another page")
