"""Membership-type mapping, contract source columns, row errors.

Part of the h-dcn backfill package (code-quality-fixes-2026-11-12 task 3).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

# ── Source-column contract: the SINGLE authored mapping is the CSV (R0.1/R0.2/D0) ─────
#
# s5m single-source-of-truth cleanup (R0.1/R0.4): the source→target mapping is authored in ONE
# place — ``scripts/onboarding/members/h-dcn/members_source_mapping.csv`` (parsed into a ``MappingContract`` by
# ``members_mapping_loader``). There is NO second hand-maintained Python dict that can drift from
# (or contradict) the CSV. The old module-level ``FIXED_SOURCE_COLUMNS`` / ``OVERLAY_SOURCE_
# COLUMNS`` dicts (and the source-column-name constants ``_SIGNED_DATE_COLUMN`` /
# ``_JOIN_YEAR_COLUMN`` / ``_REGION_SOURCE_COLUMN`` and the dead ``_STATUS_MAP`` /
# ``_REGION_STORAGE_GROUP``) were retired: their "which column feeds which target" knowledge now
# lives in the contract rows (the ``date``-ruled joined_date coalesce inputs, the ``region``-ruled
# source column, etc.). Only the genuinely-DERIVED logic below is code, and it sources any column
# NAMES from the loaded contract, never from a private copy.

#: Default ``membership.status`` when the source carries no status (the Ledenbestand has no status
#: column — A.2 decision): a genuinely-derived default, not source-column knowledge.
_DEFAULT_MEMBERSHIP_STATUS = "active"

#: joined_date DATE-valued source columns (BASE headers, lower-cased) in PRIORITY order. This is
#: the genuinely-DERIVED combination order for the ``membership.joined_date`` target, which the
#: contract declares via several ``coalesce`` inputs but which must be combined by an explicit
#: priority rather than by the columns' raw sheet position (``Tijdstempel`` is physically col 0
#: but is only the FALLBACK). Both inputs are parsed by :func:`_parse_source_date` (Dutch
#: day-first ``d-m-yyyy`` AND ISO). Order (user-confirmed): the signature date wins, then the
#: (widest-populated) member-since timestamp.
_JOINED_DATE_DATE_SOURCES = ("datum ondertekening", "tijdstempel")

#: joined_date bare-YEAR fallback source (BASE header, lower-cased): ``Aanmeldingsjaar`` → mapped
#: to ``<year>-01-01`` only when no date-valued input above parsed. Kept LAST in the derivation.
_JOINED_DATE_YEAR_SOURCE = "aanmeldingsjaar"

#: The member FIELD the region normalizes onto. S5d D1/R3.4: scope is a PLAIN member field —
#: the retired ``scope_values`` bucket is gone. For h-dcn ``region`` is a TENANT-ADDED field, so
#: its storage bucket is ``overlay`` (dotted key ``overlay.region``). The value is a SCALAR
#: (a member is single-valued per scope field, R3.2), never a list. This is the derived TARGET
#: key, not source-column knowledge — the SOURCE column for region is declared in the contract
#: (the row whose ``rule`` is ``region``).
_REGION_FIELD_KEY = "region"


def contract_source_columns(contract: Any) -> set[str]:
    """Return the set of BASE source headers (lower-cased) the loaded contract MAPS to a target.

    The single-source-of-truth replacement for the old ``FIXED_SOURCE_COLUMNS.keys()`` probe: it
    reads the loaded :class:`MappingContract` (task 2), so "which columns are recognized as
    mapped" can never drift from the authored CSV. Includes every FIXED (``personal.*`` /
    ``membership.*``) and OVERLAY (``overlay.*``, incl. the region column) source header. The
    disposition sets (calculated / excluded / additional_info) are deliberately EXCLUDED — a
    caller wanting the mapped-vs-unmapped split treats those as "not a mapped target".
    """
    return set(contract.fixed.keys()) | set(contract.overlay.keys())


class RowTransformError(Exception):
    """Raised when a single source row cannot be mapped to a valid member record.

    Carries ``member_ref`` (a best-effort identifier for the offending row so it can be found
    in the source) and ``reasons`` (dotted-key → why). The runner collects these per row into
    the fidelity report rather than aborting the whole dry-run on the first bad row.
    """

    def __init__(self, member_ref: str, reasons: Mapping[str, str]):
        self.member_ref = member_ref
        self.reasons = dict(reasons)
        detail = "; ".join(f"{k}: {v}" for k, v in self.reasons.items())
        super().__init__(f"row {member_ref!r} could not be mapped: {detail}")


class RowSkipped(Exception):
    """Raised when a source row is intentionally NOT a member and is skipped (not an error).

    ONE intentional-skip rule raises this today, landing the row in the plan's ``skipped``
    bucket — counted as SKIPPED, never as an error, never transformed/written:

    - **Empty/spacer row** — a row with NO meaningful data (no populated cell — where a
      NO-VALID-EMAIL placeholder counts as empty and the blank-named column is ignored). A
      placeholder-only row (e.g. ``E-mailadres`` = "GEEN GELDIG EMAILADRES") is treated as empty
      and skipped SILENTLY, regardless of its (blank) ``SAM Code``.

    A row that HAS meaningful data is NOT skipped — even one with a blank ``SAM Code``: a missing
    authoritative member number on a real data row is a data-gap ERROR (RowTransformError,
    reported, not written), not a silent skip. So over-skipping cannot hide a real member.

    Carries ``reason`` (why it was skipped) and ``label`` (a best-effort human identifier —
    e.g. the organisation name — for the report).
    """

    def __init__(self, reason: str, *, label: str = "<empty>"):
        self.reason = reason
        self.label = label
        super().__init__(f"row {label!r} skipped: {reason}")


# ── membership_type → catalog code mapping (C8; decoupled from the 4.2 seed) ──────────


class MembershipTypeMapper:
    """Maps an h-dcn source membership-type value to a Lidmaatschap Beheer catalog ``type_code``.

    h-dcn's live type vocabulary is free-form label text (e.g. "Erelid", "Donateur",
    "Sponsor"); the new model stores a catalog *code* the member references (C8). This mapper
    turns a label into a normalized code (lowercase, spaces→``_``, separators stripped) and,
    when given a set of ``known_codes``, VALIDATES that the produced code is one the catalog is
    expected to carry — surfacing a mismatch rather than inventing a code.

    It deliberately does NOT read or seed the catalog (that authoritative seed is task 4.2);
    the backfill only maps + validates the reference, keeping the two decoupled. When
    ``known_codes`` is ``None`` the mapper is permissive (any well-formed code is accepted),
    so a dry-run can run before the catalog exists and still report the codes it would write.
    """

    #: Explicit label→code overrides (applied before the generic normalization). Kept as DATA
    #: (h-dcn's known types) — not code branches — so extending it needs no logic change.
    DEFAULT_ALIASES: Mapping[str, str] = {
        "erelid": "erelid",
        "honorary member": "erelid",
        "donateur": "donateur",
        "donor": "donateur",
        "sponsor": "sponsor",
        "gewoon lid": "gewoon_lid",
        "regular member": "gewoon_lid",
        "lid": "gewoon_lid",
        # Family memberships — real h-dcn export types (gezins_lid: ~200, gezins_donateur: ~17).
        "gezins lid": "gezins_lid",
        "gezinslid": "gezins_lid",
        "family member": "gezins_lid",
        "gezins donateur": "gezins_donateur",
        "gezinsdonateur": "gezins_donateur",
        "family donor": "gezins_donateur",
        # A.4: `overig` ("Other") — an admin-gated catalog type (ONBOARDING §4 bucket 3).
        "overig": "overig",
        "other": "overig",
        # Real Ledenbestand spelling variants (census 2026-09-22) folded onto the 6+1 codes:
        "ere lid": "erelid",  # "Ere lid" (spaced) → erelid
        "gezins donateur zonder motor": "gezins_donateur",  # "...zonder motor" is not a type axis
        "donateur zonder motor": "donateur",
        # A.4 decision (ONBOARDING §6.1): "Clubblad" on a NUMBERED member → `overig`.
        # Clubblad is a magazine subscription, not a real membership type; a member who
        # carries it is imported as type "Other". (Clubblad ORGANISATION rows have no member
        # number and are skipped entirely — they never reach the type mapper.)
        "clubblad": "overig",
    }

    def __init__(
        self,
        *,
        aliases: Mapping[str, str] | None = None,
        known_codes: Iterable[str] | None = None,
    ):
        self._aliases = {
            k.strip().lower(): v for k, v in (aliases or self.DEFAULT_ALIASES).items()
        }
        self._known_codes = set(known_codes) if known_codes is not None else None

    @staticmethod
    def normalize_code(value: str) -> str:
        """Normalize a raw label to a catalog-code shape: lowercase, spaces→``_``, trimmed."""
        code = value.strip().lower()
        code = re.sub(r"\s+", "_", code)
        # A code becomes a sort-key id segment (see table_design) — drop the separator char.
        code = code.replace("#", "")
        return code

    def to_code(self, raw_value: Any) -> str:
        """Return the catalog ``type_code`` for a raw h-dcn membership-type value.

        Raises :class:`ValueError` if the value is blank, or (when ``known_codes`` was given)
        if the mapped code is not one of the expected catalog codes — a loud mismatch rather
        than a silently-invented type.
        """
        if not isinstance(raw_value, str) or not raw_value.strip():
            raise ValueError("membership type is blank")
        alias = self._aliases.get(raw_value.strip().lower())
        code = alias if alias is not None else self.normalize_code(raw_value)
        if not code:
            raise ValueError(
                f"membership type {raw_value!r} normalizes to an empty code"
            )
        if self._known_codes is not None and code not in self._known_codes:
            raise ValueError(
                f"membership type {raw_value!r} maps to code {code!r} which is not in the "
                f"expected catalog codes (seed via task 4.2, then re-run)"
            )
        return code


# ── The pure transform (storage-agnostic; the heart of the backfill) ──────────────────
