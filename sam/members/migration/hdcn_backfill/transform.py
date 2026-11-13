"""map_hdcn_row: the pure raw-row -> member-record transform.

Part of the h-dcn backfill package (code-quality-fixes-2026-11-12 task 3).
"""

from __future__ import annotations

import datetime as _dt
import uuid
from collections.abc import Mapping
from typing import Any

from sam.members.domain.fixed_fields import (
    FieldValidationError,
    validate_fixed_fields,
)

from .field_values import (
    _MEMBER_NUMBER_FORMAT_RE,
    ColumnShiftWarning,
    DuplicateHeaderConflict,
    _clean,
    _iso_date_part,
    _load_default_contract,
    _normalize_email,
    _normalize_gender,
    _normalize_magazine,
    _parse_source_date,
    _read_sam_code,
    _row_has_meaningful_data,
    _skip_label,
    _split_iban_or_payment,
    _year_to_iso,
    detect_column_shift,
)
from .source_layout import (
    _NULL_REGION_CANONICALIZER,
    HDCN_TENANT_ID,
    RegionCanonicalizer,
    _base_header,
)
from .vocabulary import (
    _DEFAULT_MEMBERSHIP_STATUS,
    _JOINED_DATE_DATE_SOURCES,
    _JOINED_DATE_YEAR_SOURCE,
    _REGION_FIELD_KEY,
    MembershipTypeMapper,
    RowSkipped,
    RowTransformError,
)


