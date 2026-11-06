"""
SAM Page Look-and-Feel — Layer-1 authoring service (``LookAndFeelSettingsService``).

Spec: ``.kiro/specs/Members/15 - sam-page-look-and-feel`` (design C3 / DD-2, Layer 1), task 5.1.

This is the DOMAIN service for authoring and reading a Page's ``Look_And_Feel_Settings`` **values**
(never generated CSS — that is Layer 2). It follows the ``ConfigFieldsCrudService`` pattern: a pure
domain service with a constructor-injected resolved-view READER and a Change-Op WRITER, holding NO
``boto3`` / DynamoDB / table resolution (steering 35/39 — dependency inversion; the repository owns
the client, this service owns INTENT → validated write).

Responsibilities (task 5.1)
---------------------------
- ``get_settings(tenant_id, page_id)`` — resolved-view read of the stored ``look_and_feel`` slice,
  tenant-scoped (Req 2.4); an absent slice/key resolves to an empty mapping so Layer 2 applies its
  own SAM-owned defaults (Req 3.3 / 4.4 / 5.4). VALUES only.
- ``set_setting(tenant_id, page_id, attribute, value)`` — author ONE attribute VALUE (Req 8.1). It
  VALIDATES the attribute against the supported set (the ten of
  :data:`~sam.shared.page_styles.SUPPORTED_ATTRIBUTES` — Req 3.4) and the value against
  its permitted set (Req 4.5) BEFORE any write; an invalid attribute/value is REJECTED and the
  Page's previously stored values are left UNCHANGED (no Change-Op is issued). A valid change is a
  SINGLE scoped, version-conditional Change-Op via the injected writer.

- ``copy_settings(tenant_id, source_page_id, target_page_id, *, source_tenant_id=None)`` — author a
  ONE-TIME snapshot copy of one Page's stored VALUES onto another Page within the SAME verified
  tenant (Req 9). It reads the source's resolved view (``get_look_and_feel``) and issues a SINGLE
  ``SET look_and_feel = :snapshot`` on the target via the writer's ``copy_look_and_feel`` (Req 9.1 /
  9.3). It establishes NO ongoing link or inheritance between source and target — a later change to
  either Page does not touch the other (Req 9.2 / 9.5), because the copy is a plain value snapshot
  with nothing wired between them. A source belonging to ANOTHER tenant is REJECTED before any read
  or write (Req 9.4, caller-safe 403). ``source_page_id`` / ``target_page_id`` resolve today to the
  one SAM-owned page (the application form); an unknown id on either side is rejected.

The ``page_id`` seam (forward-looking)
--------------------------------------
``page_id`` is kept on the public surface so the service can one day address more than one page
type (the per-page-type generalization under DD-2). TODAY it resolves to the single SAM-owned page
wired in this feature — the application form's ``look_and_feel`` slice on ``config#fields`` — and the
injected reader/writer seams already target exactly that slice. No generic ``Page`` entity or
page-type discriminator is introduced now (steering 37 rule-of-three); an unknown ``page_id`` is
rejected rather than silently writing to the application form.

Validation contract (Req 3.4 / Req 4.5)
---------------------------------------
- Attribute support (Req 3.4): the attribute MUST be one of
  :data:`~sam.shared.page_styles.SUPPORTED_ATTRIBUTES` (the ten the Layer-2 generator
  consumes — the original seven plus the bugfix extension ``columns`` / ``logo`` /
  ``header_title``). An unsupported attribute is rejected and NO write is issued.
- Value permitted-set (Req 4.5): each attribute has a permitted VALUE contract (see
  :data:`_PERMITTED_VALUES` / the colour + font format checks / the columns-bounds + logo-reference
  + header_title-length checks). A value outside it is rejected and the stored values are left
  unchanged. The enum permitted sets (and the ``columns`` bound) mirror the Layer-2 generator's own
  lookup maps / grid clamp so a value the service accepts is a value the generator renders
  meaningfully.

Both rejections raise :class:`LookAndFeelValidationError` (a :class:`ValueError`) BEFORE any writer
call, so the stored values are untouched by construction (the edge maps it to a caller-safe 422 that
identifies the rejected attribute/value — the client's own key/value, safe to surface).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, Protocol, runtime_checkable

from sam.shared.page_styles import SUPPORTED_ATTRIBUTES

__all__ = [
    "LookAndFeelSettingsService",
    "LookAndFeelSettingsReader",
    "LookAndFeelSettingsWriter",
    "LookAndFeelValidationError",
    "CrossTenantCopyError",
    "APPLICATION_FORM_PAGE_ID",
    "DEFAULT_PAGE_ID",
]

#: The forward-looking ``page_id`` that resolves to the application form's ``look_and_feel`` slice
#: on ``config#fields`` — the ONLY SAM-owned page wired in this feature (DD-2). Kept as a named
#: seam so the generalization to more page types is a later, additive change (steering 37).
APPLICATION_FORM_PAGE_ID = "application_form"

#: ``page_id`` defaults to the application form when a caller omits it — today the single page.
DEFAULT_PAGE_ID = APPLICATION_FORM_PAGE_ID

#: The page ids this service can address TODAY. An id outside this set is rejected (never silently
#: routed to the application form). Widened additively when a second SAM-owned page is wired (Req 6).
_KNOWN_PAGE_IDS = frozenset({APPLICATION_FORM_PAGE_ID})

# ─── Permitted VALUE sets per attribute (Req 4.5) ───────────────────────────────────────
# The enum attributes have a CLOSED permitted set mirroring the Layer-2 generator's own lookup
# maps (``sam/shared/page_styles``: _SPACING_MAP / _GLOBAL_RADIUS_MAP / _SHADOW_MAP). A value the
# service accepts is therefore a value the generator renders meaningfully — a value outside the set
# is rejected (Req 4.5) rather than silently falling back to the generator's map default. These are
# kept in lock-step with the generator's maps by the parity test in the paired test file.
_PERMITTED_VALUES: dict[str, frozenset[str]] = {
    "base_spacing": frozenset({"compact", "normal", "relaxed"}),
    "border_radius_global": frozenset({"sharp", "rounded", "pill"}),
    "shadow_style": frozenset({"none", "subtle", "medium", "dramatic"}),
}

#: Hex-colour attributes — a value must be a ``#RGB`` or ``#RRGGBB`` hex string (Req 4.5). This is
#: the permitted set for an open-ended colour value: it keeps a malformed / injection-shaped value
#: out of the stored slice (the Layer-2 generator also sanitises, but a rejected value never reaches
#: storage at all).
_COLOUR_ATTRIBUTES = frozenset({"color_primary", "color_accent"})
_HEX_COLOUR_PATTERN = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")

#: Font attributes — a value must be a non-blank font-family name (``system`` or a web-font name).
#: The permitted set is "a reasonable font-family token": a non-blank string of letters, digits,
#: spaces and hyphens (no quotes, braces, colons, parentheses — the characters a CSS-injection or a
#: ``url(...)`` / ``expression(...)`` payload would need). ``system`` selects the native stack.
_FONT_ATTRIBUTES = frozenset({"font_heading", "font_body"})
_FONT_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 \-]{0,63}$")

# ─── The three NEW values-only attributes (bugfix bugfix-published-form-styling, Task 10) ─────
# Permitted-value rules for the deliberate seven→ten extension (bugfix 3.4 / design §C,
# DD-C1). These sit alongside the enum / colour / font rules above and are enforced by
# ``_require_permitted_value`` BEFORE any write, exactly like the original seven — an
# out-of-range value is REJECTED and the stored values are left UNCHANGED (Req 4.5 / bugfix 3.4).

#: ``columns`` — a BOUNDED integer (DD-C1): the number of layout columns for the application-form
#: field groups. The permitted set is the CLOSED integer range the Layer-2 generator's grid clamps
#: to (``sam/shared/page_styles``: ``1 .. _MAX_FORM_COLUMNS``). A value the service accepts is
#: therefore a value the generator renders meaningfully (parity pinned by the paired test). An
#: out-of-range or non-integer value (incl. a bool — ``bool`` is an ``int`` subclass, excluded
#: explicitly) is rejected. An integer-valued string (e.g. ``"3"``) is accepted — the authoring
#: edge may carry the value as text — and coerced to its ``int`` before the bounds check.
_COLUMNS_ATTRIBUTE = "columns"
_MIN_COLUMNS = 1
_MAX_COLUMNS = 4

#: ``logo`` — a well-formed URL / asset REFERENCE (never a CSS/binary upload — values-only,
#: steering 39 / DD-C1). The permitted set is a bounded ``https://`` (or a site-relative ``/...``)
#: reference with no CSS-injection shape (no quotes, whitespace, angle brackets, or a
#: ``javascript:`` / ``data:`` / ``url(`` / ``expression(`` payload). The renderer escapes it on
#: output (Task 6); rejecting a malformed reference here keeps it out of the stored slice entirely.
_LOGO_ATTRIBUTE = "logo"
_MAX_LOGO_LENGTH = 2048
_LOGO_REFERENCE_PATTERN = re.compile(r"^(?:https://|/)[^\s\"'<>\\]+$")
#: Injection shapes that must never appear anywhere in a ``logo`` reference even if the overall
#: shape matched (defence-in-depth; the renderer also escapes). Matched case-insensitively.
_LOGO_UNSAFE_PATTERN = re.compile(
    r"(javascript\s*:|data\s*:|url\s*\(|expression\s*\()", re.IGNORECASE
)

#: ``header_title`` — length-bounded FREE TEXT (DD-C1): the form header/title. Any non-blank string
#: within the length bound is permitted; it is HTML-escaped on render (Task 6, the same contract as
#: field labels), so no character class is forbidden here — only the length is bounded so an
#: unbounded blob cannot be stored. A blank/whitespace-only value is rejected (use an explicit
#: ``None`` to CLEAR — the steering-39 clear-vs-unchanged contract).
_HEADER_TITLE_ATTRIBUTE = "header_title"
_MAX_HEADER_TITLE_LENGTH = 200


class LookAndFeelValidationError(ValueError):
    """A deliberate, caller-safe rejection of an unsupported attribute or an out-of-set value.

    Raised BEFORE any writer call (Req 3.4 / Req 4.5) so the Page's previously stored values are
    left UNCHANGED by construction. The message names the rejected attribute (and, for a value
    rejection, the rejected value) — the client's own key/value, safe to surface — so the edge can
    map it to a 422 identifying the rejected setting (steering 30/37; no internals, no ``str(e)``).
    Subclasses :class:`ValueError` so an existing ``except ValueError`` edge keeps working.
    """


class CrossTenantCopyError(PermissionError):
    """A copy whose source Page belongs to a DIFFERENT tenant than the verified target (Req 9.4).

    Raised BEFORE any source read or target write, so neither tenant's state is touched. The copy is
    permitted ONLY within a single verified tenant; a source from another tenant is a boundary
    violation the edge maps to a caller-safe **403** ("not permitted"), NOT a validation 422 — so it
    is a distinct type from :class:`LookAndFeelValidationError`. The message is generic (it must not
    confirm whether the other tenant or page exists — no cross-tenant information leak).
    Subclasses :class:`PermissionError` so an edge can branch on it cleanly.
    """


@runtime_checkable
class LookAndFeelSettingsReader(Protocol):
    """Resolved-view READ seam for the ``look_and_feel`` slice (injected — no boto3 in the domain).

    Mirrors the reader seam
    :meth:`sam.members.repository.projection_config_reader.MembersProjectionReader.get_look_and_feel`
    (task 4.2): a tenant-scoped, VALUES-ONLY resolved read restricted to the seven supported
    attributes; absent slice/key → empty mapping (Layer 2 then applies its own defaults). Tests
    inject an in-memory fake.
    """

    def get_look_and_feel(self, tenant_id: str) -> Mapping[str, Any]: ...


@runtime_checkable
class LookAndFeelSettingsWriter(Protocol):
    """Change-Op WRITE seam for the ``look_and_feel`` slice (injected — no boto3 in the domain).

    Mirrors the writer adapter on
    :class:`~sam.members.domain.config_fields_crud_service.ConfigFieldsCrudService` (task 4.5): each
    method is a SINGLE path-scoped, version-conditional ``update_item`` (never a whole-record
    ``put_item``). This service calls only :meth:`set_look_and_feel` / :meth:`remove_look_and_feel`;
    :meth:`copy_look_and_feel` is used by task 5.3 (``copy_settings``), declared here so the one
    writer seam is complete. Tests inject an in-memory fake that records the ops.
    """

    def set_look_and_feel(
        self, tenant_id: str, attribute: str, value: Any, *, client_op_id: str | None = ...
    ) -> dict: ...

    def remove_look_and_feel(
        self, tenant_id: str, attribute: str, *, client_op_id: str | None = ...
    ) -> dict: ...

    def copy_look_and_feel(
        self, tenant_id: str, snapshot_values: Mapping[str, Any], *, client_op_id: str | None = ...
    ) -> dict: ...


class LookAndFeelSettingsService:
    """Layer-1 authoring authority for a Page's ``Look_And_Feel_Settings`` VALUES (design C3).

    A pure domain service (no boto3, steering 35/39) over an injected resolved-view reader and a
    Change-Op writer. It reads and authors the application form's presentation VALUES — the distinct
    named ``look_and_feel`` slice on ``config#fields`` (DD-2) — and never touches generated CSS
    (that is Layer 2).

    Args:
        reader: a :class:`LookAndFeelSettingsReader` — the resolved-view read seam
            (``get_look_and_feel(tenant_id)``). In production the real ``MembersProjectionReader``;
            in tests an in-memory fake.
        writer: a :class:`LookAndFeelSettingsWriter` — the Change-Op write seam
            (``set_look_and_feel`` / ``remove_look_and_feel`` / ``copy_look_and_feel``). In
            production the real ``ConfigFieldsCrudService`` adapter; in tests an in-memory fake.
    """

    def __init__(
        self,
        reader: LookAndFeelSettingsReader,
        writer: LookAndFeelSettingsWriter,
    ):
        self._reader = reader
        self._writer = writer

    # ── READ: resolved-view get of the stored VALUES (absent → defaults) ────────────────

    def get_settings(
        self, tenant_id: str, page_id: str = DEFAULT_PAGE_ID
    ) -> Mapping[str, Any]:
        """Return the Page's resolved ``Look_And_Feel_Settings`` VALUES, tenant-scoped (Req 2.4).

        A resolved-view read of the stored ``look_and_feel`` slice via the injected reader. An
        absent slice (or an absent key within it) resolves to an EMPTY mapping — Layer 2 then
        applies its own SAM-owned default for each unset attribute (Req 3.3 / 4.4 / 5.4). VALUES
        only; never generated CSS and never a Flask value (Req 2.1).

        ``page_id`` resolves today to the application form's slice (the one SAM-owned page); an
        unknown id is rejected (:class:`LookAndFeelValidationError`), never silently routed.
        """
        self._require_known_page(page_id)
        resolved = self._reader.get_look_and_feel(tenant_id)
        # Defensive: the reader contract is a mapping, but keep the resolved-view guarantee here too
        # (a non-mapping degrades to "absent" → defaults, never a raise — absent is always valid).
        if not isinstance(resolved, Mapping):
            return {}
        return dict(resolved)

    # ── WRITE: author ONE attribute value (validate, then a single scoped Change-Op) ────

    def set_setting(
        self,
        tenant_id: str,
        page_id: str,
        attribute: str,
        value: Any,
        *,
        client_op_id: str | None = None,
    ) -> dict:
        """Author ONE look-and-feel attribute VALUE for the Page (Req 8.1).

        Validates the ``attribute`` against the supported set (the ten in
        :data:`~sam.shared.page_styles.SUPPORTED_ATTRIBUTES` — Req 3.4) and the
        ``value`` against that attribute's permitted set (Req 4.5) BEFORE any write. An unsupported
        attribute or an out-of-set value raises :class:`LookAndFeelValidationError` and issues NO
        Change-Op — so the Page's previously stored values are left UNCHANGED by construction
        (Req 4.5). A valid change is a SINGLE scoped, version-conditional Change-Op via the injected
        writer (steering 39 — never a whole-record replace); a concurrent edit surfaces as the
        writer's ``StaleVersionError`` (caller-safe 409), passed through unchanged.

        An explicit ``value`` of ``None`` CLEARS the attribute (revert to the Layer-2 default) via
        the writer's scoped ``REMOVE`` — the steering-39 clear-vs-unchanged contract; no value
        validation is needed to clear.

        ``page_id`` resolves today to the application form's slice; an unknown id is rejected.
        """
        self._require_known_page(page_id)
        attr = self._require_supported_attribute(attribute)

        # Clear-vs-set (steering 39): an explicit None REMOVEs the attribute (revert to default).
        if value is None:
            return self._writer.remove_look_and_feel(
                tenant_id, attr, client_op_id=client_op_id
            )

        self._require_permitted_value(attr, value)
        return self._writer.set_look_and_feel(
            tenant_id, attr, value, client_op_id=client_op_id
        )

    # ── COPY: one-time snapshot of one Page's values onto another (same tenant, no link) ─

    def copy_settings(
        self,
        tenant_id: str,
        source_page_id: str,
        target_page_id: str,
        *,
        source_tenant_id: str | None = None,
        client_op_id: str | None = None,
    ) -> dict:
        """Copy a Page's look-and-feel VALUES onto another Page as a ONE-TIME snapshot (Req 9).

        Reads the source Page's resolved VALUES via the injected reader and writes them onto the
        target Page as a SINGLE ``SET look_and_feel = :snapshot`` Change-Op (via the writer's
        ``copy_look_and_feel``) — OVERWRITING the target's existing values (Req 9.1 / 9.3). The copy
        is a plain value snapshot: it establishes NO ongoing link or inheritance between source and
        target, so a later change to either Page leaves the other untouched by construction
        (Req 9.2 / 9.5) — nothing is wired between them to propagate.

        Same tenant only (Req 9.4): the copy runs within the ONE verified ``tenant_id``.
        ``source_tenant_id`` defaults to ``tenant_id`` (the common same-tenant copy). If a caller
        supplies a ``source_tenant_id`` that differs from the verified ``tenant_id``, the copy is
        REJECTED with :class:`CrossTenantCopyError` BEFORE any read or write — neither tenant's
        state is touched, and the edge maps it to a caller-safe 403. The source is read scoped to the
        verified tenant only; there is no path that reads another tenant's slice.

        ``source_page_id`` / ``target_page_id`` resolve today to the single SAM-owned page (the
        application form); an unknown id on either side is rejected (:class:`LookAndFeelValidationError`),
        never silently routed. A concurrent edit on the target surfaces as the writer's
        ``StaleVersionError`` (caller-safe 409), passed through unchanged.

        An absent/empty source slice is a VALID snapshot — it overwrites the target to "all
        defaults" (Layer 2 then applies its SAM-owned default per attribute); copying is not a
        validation of values, so no per-value check is performed here.
        """
        # Cross-tenant guard FIRST (Req 9.4): reject before any read or write so neither tenant's
        # state is observed or touched. Default source tenant to the verified tenant (same-tenant).
        effective_source_tenant = (
            tenant_id if source_tenant_id is None else source_tenant_id
        )
        if effective_source_tenant != tenant_id:
            raise CrossTenantCopyError(
                "copy is permitted only within a single tenant"
            )

        # Both page ids must be addressable today (never silently routed to the application form).
        self._require_known_page(source_page_id)
        self._require_known_page(target_page_id)

        # One-time snapshot: read the source's resolved VALUES (scoped to the verified tenant),
        # then a single scoped SET overwrites the target — no link is established between them.
        snapshot = self._reader.get_look_and_feel(tenant_id)
        snapshot_values = dict(snapshot) if isinstance(snapshot, Mapping) else {}
        return self._writer.copy_look_and_feel(
            tenant_id, snapshot_values, client_op_id=client_op_id
        )

    # ── Validation helpers (all raise BEFORE any write → stored values unchanged) ───────

    @staticmethod
    def _require_known_page(page_id: str) -> str:
        """Reject a page id the service cannot address today (never silently route it).

        Today only :data:`APPLICATION_FORM_PAGE_ID` is wired (DD-2). An unknown id raises
        :class:`LookAndFeelValidationError` rather than defaulting to the application form, so a
        future page type is added by a deliberate, reviewed change (steering 37).
        """
        if not isinstance(page_id, str) or page_id not in _KNOWN_PAGE_IDS:
            raise LookAndFeelValidationError(
                f"unknown page {page_id!r}: look-and-feel is wired only for "
                f"{sorted(_KNOWN_PAGE_IDS)!r} today"
            )
        return page_id

    @staticmethod
    def _require_supported_attribute(attribute: str) -> str:
        """Return ``attribute`` iff it is one of the supported attributes (the ten — Req 3.4).

        An unsupported attribute (or a non-string) is rejected BEFORE any write — the request
        produces no styling and no stored change (Req 3.4). The offending key is the client's own,
        safe to name in the caller-facing message.
        """
        if not isinstance(attribute, str) or attribute not in SUPPORTED_ATTRIBUTES:
            raise LookAndFeelValidationError(
                f"unsupported look-and-feel attribute {attribute!r}: supported attributes are "
                f"{sorted(SUPPORTED_ATTRIBUTES)!r}"
            )
        return attribute

    @staticmethod
    def _require_permitted_value(attribute: str, value: Any) -> None:
        """Reject a value outside the attribute's permitted set (Req 4.5), BEFORE any write.

        - Enum attributes (``base_spacing`` / ``border_radius_global`` / ``shadow_style``): the
          value must be one of the closed permitted set mirroring the Layer-2 generator's maps.
        - Colour attributes (``color_primary`` / ``color_accent``): a ``#RGB`` / ``#RRGGBB`` hex.
        - Font attributes (``font_heading`` / ``font_body``): a non-blank font-family token
          (``system`` or a web-font name), restricted to safe characters.
        - ``columns`` (bugfix extension, DD-C1): a bounded integer (or integer-valued string) in
          ``_MIN_COLUMNS .. _MAX_COLUMNS``, mirroring the Layer-2 generator's grid clamp.
        - ``logo`` (bugfix extension, DD-C1): a well-formed, bounded ``https://`` / site-relative
          URL/asset reference with no injection payload — never a CSS/binary upload (values-only).
        - ``header_title`` (bugfix extension, DD-C1): non-blank, length-bounded free text
          (HTML-escaped on render).

        A rejection leaves the stored values unchanged (no Change-Op is issued). The rejected value
        is the client's own, safe to name in the caller-facing message.
        """
        if attribute in _PERMITTED_VALUES:
            permitted = _PERMITTED_VALUES[attribute]
            if value not in permitted:
                raise LookAndFeelValidationError(
                    f"invalid value {value!r} for {attribute!r}: permitted values are "
                    f"{sorted(permitted)!r}"
                )
            return

        if attribute in _COLOUR_ATTRIBUTES:
            if not isinstance(value, str) or not _HEX_COLOUR_PATTERN.match(value):
                raise LookAndFeelValidationError(
                    f"invalid value {value!r} for {attribute!r}: expected a hex colour "
                    f"(e.g. '#2D5F8A' or '#abc')"
                )
            return

        if attribute in _FONT_ATTRIBUTES:
            if not isinstance(value, str) or not _FONT_NAME_PATTERN.match(value):
                raise LookAndFeelValidationError(
                    f"invalid value {value!r} for {attribute!r}: expected a font-family name "
                    f"(e.g. 'system' or 'Inter')"
                )
            return

        # ── The three NEW values-only attributes (bugfix bugfix-published-form-styling, Task 10) ──

        if attribute == _COLUMNS_ATTRIBUTE:
            # Bounded integer (DD-C1). Accept an int or an integer-valued string (the edge may
            # carry the value as text); reject a bool (an ``int`` subclass that is not a real
            # column count), a non-integer, or an out-of-range value. The accepted range mirrors
            # the Layer-2 generator's grid clamp (1 .. _MAX_FORM_COLUMNS), pinned by the paired
            # parity test.
            if isinstance(value, bool):
                raise LookAndFeelValidationError(
                    f"invalid value {value!r} for {attribute!r}: expected an integer in "
                    f"{_MIN_COLUMNS}..{_MAX_COLUMNS}"
                )
            if isinstance(value, int):
                column_count = value
            elif isinstance(value, str) and re.fullmatch(r"-?\d+", value.strip()):
                column_count = int(value.strip())
            else:
                raise LookAndFeelValidationError(
                    f"invalid value {value!r} for {attribute!r}: expected an integer in "
                    f"{_MIN_COLUMNS}..{_MAX_COLUMNS}"
                )
            if not (_MIN_COLUMNS <= column_count <= _MAX_COLUMNS):
                raise LookAndFeelValidationError(
                    f"invalid value {value!r} for {attribute!r}: expected an integer in "
                    f"{_MIN_COLUMNS}..{_MAX_COLUMNS}"
                )
            return

        if attribute == _LOGO_ATTRIBUTE:
            # A well-formed, bounded URL/asset reference — never a CSS/binary upload (values-only,
            # DD-C1). Reject a non-string, an over-length value, a value whose shape is not an
            # https:// (or site-relative '/...') reference, or one carrying an injection payload.
            if (
                not isinstance(value, str)
                or len(value) > _MAX_LOGO_LENGTH
                or not _LOGO_REFERENCE_PATTERN.match(value)
                or _LOGO_UNSAFE_PATTERN.search(value)
            ):
                raise LookAndFeelValidationError(
                    f"invalid value for {attribute!r}: expected a well-formed URL/asset "
                    f"reference (e.g. 'https://…/logo.png' or '/assets/logo.png')"
                )
            return

        if attribute == _HEADER_TITLE_ATTRIBUTE:
            # Length-bounded free text (DD-C1). HTML-escaped on render, so no character class is
            # forbidden — only a non-string, a blank/whitespace-only value, or an over-length value
            # is rejected (use an explicit None to CLEAR).
            if (
                not isinstance(value, str)
                or not value.strip()
                or len(value) > _MAX_HEADER_TITLE_LENGTH
            ):
                raise LookAndFeelValidationError(
                    f"invalid value for {attribute!r}: expected non-blank text of at most "
                    f"{_MAX_HEADER_TITLE_LENGTH} characters"
                )
            return

        # Unreachable while the attribute is one of SUPPORTED_ATTRIBUTES (every supported attribute
        # is covered above). Guard defensively so a newly-added attribute without a permitted-set
        # rule fails loud rather than silently accepting any value.
        raise LookAndFeelValidationError(
            f"no permitted-value rule defined for attribute {attribute!r}"
        )
