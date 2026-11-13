"""Form-slug, publish-state, prefix and look-and-feel ops.

Part of ConfigFieldsCrudService (code-quality-fixes-2026-11-12 task 4).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sam.members.domain.form_slug import (
    validate_slug_format,
    validate_slug_prefix_ownership,
)
from sam.members.repository.projection_config_write_repository import REMOVE, SET
from sam.members.repository.slug_marker_store import SlugMarker, SlugTaken

from ._config_fields_shared import (
    _LOOK_AND_FEEL_MAP,
    SLUG_OWNER_KIND,
    SLUG_OWNER_PLANE,
    SLUG_RESOURCE_REF,
    ConfigFieldsCrudError,
    SlugAuthorConflict,
    SlugAuthorRejected,
)


class ConfigFieldsSlugOpsMixin:
    """Form-slug, publish-state, prefix and look-and-feel ops."""

    # ── Form-slug author op (bugfix-slug-lifecycle task 3.1 — design §Fix Implementation) ──

    def set_form_slug(
        self,
        tenant_id: str,
        slug: str | None,
        *,
        client_op_id: str | None = None,
    ) -> dict:
        """Author / change / clear the application-form public ``slug`` on ``config#fields``.

        The MISSING client-reachable SAM slug WRITE (bugfix defect B): the single sanctioned path
        that validates, claims the shared marker, and persists ``config#fields.slug`` as an
        identity Change-Op. Runs in this fixed order (form_slug "Ordering on a claim path"):

        1. **format/reserved** (:func:`form_slug.validate_slug_format`, R2.3) — a malformed /
           reserved slug is rejected (:class:`SlugAuthorRejected`) before anything else; no claim,
           no write.
        2. **SEC-4 prefix ownership** (:func:`form_slug.validate_slug_prefix_ownership`) — the slug
           must sit under the AUTHENTICATED tenant's own ``public_prefix`` (resolved via the
           injected ``prefix_reader.get_public_prefix``). A re-author of the tenant's OWN
           already-live slug is a grandfathered same-owner case (``is_grandfathered=True``) and is
           NOT re-validated against the prefix rule (R2.5).
        3. **claim / rename** (R4 / R4.6) — a NEW or same-slug re-author takes a bare atomic
           :meth:`S3SlugMarkerStore.claim` writing the structured owner body
           ``{owner_plane=sam, kind=application_form, tenant_id, resource_ref=config#fields}``
           under ``If-None-Match: *`` (IDEMPOTENT same-owner, clobber backstop). A CHANGE — the
           tenant already owns a DIFFERENT stored ``config#fields.slug`` — instead goes through
           :meth:`S3SlugMarkerStore.rename` (task 3.2): it claims the NEW marker FIRST and releases
           the OLD one ONLY after that succeeds (claim-new-before-release-old), so a stale
           ``_slugs/{old}`` marker is never orphaned and a crash/conflict mid-change never leaves
           the tenant with no slug. Either shape maps a FOREIGN owner's :class:`SlugTaken` to the
           caller-safe :class:`SlugAuthorConflict` (the clobber backstop — a foreign marker is
           NEVER overwritten, the OLD marker is left intact, and NOTHING is persisted).
        4. **persist** — a SINGLE identity Change-Op on the top-level ``slug`` path via
           ``apply_ops`` (``SET slug = <value>`` for a non-blank slug), reusing the version-
           conditional write (NOT a whole-record replace, steering 39). The op addresses ONLY the
           ``slug`` attribute, so DynamoDB leaves ``published_at`` / ``published_version`` (and
           every ``fields`` / ``overrides`` / ``functional_groups`` slice) physically UNTOUCHED —
           publish-state is carried through BY CONSTRUCTION, never authored here (R3.4).

        Clear semantics (steering 39 clear-vs-unchanged): an explicit ``slug=None`` CLEARS the
        stored slug via a scoped ``REMOVE slug`` — no validation, no claim (there is nothing to
        own); the marker is intentionally NOT released here (teardown/rename owns marker lifecycle,
        task 3.2). A blank/whitespace string is treated as a clear.

        Args:
            tenant_id: The AUTHORITATIVE tenant from the verified token (never a body value,
                steering 39).
            slug: The new slug to author, or ``None`` / blank to CLEAR the stored slug.
            client_op_id: Optional lost-response idempotency token forwarded to ``apply_ops``.

        Returns:
            The repository ``apply_ops`` result verbatim (``{"version": ..., "idempotent_replay":
            ...}``).

        Raises:
            SlugAuthorRejected: the slug is malformed/reserved or violates the SEC-4 prefix rule.
            SlugAuthorConflict: the slug is owned by a FOREIGN owner — no clobber, no write.
            ConfigFieldsCrudError: the slug-author seams (marker store / prefix reader) are not
                wired (a mis-configured service) — a fail-loud internal guard, never a client path.
        """
        # CLEAR — an explicit null / blank slug drops the stored attribute with a scoped REMOVE.
        # No format/prefix check and no marker claim (there is no slug to own); publish-state and
        # every other slice stay untouched (the REMOVE names ONLY the `slug` path).
        if slug is None or (isinstance(slug, str) and not slug.strip()):

            def derive_clear(snapshot):
                return [{"action": REMOVE, "path": ["slug"]}]

            return self._run(tenant_id, derive_clear, client_op_id=client_op_id)

        if not isinstance(slug, str):
            raise SlugAuthorRejected("slug must be a string")

        candidate = slug.strip()

        # 1. Format / reserved FIRST (R2.3) — a malformed slug never reaches the prefix check.
        format_error = validate_slug_format(candidate)
        if format_error is not None:
            raise SlugAuthorRejected(format_error)

        if self._slug_marker_store is None or self._prefix_reader is None:
            # The op cannot claim without its injected seams. This is a mis-wired service, not a
            # client error — fail loud (caller-safe, no internals) rather than silently persisting
            # a slug whose marker was never claimed.
            raise ConfigFieldsCrudError(
                "slug-author is not available: the marker store / prefix reader are not wired"
            )

        # 2. SEC-4 prefix ownership. Grandfather the tenant's OWN already-live slug (same-owner
        #    marker) so an established slug is never re-validated/force-renamed (R2.5). Ownership is
        #    read from the marker BODY, never parsed from the slug string (slug_marker_store P2).
        owner = SlugMarker(
            owner_plane=SLUG_OWNER_PLANE,
            kind=SLUG_OWNER_KIND,
            tenant_id=tenant_id,
            resource_ref=SLUG_RESOURCE_REF,
        )
        is_grandfathered = self._slug_is_own_live(candidate, owner)
        tenant_prefix = self._prefix_reader.get_public_prefix(tenant_id)
        prefix_error = validate_slug_prefix_ownership(
            candidate, tenant_prefix, is_grandfathered=is_grandfathered
        )
        if prefix_error is not None:
            raise SlugAuthorRejected(prefix_error)

        # 3. Claim the candidate marker. Two shapes (task 3.2):
        #    - CHANGE (the tenant already owns a DIFFERENT stored slug): hand the old→new
        #      transition to `S3SlugMarkerStore.rename` (claim-NEW-before-release-OLD, R4.6) so the
        #      stale `_slugs/{old}` marker is released — but ONLY after the new one is safely owned.
        #      A crash/foreign-conflict mid-rename never leaves the tenant with no slug (the old
        #      marker survives); the old marker is never orphaned on success.
        #    - NEW / same-slug re-author: a bare atomic `claim` (idempotent same-owner / clobber
        #      backstop) — the task-3.1 path, unchanged.
        #    Either way a FOREIGN owner → SlugTaken, mapped to the caller-safe conflict; NOTHING is
        #    persisted and no old marker is released.
        old_slug = self._current_stored_slug(tenant_id)
        is_change = old_slug is not None and old_slug != candidate
        try:
            if is_change:
                self._slug_marker_store.rename(old_slug, candidate, owner)
            else:
                self._slug_marker_store.claim(candidate, owner)
        except SlugTaken as exc:
            raise SlugAuthorConflict(candidate) from exc

        # 4. Persist the slug as a SINGLE identity Change-Op (top-level `slug` path). The op names
        #    only `slug`, so published_* and every catalog slice survive by construction (R3.4 /
        #    steering 39 — never a whole-record replace).
        def derive_set(snapshot):
            return [{"action": SET, "path": ["slug"], "value": candidate}]

        return self._run(tenant_id, derive_set, client_op_id=client_op_id)

    # ── Publish-state op (bugfix-published-form-submit Round 3, task 11.4) ──────────────

    def set_publish_state(
        self,
        tenant_id: str,
        *,
        published_version: int,
        published_at: str,
        client_op_id: str | None = None,
    ) -> dict:
        """Persist the publish-state metadata (``published_version`` / ``published_at``).

        Mirrors :meth:`set_form_slug`'s persist step: a SINGLE version-conditional identity
        Change-Op through ``apply_ops`` (steering 39 — never a whole-record put). The op SETs ONLY
        the two top-level publish-state attributes, so DynamoDB leaves ``slug`` and every
        ``fields`` / ``overrides`` / ``functional_groups`` slice physically UNTOUCHED (by
        construction). A concurrent write surfaces as the repository's ``StaleVersionError`` after
        the guarded one-shot re-derive retry in :meth:`_run` (a clean conflict, no partial change).

        Args:
            tenant_id: The AUTHORITATIVE tenant (verified token / publish service), never a body.
            published_version: The new monotonic publish version (a positive int, not a bool).
            published_at: The ISO-8601 publish timestamp (a non-blank string).
            client_op_id: Optional lost-response idempotency token forwarded to ``apply_ops``.

        Raises:
            ConfigFieldsCrudError: ``published_version`` / ``published_at`` are malformed.
        """
        if (
            isinstance(published_version, bool)
            or not isinstance(published_version, int)
            or published_version < 1
        ):
            raise ConfigFieldsCrudError("published_version must be a positive integer")
        if not isinstance(published_at, str) or not published_at.strip():
            raise ConfigFieldsCrudError("published_at must be a non-blank string")

        def derive(snapshot):
            return [
                {
                    "action": SET,
                    "path": ["published_version"],
                    "value": published_version,
                },
                {"action": SET, "path": ["published_at"], "value": published_at},
            ]

        return self._run(tenant_id, derive, client_op_id=client_op_id)

    # ── Public-prefix author op (slug-prefix SAM-owned, config#fields.public_prefix) ────

    def set_public_prefix(
        self,
        tenant_id: str,
        prefix: str | None,
        *,
        client_op_id: str | None = None,
    ) -> dict:
        """Author / change / clear the tenant's SAM-owned public slug ``prefix`` on config#fields.

        The slug PREFIX is the tenant's own short public stem (e.g. ``h-dcn``) under which every
        application-form slug must sit (SEC-4 prefix ownership, :meth:`set_form_slug` step 2). It is
        SAM-OWNED: stored as the top-level ``public_prefix`` attribute on the tenant's
        ``config#fields`` row and read back by
        :meth:`sam.members.repository.projection_config_reader.MembersProjectionReader.get_public_prefix`.
        (Flask no longer stores or projects it — the MySQL ``tenants.public_prefix`` column was
        dropped; the prefix lives only on the SAM plane.)

        Shape rules: a prefix is itself a slug stem, so it must satisfy the SAME slug-safe contract
        a slug does (:func:`form_slug.validate_slug_format` — lowercase ``[a-z0-9-]``, 3–100 chars,
        no leading/trailing or consecutive hyphens, not reserved). There is NO marker claim: the
        prefix is the tenant's own namespace, not a globally-unique public address, so it is not
        claimed in ``_slugs/`` (cross-tenant prefix uniqueness is NOT enforced here — see the note
        below).

        Clear semantics (steering 39 clear-vs-unchanged): an explicit ``prefix=None`` or a
        blank/whitespace string CLEARS the stored prefix via a scoped ``REMOVE public_prefix`` — no
        format check. A tenant with no prefix cannot author a NEW slug (the SEC-4 rule refuses a
        prefix-less claim), so clearing the prefix does NOT retroactively invalidate an already
        authored+claimed slug (that slug keeps its own marker; its grandfathering is decided from
        the marker body, not the prefix).

        Persist is a SINGLE identity Change-Op on the top-level ``public_prefix`` path via
        ``apply_ops`` — it names ONLY that attribute, so ``slug`` / ``published_*`` and every
        ``fields`` / ``overrides`` / ``functional_groups`` slice stay physically UNTOUCHED (never a
        whole-record replace, steering 39).

        NOTE (cross-tenant uniqueness): the dropped MySQL column carried a UNIQUE constraint. There
        is no equivalent global uniqueness guard on the SAM plane yet. Because every authored slug
        IS atomically claimed in the shared ``_slugs/`` namespace (:meth:`set_form_slug`), two
        tenants cannot end up serving the same public address even if they share a prefix stem — the
        squatting protection lives at the slug-claim layer, not the prefix. A dedicated
        prefix-uniqueness guard, if wanted, is a separate follow-up.

        Args:
            tenant_id: The AUTHORITATIVE tenant from the verified token (never a body value).
            prefix: The new public prefix to author, or ``None`` / blank to CLEAR it.
            client_op_id: Optional lost-response idempotency token forwarded to ``apply_ops``.

        Returns:
            The repository ``apply_ops`` result verbatim (``{"version", "idempotent_replay"}``).

        Raises:
            SlugAuthorRejected: the prefix is malformed/reserved (same caller-safe 422 path as the
                slug author), so nothing is persisted.
        """
        # CLEAR — explicit null / blank drops the stored attribute with a scoped REMOVE.
        if prefix is None or (isinstance(prefix, str) and not prefix.strip()):

            def derive_clear(snapshot):
                return [{"action": REMOVE, "path": ["public_prefix"]}]

            return self._run(tenant_id, derive_clear, client_op_id=client_op_id)

        if not isinstance(prefix, str):
            raise SlugAuthorRejected("public prefix must be a string")

        candidate = prefix.strip()

        # A prefix is a slug stem — it must satisfy the SAME slug-safe shape contract.
        format_error = validate_slug_format(candidate)
        if format_error is not None:
            raise SlugAuthorRejected(format_error)

        # Persist as a SINGLE identity Change-Op (top-level `public_prefix` path). Names only that
        # attribute, so slug / published_* / every catalog slice survive by construction.
        def derive_set(snapshot):
            return [{"action": SET, "path": ["public_prefix"], "value": candidate}]

        return self._run(tenant_id, derive_set, client_op_id=client_op_id)

    # ── Look-and-feel writer adapter (spec 15 — SAM Page Look-and-Feel, task 4.5) ───────
    #
    # The Layer-1 Change-Op WRITER over ``apply_ops`` for the DISTINCT ``look_and_feel`` slice
    # (DD-2). Three op shapes, each a SINGLE path-scoped, version-conditional ``update_item`` —
    # NEVER a whole-record ``put_item`` from a client path (steering 39 Change-Op write contract):
    #
    #   * :meth:`set_look_and_feel`    → ``SET look_and_feel.<attr> = :v``   (author one value)
    #   * :meth:`remove_look_and_feel` → ``REMOVE look_and_feel.<attr>``     (revert to default)
    #   * :meth:`copy_look_and_feel`   → ``SET look_and_feel = :snapshot``   (one-time snapshot)
    #
    # Each op names ONLY the ``look_and_feel`` path, so DynamoDB leaves ``fields`` / ``overrides``
    # / ``functional_groups`` / ``slug`` / publish-state physically UNTOUCHED (by construction) and
    # a concurrent edit surfaces as the repository's :class:`StaleVersionError` (caller-safe 409) —
    # UNCHANGED by this adapter; the ``TruncationTripwireError`` backstop still applies since every
    # write goes through the one ``apply_ops`` seam. This adapter stores VALUES ONLY (never
    # generated CSS). It is the thin WRITER (intent → ops translation + placement); ATTRIBUTE and
    # VALUE validation (the supported-seven / permitted-set rules, Req 3.4 / 4.5) is the
    # ``LookAndFeelSettingsService`` seam's responsibility (task 5.1) layered ABOVE this adapter —
    # kept out of here so the adapter stays a pure, reusable Change-Op surface.

    def set_look_and_feel(
        self,
        tenant_id: str,
        attribute: str,
        value: Any,
        *,
        client_op_id: str | None = None,
    ) -> dict:
        """Author ONE look-and-feel attribute VALUE: ``SET look_and_feel.<attribute> = value``.

        A SINGLE path-scoped, version-conditional ``update_item`` into the pre-existing
        ``look_and_feel`` parent map (seeded empty by the C6 row skeleton). The op names ONLY
        ``look_and_feel.<attribute>``, so every member field-config slice and the slug /
        publish-state attributes survive by construction (steering 39). Stores the VALUE as-is
        (never CSS). A stale row surfaces as :class:`StaleVersionError` (caller-safe 409) via the
        guarded one-shot retry in :meth:`_run`.

        ``attribute`` MUST be a non-blank string (a blank segment is a malformed path the repository
        would reject opaquely — rejected here as a caller-safe :class:`ConfigFieldsCrudError`
        BEFORE any write). The supported-attribute / permitted-value validation is the
        ``LookAndFeelSettingsService`` layer's responsibility (task 5.1), not this writer adapter.
        """
        attr = self._require_look_and_feel_attribute(attribute)

        def derive(snapshot):
            # CREATE-vs-UPDATE by parent-map existence (same discipline as the field CREATE
            # path, Must-fix #1): a nested ``SET look_and_feel.<attr>`` is INVALID when the
            # ``look_and_feel`` parent map does not yet exist on the row — DynamoDB rejects it
            # with a ValidationException ("document path ... invalid for update"). A LEGACY
            # pre-task-4.1 ``config#fields`` row never received the skeleton seed, so its parent
            # map is absent. When absent, SEED the whole slice in one op (``SET look_and_feel =
            # {attr: value}``) — which creates the parent map with this one attribute; when it
            # already exists, emit the minimal nested ``SET look_and_feel.<attr>`` so sibling
            # attributes are left physically untouched. Either way a SINGLE op naming only the
            # ``look_and_feel`` path (other slices survive by construction).
            existing = (
                snapshot.get(_LOOK_AND_FEEL_MAP)
                if isinstance(snapshot, Mapping)
                else None
            )
            if isinstance(existing, Mapping):
                return [
                    {
                        "action": SET,
                        "path": [_LOOK_AND_FEEL_MAP, attr],
                        "value": value,
                    }
                ]
            # Parent map absent (legacy/never-authored row) — seed the whole slice.
            return [
                {
                    "action": SET,
                    "path": [_LOOK_AND_FEEL_MAP],
                    "value": {attr: value},
                }
            ]

        return self._run(tenant_id, derive, client_op_id=client_op_id)

    def remove_look_and_feel(
        self,
        tenant_id: str,
        attribute: str,
        *,
        client_op_id: str | None = None,
    ) -> dict:
        """Clear ONE look-and-feel attribute (revert to default): ``REMOVE look_and_feel.<attr>``.

        The explicit-remove half of the steering-39 clear-vs-unchanged contract: an absent attribute
        is "leave untouched" (no path written — the caller simply omits it), while this is the
        deliberate scoped ``REMOVE`` of exactly one attribute, after which the resolved view falls
        back to the Layer-2 default for that attribute. A SINGLE path-scoped, version-conditional
        ``update_item`` naming ONLY ``look_and_feel.<attribute>``; unrelated slices are untouched.
        """
        attr = self._require_look_and_feel_attribute(attribute)

        def derive(snapshot):
            return [{"action": REMOVE, "path": [_LOOK_AND_FEEL_MAP, attr]}]

        return self._run(tenant_id, derive, client_op_id=client_op_id)

    def copy_look_and_feel(
        self,
        tenant_id: str,
        snapshot_values: Mapping[str, Any],
        *,
        client_op_id: str | None = None,
    ) -> dict:
        """Overwrite the WHOLE look-and-feel slice with a one-time snapshot: ``SET look_and_feel =
        :snapshot`` (Req 9 copy, the Change-Op half).

        A SINGLE path-scoped, version-conditional ``update_item`` that SETs the WHOLE
        ``look_and_feel`` map to ``snapshot_values`` — the physical effect of a copy-from-another-
        page (the SERVICE layer, task 5.3, resolves the source page's values and enforces the
        same-tenant rule; this adapter performs only the scoped overwrite). It names ONLY the
        ``look_and_feel`` path — NOT a whole-record ``put_item`` — so ``fields`` / ``overrides`` /
        ``functional_groups`` / ``slug`` / publish-state are left physically untouched, and a stale
        row still surfaces as :class:`StaleVersionError`. Stores VALUES only (never CSS).

        ``snapshot_values`` MUST be a mapping (the snapshot of the source page's stored values);
        an empty mapping is a valid snapshot (overwrites the target to "all defaults"). A non-mapping
        is rejected as a caller-safe :class:`ConfigFieldsCrudError` BEFORE any write.
        """
        if not isinstance(snapshot_values, Mapping):
            raise ConfigFieldsCrudError(
                "copy_look_and_feel: snapshot_values must be a mapping of attribute values"
            )
        snapshot_copy = dict(snapshot_values)

        def derive(snapshot):
            return [
                {
                    "action": SET,
                    "path": [_LOOK_AND_FEEL_MAP],
                    "value": snapshot_copy,
                }
            ]

        return self._run(tenant_id, derive, client_op_id=client_op_id)

    @staticmethod
    def _require_look_and_feel_attribute(attribute: str) -> str:
        """Validate the attribute is a non-blank string and return it trimmed (caller-safe).

        A structural guard only — a blank/non-string segment is a malformed path the repository
        would otherwise reject with an opaque ``ChangeOpError``; rejecting it here keeps the message
        intelligible (:class:`ConfigFieldsCrudError`, BEFORE any write). It deliberately does NOT
        check the attribute against the supported-seven set — that semantic validation is the
        ``LookAndFeelSettingsService`` layer's job (task 5.1), kept out of this reusable adapter.
        """
        if not isinstance(attribute, str) or not attribute.strip():
            raise ConfigFieldsCrudError(
                "look-and-feel attribute must be a non-blank string"
            )
        return attribute.strip()

    def _current_stored_slug(self, tenant_id: str) -> str | None:
        """Return the tenant's CURRENTLY stored ``config#fields.slug``, or ``None`` (task 3.2).

        Used ONLY to decide a slug CHANGE (the tenant already owns a different slug) so the op can
        route the old→new transition through :meth:`S3SlugMarkerStore.rename` instead of a bare
        claim that would orphan ``_slugs/{old}``. Reads via the injected forward slug reader's
        ``get_form_slug`` (the SAME resolved read the publish/display surfaces use). Fail-safe: no
        reader, no ``get_form_slug``, a blank value, or a lookup error all resolve to ``None`` —
        "no prior slug", so the op falls back to the task-3.1 bare-claim path (change detection is a
        strict enhancement and never blocks an author/re-author). A blank/whitespace result is
        normalised to ``None``.
        """
        reader = self._slug_reader
        if reader is None or not hasattr(reader, "get_form_slug"):
            return None
        try:
            current = reader.get_form_slug(tenant_id)
        except Exception:  # noqa: BLE001 - a read fault must not block authoring; degrade to "none"
            return None
        if isinstance(current, str) and current.strip():
            return current.strip()
        return None

    def _slug_is_own_live(self, slug: str, owner: SlugMarker) -> bool:
        """True when ``_slugs/{slug}`` already exists AND is owned by THIS tenant's form (R2.5).

        Grandfathering predicate for the SEC-4 prefix rule: a re-author of the tenant's OWN
        already-live slug must pass the prefix check unconditionally (an established slug is never
        force-renamed). Ownership is compared on ``owner_plane`` + ``kind`` + ``tenant_id`` read
        from the marker BODY (never the slug string). A missing / unreadable / foreign marker →
        ``False`` (not grandfathered → the prefix rule applies, as it must for a NEW claim).
        """
        store = self._slug_marker_store
        if store is None or not hasattr(store, "resolve"):
            return False
        existing = store.resolve(slug)
        if existing is None:
            return False
        return (
            existing.owner_plane == owner.owner_plane
            and existing.kind == owner.kind
            and existing.tenant_id == owner.tenant_id
        )