def map_hdcn_row(
    raw_row: Mapping[str, Any],
    *,
    type_mapper: MembershipTypeMapper | None = None,
    tenant_id: str = HDCN_TENANT_ID,
    region_canonicalizer: RegionCanonicalizer | None = None,
    conflicts: list[DuplicateHeaderConflict] | None = None,
    shift_warnings: list[ColumnShiftWarning] | None = None,
    contract: Any = None,
) -> dict[str, Any]:
    """Map ONE raw h-dcn member row to a member record for the new model (pure, no I/O).

    The produced record matches the design data model (S5d D1: NO ``scope_values`` bucket —
    scope is a plain member field)::

        { tenant_id, member_id,
          personal:   { first_name, last_name, name_infix, initials, gender, email, phone,
                        street, postal_code, city, country, birth_date },
          membership: { member_number, status, membership_type, joined_date },
          overlay:    { region: <canonical region>,     # h-dcn: the scope FIELD, a scalar
                        <canonical overlay key>: <value>, ..., additional_info: <concat> } }

    **Contract-driven (s5m Task 3, R0.3/D0).** The source→target mapping and every non-mapped
    column's disposition come from the loaded :class:`MappingContract` (task 2's
    ``members_mapping_loader.load_mapping_contract``) — NOT hardcoded dicts. Pass an explicit
    ``contract`` (the runner does, once per batch) or leave it ``None`` to lazily load + cache
    the authored default (``scripts/onboarding/members/h-dcn/members_source_mapping.csv``). Each column is
    resolved in this order (design D2b): **FIXED → OVERLAY → CALCULATED (skip) → EXCLUDED (skip)
    → additional_info** (anything mapped nowhere, kept, is concatenated into
    ``overlay.additional_info``).

    Per-``rule`` conversions applied to the coalesced source value (R0.2/R0.3):
    - ``single`` / ``coalesce`` — copy (string), first-non-empty across duplicate/ordered columns;
    - ``date`` — ISO datetime → bare ``YYYY-MM-DD`` (``birth_date`` optional, and the membership
      ``deregistration_date`` / ``termination_date`` overlay dates; absent/unparseable → unset);
    - ``member_number`` — READ VERBATIM (trimmed) from the authoritative ``SAM Code`` column
      (Members ``M#####`` / Donateurs ``D#####`` / Contacts ``C#####``); validated against the
      format regex. A meaningful row with a blank/malformed ``SAM Code`` is a data-gap error
      (reported, not written); an empty/spacer row is skipped. It is NEVER derived/regenerated;
    - ``membership_type`` — free text → catalog ``type_code`` (via ``type_mapper``, C8);
    - ``region`` — canonicalized onto the tenant region value set (a scalar ``overlay.region``);
    - ``gender`` — Dutch ``Man``/``Vrouw`` (and ``m``/``v``) → tenant enum ``M``/``V``;
    - ``magazine`` — ``Clubblad`` → ``magazine_pref`` (``Geen``/``Papier``/``Digitaal``, fallback
      ``Geen``);
    - ``iban_or_payment`` — one ``Bankrekeningnummer`` → ``overlay.iban`` + ``overlay.
      payment_method`` (valid IBAN → iban + ``incasso``; non-IBAN text → payment_method=text).

    ``tenant_id`` defaults to the pilot ``"h-dcn"`` (the value the backfill stamps). Raises
    :class:`RowTransformError` if the row cannot produce a valid fixed record.

    **Duplicate-header safety (R1.3/R1.4/R1.6).** The adapters hand this transform a
    collision-free row where a repeated source header has been position-tracked to
    ``<header>#<colindex>`` (:func:`build_position_tracked_row`). Here each column key is first
    stripped back to its BASE header (:func:`_base_header`) before consulting the contract, so
    every column sharing a base feeds the SAME target and is combined by first-non-empty
    COALESCE: the first non-empty value in column order wins; a later empty NEVER overwrites it.
    Two DIFFERENT non-empty values sharing a base are a genuine conflict — the first is kept and
    the loser is recorded (by its INDEXED column name) into the optional ``conflicts`` list for
    the fidelity report (R1.6). A blank-named column is still dropped (R1.5).

    **Data-quality safeguards (R8.1, ported from h-dcn's importer).** ``personal.email`` cells
    that are NO-VALID-EMAIL placeholders (``geen email``, ``n.v.t.``, …) are treated as EMPTY so
    a fake marker never wins the coalesce nor lands as a deliverable address. If a
    ``shift_warnings`` list is supplied, column-shift signals (a year in ``Geslacht``, a gender
    token in ``Regio``) are appended to it for the report — a warning only; nothing is blocked
    or rewritten.
    """
    mapper = type_mapper or MembershipTypeMapper()
    contract = contract if contract is not None else _load_default_contract()

    # ── SAM Code identity + empty-row skip ─────────────────────────────────────────────
    # The authoritative human ``member_number`` is READ from the ``SAM Code`` column verbatim
    # (user-approved identity change) — no longer DERIVED from Lidnummer/Achternaam. Read it up
    # front (on its BASE header, so a position-tracked duplicate is matched like its bare sibling)
    # to drive both the empty-row skip and the member_number below.
    sam_code = _read_sam_code(raw_row)

    # Empty/spacer row: NO meaningful data (no populated cell — a NO-VALID-EMAIL placeholder and
    # the blank-named column count as empty). Skipped SILENTLY (RowSkipped) regardless of SAM
    # Code — never an error, never written. A meaningful row with a blank SAM Code is NOT skipped
    # here; it becomes a data-gap error below.
    if not _row_has_meaningful_data(raw_row):
        raise RowSkipped("empty row (no meaningful data)", label="<empty>")

    personal: dict[str, Any] = {}
    membership: dict[str, Any] = {}
    overlay: dict[str, Any] = {}
    reasons: dict[str, str] = {}
    conflict_out = conflicts if conflicts is not None else []

    # Column-shift detection (R8.1, data-quality safeguard): flag year-in-Geslacht /
    # gender-in-Regio into the optional ``shift_warnings`` list for the fidelity report. Never
    # blocks the row nor rewrites a value — the operator inspects the flagged source column.
    if shift_warnings is not None:
        shift_warnings.extend(detect_column_shift(raw_row))

    # First-non-empty COALESCE bookkeeping (R1.3/R1.4): a logical slot is "filled" by the FIRST
    # column (in row order) that carries a non-empty value for it. Later columns sharing the same
    # base header either agree (no-op) or conflict (recorded, first-in-order kept). Keyed by a
    # stable slot id (the dotted target, "overlay:<key>", "additional_info:<base>", …); carries
    # the kept RAW value + the INDEXED column that supplied it, so a later conflict can name the
    # loser. ``slot_raw`` holds the accepted raw value so the rule conversion runs AFTER the loop
    # (once every column sharing a base has been seen — a blank duplicate can never mask a
    # populated sibling, R1.4).
    filled: dict[str, tuple[str, str]] = {}
    slot_raw: dict[str, Any] = {}
    #: Additional-info accumulator: ordered (label, value) pairs collected in source-column order
    #: and joined into ``overlay.additional_info`` after the loop (R2.7).
    additional: list[tuple[str, str]] = []
    #: joined_date source values collected PER source base header (lower-cased) — NOT collapsed
    #: into the one column-order coalesce slot. joined_date has several contract inputs
    #: (``Datum ondertekening`` / ``Tijdstempel`` / ``Aanmeldingsjaar``) that must be combined by
    #: an EXPLICIT PRIORITY order (below), not by their raw sheet-column order (``Tijdstempel`` is
    #: col 0, so a plain first-non-empty-in-column-order coalesce would wrongly let it beat the
    #: authoritative ``Datum ondertekening`` at col 30). First non-empty per base header is kept.
    joined_date_by_source: dict[str, str] = {}

    def _coalesce(slot: str, indexed_column: str, base: str, new_value: Any) -> bool:
        """Return True if ``slot`` should accept ``new_value`` now (first non-empty wins).

        Records a :class:`DuplicateHeaderConflict` (and returns False) when the slot is already
        filled by a DIFFERENT non-empty value from an earlier column (R1.6). A later empty value
        never reaches here (callers guard on ``cleaned is not None``), so it can never overwrite.
        """
        new_str = (
            str(new_value).strip()
            if not isinstance(new_value, str)
            else new_value.strip()
        )
        prior = filled.get(slot)
        if prior is None:
            filled[slot] = (new_str, indexed_column)
            return True
        kept_value, _kept_col = prior
        if kept_value != new_str:
            conflict_out.append(
                DuplicateHeaderConflict(
                    base_header=base,
                    losing_column=indexed_column,
                    kept_value=kept_value,
                    dropped_value=new_str,
                )
            )
        return False  # a genuine duplicate (equal or conflicting) — first-in-order already kept

    # PASS 1 (in column order): coalesce each source column onto its contract slot. The rule
    # CONVERSION is deferred to pass 2 so a blank duplicate can never mask a populated sibling.
    for column, value in raw_row.items():
        indexed_column = (column or "").strip()
        # R1.3: match on the BASE header — strip a position-tracking `#<colindex>` suffix so a
        # duplicated header resolves to the SAME target as its bare sibling and coalesces.
        base = _base_header(indexed_column)
        col_lower = base.lower()
        cleaned = _clean(value)

        # R1.5: a blank-named source column is dropped (DynamoDB rejects an empty attribute
        # name). Its index was already consumed by the row-builder; nothing to store.
        if base == "":
            continue

        fixed_map = contract.fixed.get(col_lower)
        overlay_map = contract.overlay.get(col_lower)

        # FIXED (personal.*/membership.*) — coalesce the RAW value onto the dotted-key slot.
        if fixed_map is not None:
            slot = fixed_map.target
            # joined_date: DON'T fold its several inputs into the one column-order slot. Keep
            # each source column's first-non-empty value under its BASE header so PASS 2 can
            # combine them by an explicit PRIORITY order (Datum ondertekening → Tijdstempel →
            # Aanmeldingsjaar), independent of the columns' physical sheet order (R: joined_date
            # fallback). A position-tracked duplicate of the SAME source column still coalesces
            # (first non-empty per base header wins).
            if slot == "membership.joined_date":
                if cleaned is not None and col_lower not in joined_date_by_source:
                    joined_date_by_source[col_lower] = (
                        cleaned if isinstance(cleaned, str) else str(cleaned).strip()
                    )
                continue
            # EMAIL (R8.1): strip a NO-VALID-EMAIL placeholder to empty DURING coalesce, so a
            # fake "geen email" marker in an earlier column never wins over a real address in a
            # later duplicate — and never lands on personal.email as if it were deliverable.
            if slot == "personal.email":
                cleaned = _normalize_email(cleaned)
            if cleaned is not None and _coalesce(slot, indexed_column, base, cleaned):
                slot_raw[slot] = cleaned
            continue

        # OVERLAY (canonical overlay.* key(s)) — a `single`/`coalesce` row names one target; the
        # `iban_or_payment` conditional split names two. Coalesce the RAW source value onto a
        # slot keyed by the source base header (both targets share the one source value).
        if overlay_map is not None:
            slot = f"overlay-src:{col_lower}"
            if cleaned is not None and _coalesce(slot, indexed_column, base, cleaned):
                slot_raw[slot] = (overlay_map, cleaned)
            continue

        # CALCULATED — the value is DERIVED by a calculated field, NOT stored (R2.2/R2.6).
        if col_lower in contract.calculated:
            continue

        # EXCLUDED — deliberately dropped, unfit / (near-)duplicate (R2.6).
        if col_lower in contract.excluded:
            continue

        # additional_info (declared, R2.7) OR any unmapped-but-kept column — concatenate into
        # overlay.additional_info as `Label: value` (source header as the label). Coalesce so a
        # position-tracked duplicate does not double-count; a genuine conflict is reported.
        if cleaned is not None and _coalesce(
            f"additional_info:{col_lower}", indexed_column, base, cleaned
        ):
            additional.append((indexed_column, str(cleaned).strip()))

    # PASS 2: convert each coalesced raw value by its declared rule and write the target.

    # ── FIXED targets ────────────────────────────────────────────────────────────────
    for slot, raw in slot_raw.items():
        fmap = None
        # Only fixed slots are dotted keys present in the contract's fixed map (by target).
        for m in contract.fixed.values():
            if m.target == slot:
                fmap = m
                break
        if fmap is None:
            continue  # an overlay slot — handled below
        group, key = slot.split(".", 1)
        target = personal if group == "personal" else membership
        rule = fmap.rule

        if key == "member_number":
            # Handled after the loop from the authoritative ``SAM Code`` (read verbatim) — the
            # raw value coalesced onto this slot is NOT copied as a plain string here.
            continue
        if key == "membership_type":
            try:
                target[key] = mapper.to_code(raw)
            except ValueError as exc:
                reasons[slot] = str(exc)
            continue
        if rule == "date":
            # birth_date / joined_date etc. — reduce an ISO datetime to a bare YYYY-MM-DD. An
            # unparseable value simply leaves the (optional) field unset (R2.1/R3.3). joined_date
            # additionally gets a year/today fallback below.
            iso = _iso_date_part(raw)
            if iso is not None:
                target[key] = iso
            continue
        if rule == "gender":
            g = _normalize_gender(raw)
            if g is not None:
                target[key] = g
            continue
        # single / coalesce string copy. The JSON export carries some fixed fields as numbers
        # (Postcode / Telefoonnummer as ints), so coerce to a trimmed string for the validator.
        target[key] = str(raw).strip() if not isinstance(raw, str) else raw

    # joined_date — derived from its several contract inputs by an EXPLICIT PRIORITY order, NOT
    # the columns' raw sheet order. Each input's value was collected per base header in PASS 1.
    #   1. Datum ondertekening (the signature date — authoritative) parsed as a date;
    #   2. else Tijdstempel (the member-since timestamp — the widest-populated column, 1215/1242)
    #      parsed as a date — the fallback added so a member with no signature date but a
    #      timestamp gets a REAL join date instead of today;
    #   3. else Aanmeldingsjaar (a bare registration year) → <year>-01-01;
    #   4. else default to today so a real member is never dropped for a missing join date
    #      (A.2 decision).
    # Both date inputs go through the SAME date parser (Dutch d-m-yyyy AND ISO) — the fix that
    # stops every real Dutch date falling through to today.
    joined_date: str | None = None
    for _src in _JOINED_DATE_DATE_SOURCES:  # date-valued inputs, in priority order
        _val = joined_date_by_source.get(_src)
        if _val is not None:
            joined_date = _parse_source_date(_val)
            if joined_date is not None:
                break
    if joined_date is None:  # year fallback (Aanmeldingsjaar → <year>-01-01)
        _year_val = joined_date_by_source.get(_JOINED_DATE_YEAR_SOURCE)
        if _year_val is not None:
            joined_date = _year_to_iso(_year_val)
    membership["joined_date"] = joined_date or _dt.date.today().isoformat()

    # ── OVERLAY targets (canonical keys) ───────────────────────────────────────────────
    region_raw: str | None = None
    for slot, payload in slot_raw.items():
        if not slot.startswith("overlay-src:"):
            continue
        overlay_map, raw = payload
        rule = overlay_map.rule

        if rule == "region":
            # Deferred: canonicalized after the loop (needs the injected canonicalizer). Stored
            # on the plain `overlay.region` field as a SCALAR (S5d D1 — no scope_values bucket).
            if isinstance(raw, str):
                region_raw = raw
            continue
        if rule == "iban_or_payment":
            iban, payment = _split_iban_or_payment(raw)
            if iban is not None:
                overlay["iban"] = iban
            if payment is not None:
                overlay["payment_method"] = payment
            continue
        if rule == "magazine":
            overlay[overlay_map.targets[0]] = _normalize_magazine(raw)
            continue
        if rule == "date":
            # Filterable overlay date fields (deregistration_date / termination_date): stored
            # only when the source parses to a date, else left unset (R2.3).
            iso = _iso_date_part(raw)
            if iso is not None:
                overlay[overlay_map.targets[0]] = iso
            continue
        # single / coalesce — copy onto the canonical overlay key (string).
        overlay[overlay_map.targets[0]] = (
            str(raw).strip() if not isinstance(raw, str) else raw
        )

    # membership_type is a REQUIRED fixed field. Flag it missing only if NO column supplied a
    # value and no code was mapped (a blank duplicate never masks a populated sibling, R1.4).
    if (
        "membership_type" not in membership
        and "membership.membership_type" not in reasons
        and "membership.membership_type" not in slot_raw
    ):
        reasons["membership.membership_type"] = "is required"

    # ── member_number — READ from the authoritative ``SAM Code`` (identity change) ──────
    # The human number is READ verbatim from the ``SAM Code`` column (Members ``M#####`` /
    # Donateurs ``D#####`` / Contacts ``C#####``), NOT derived from Lidnummer/Achternaam. This
    # row already passed the empty-row test above, so it IS a meaningful data row:
    #   - a present, non-blank SAM Code that MATCHES the format → used verbatim as member_number;
    #   - a present SAM Code that does NOT match the format → a data-gap error (reported, not
    #     written) — the authoritative code is malformed and must be fixed at source;
    #   - a BLANK/absent SAM Code on a meaningful row → a data-gap error (reported, not written):
    #     a missing code is a real gap, NOT something to silently derive around (user-approved).
    if sam_code is None:
        reasons["membership.member_number"] = (
            "meaningful row has a blank 'SAM Code' — the authoritative member number is missing "
            "(fix the source; the importer never derives it)"
        )
    elif not _MEMBER_NUMBER_FORMAT_RE.match(sam_code):
        reasons["membership.member_number"] = (
            f"'SAM Code' {sam_code!r} does not match the member-number format "
            f"{_MEMBER_NUMBER_FORMAT_RE.pattern!r} (expected M#####/D#####/C#####)"
        )
    else:
        membership["member_number"] = sam_code

    # A.2 DERIVED: status — the export has no status column → default "active".
    membership.setdefault("status", _DEFAULT_MEMBERSHIP_STATUS)

    # A.2: mint a STABLE internal id (uuid4) — the export carries no member_id, and the internal
    # id is intentionally decoupled from the human `member_number`. ONBOARDING §2.
    member_id = str(uuid.uuid4())
    # Best-effort ref for the fidelity report: the member_number if valid, else the raw (possibly
    # blank/malformed) SAM Code, else a name — so a data-gap row can still be found in the source.
    member_ref = (
        membership.get("member_number") or sam_code or _skip_label(personal, overlay)
    )

    # region (deferred canonicalization): store the CANONICAL value as a SCALAR on overlay.region
    # (S5d D1/R3.4). An absent region omits the field entirely (no empty placeholder).
    if region_raw:
        canon = region_canonicalizer or _NULL_REGION_CANONICALIZER
        overlay[_REGION_FIELD_KEY] = canon.canonical(region_raw)

    # additional_info (R2.7): concatenate the kept leftovers as `Label: value` pairs in stable
    # source-column order, ` | ` delimiter, only non-empty cells. Unset if nothing contributed.
    info = " | ".join(f"{label}: {val}" for label, val in additional if val)
    if info:
        overlay["additional_info"] = info

    record: dict[str, Any] = {
        "tenant_id": tenant_id,
        "member_id": member_id,
        "personal": personal,
        "membership": membership,
        "overlay": overlay,
    }

    # Validate the FIXED half loudly so a bad mapping never becomes a silent write.
    try:
        validate_fixed_fields(record)
    except FieldValidationError as exc:
        reasons.update(exc.errors)

    if reasons:
        raise RowTransformError(str(member_ref), reasons)

    return record
