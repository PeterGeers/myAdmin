"""Per-field value normalization + the mapping-contract loader.

Part of the h-dcn backfill package (code-quality-fixes-2026-11-12 task 3).
"""

from __future__ import annotations

import datetime as _dt
import os
import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .source_layout import _base_header


def _clean(value: Any) -> str | None:
    """Normalize a raw cell: strip strings, treat empty / whitespace as absent (``None``)."""
    if value is None:
        return None
    if isinstance(value, str):
        s = value.strip()
        return s or None
    return value  # non-string (already-typed) values pass through


#: The AUTHORITATIVE source column that supplies the human ``member_number`` VERBATIM (the
#: "SAM Code" identity change, user-approved). The real h-dcn Google Sheet now carries a new
#: FIRST column ``SAM Code`` holding the formatted number for every data row — Members
#: ``M<5 digits>`` (``M06599``), Donateurs ``D00001``++, Contacts ``C00001``++. This column is
#: HUMAN-OWNED and STABLE (survives a sheet re-sort), so the importer READS it verbatim (trimmed)
#: and NEVER regenerates it — replacing the old fragile derivation (M+Lidnummer / D-skip /
#: C_+Achternaam). Matched on its BASE header, case-insensitive.
_SAM_CODE_COLUMN = "sam code"

#: The ``member_number`` FORMAT the SAM Code must satisfy (mirrors the tenant format authored in
#: ``members_config.json`` → ``membership.field_overlay.member_number.format.regex``): a Member
#: ``M#####`` / Donateur ``D#####`` / Contact ``C#####`` — all a single letter + exactly 5 digits.
#: A present SAM Code that does NOT match is a data gap (RowTransformError), never silently kept.
#: Kept in sync with the config regex; the importer validates the code it reads against it here
#: (``validate_fixed_fields`` does NOT enforce the tenant member_number format — that is Parameter
#: config resolved elsewhere — so the transform validates the authoritative code itself).
_MEMBER_NUMBER_FORMAT_RE = re.compile(r"^(M\d{5}|D\d{5}|C\d{5})$")


_ISO_DATE_PREFIX_RE = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})(?:[T ].*)?$")
#: Dutch ``d-m-yyyy`` / ``dd-mm-yyyy`` (DAY-first), with an OPTIONAL trailing ` hh:mm[:ss]` time
#: part. Groups: day, month, year. Verified against the live h-dcn sheet: ``Datum ondertekening``
#: (``13-4-2023``, no time) and ``Tijdstempel`` (``4-5-2026 10:59:37`` — SOME carry a time).
_DUTCH_DATE_RE = re.compile(
    r"^(\d{1,2})-(\d{1,2})-(\d{4})(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?$"
)
_YEAR_RE = re.compile(r"^\s*(\d{4})\s*$")


def _skip_label(personal: Mapping[str, Any], overlay: Mapping[str, Any]) -> str:
    """A best-effort human identifier for a SKIPPED row (for the report).

    Prefers the name parts already mapped (last/first), else any overlay ``naam``-like value,
    else ``<empty>``. Purely cosmetic — used only in the skipped-rows report.
    """
    last = str(personal.get("last_name", "")).strip()
    first = str(personal.get("first_name", "")).strip()
    name = " ".join(p for p in (first, last) if p)
    return name or "<empty>"


def _valid_ymd(year: int, month: int, day: int) -> str | None:
    """Return a normalized ``YYYY-MM-DD`` string for a valid calendar date, else None.

    Uses :class:`datetime.date` so an impossible calendar day (e.g. ``31-2``, ``29-2`` in a
    non-leap year) is rejected as well as a plainly out-of-range month/day. Returning None keeps
    the caller's contract: an optional date field stays unset rather than raising or fabricating.
    """
    try:
        return _dt.date(year, month, day).isoformat()
    except ValueError:
        return None


def _parse_source_date(raw: Any) -> str | None:
    """Normalize a source date/datetime string to a bare ``YYYY-MM-DD``, or None.

    ONE code path used by BOTH ``joined_date`` and ``birth_date`` (and the overlay date fields)
    so their date handling can never drift. Accepts two shapes seen on the live h-dcn sheet, in
    ADDITION to the ISO form the OLD fixture uses:

    - **Dutch ``d-m-yyyy`` / ``dd-mm-yyyy``** — DAY-first (user-confirmed): ``4-5-2026`` is
      4 May 2026 (day=4, month=5). An OPTIONAL trailing ` hh:mm` / ` hh:mm:ss` time part
      (``Tijdstempel`` carries some) is ignored — only the date is kept. Verified real samples:
      ``13-4-2023`` → ``2023-04-13``, ``22-11-2025`` → ``2025-11-22``.
    - **ISO ``YYYY-MM-DD``** (optionally followed by ``T…`` / ` …` time, as in the fixture's
      ``2010-01-01T00:00:00.000Z``) → the leading calendar date.

    Both are validated as real calendar dates (month 1-12, day 1-31, no impossible days); an
    out-of-range or unparseable value returns None — the optional field stays unset, never
    raises, never fabricates a date.
    """
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    # ISO first (YYYY-MM-DD[...]): the four-digit YEAR leads, so it is unambiguous vs the Dutch
    # day-first form (which leads with a 1-2 digit day).
    m = _ISO_DATE_PREFIX_RE.match(s)
    if m:
        return _valid_ymd(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    # Dutch d-m-yyyy (day-first), optional trailing time.
    m = _DUTCH_DATE_RE.match(s)
    if m:
        return _valid_ymd(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    return None


#: Backwards-compatible alias. Historically the transform reduced an ISO datetime to its date
#: part via ``_iso_date_part``; that role is now the broader :func:`_parse_source_date` (Dutch
#: day-first ``d-m-yyyy`` AND ISO). The alias keeps any existing reference working and reads
#: correctly at every call site (both fixed and overlay date fields route through it).
_iso_date_part = _parse_source_date


def _year_to_iso(raw: Any) -> str | None:
    """Map a bare year (e.g. ``"2023"``) to ``<year>-01-01``, or None if not a 4-digit year."""
    if raw is None:
        return None
    m = _YEAR_RE.match(str(raw))
    return f"{m.group(1)}-01-01" if m else None


def _row_has_meaningful_data(raw_row: Mapping[str, Any]) -> bool:
    """True if a raw source row carries ANY meaningful (populated) cell (R7.2 empty-row test).

    Used to detect a truly-EMPTY row that must be SKIPPED (not counted as an error, not written).
    A cell is "meaningful" when, after normalization, it still holds a value:
    - the blank-NAMED column (empty/whitespace header) is IGNORED (it is a Google-Sheet export
      artifact, dropped by the transform anyway, R1.5);
    - an ``E-mailadres`` cell that is a NO-VALID-EMAIL placeholder (``_NO_VALID_EMAIL_INDICATORS``,
      e.g. "GEEN GELDIG EMAILADRES") normalizes to empty and so does NOT count as meaningful —
      a placeholder-only row is therefore empty and skipped silently;
    - every other cell counts as meaningful when it is non-blank after a plain strip.

    The header is matched on its BASE (position-tracking ``#<colindex>`` stripped) so a
    duplicate column is judged like its bare sibling.
    """
    for column, value in raw_row.items():
        base = _base_header((column or "").strip())
        if base == "":
            continue  # blank-named column is a dropped artifact — never "meaningful"
        cleaned = _clean(value)
        if cleaned is None:
            continue
        # An email placeholder normalizes to empty — it does not make the row meaningful.
        if base.lower() == "e-mailadres" and _normalize_email(cleaned) is None:
            continue
        return True
    return False


def _read_sam_code(raw_row: Mapping[str, Any]) -> str | None:
    """Read the authoritative ``SAM Code`` cell VERBATIM (trimmed), or None when blank/absent.

    The SAM Code identity change (user-approved): ``member_number`` is now READ from the sheet's
    ``SAM Code`` column (matched on its BASE header ``sam code``, case-insensitive — it is the
    first column) rather than DERIVED from ``Lidnummer``/``Achternaam``. A present code is used
    verbatim (trimmed); the caller validates it against :data:`_MEMBER_NUMBER_FORMAT_RE`. A blank
    / absent cell yields ``None`` (the caller decides: an empty row is skipped, a meaningful row
    with a blank code is a data-gap error). A position-tracked duplicate is matched on its base.
    """
    for column, value in raw_row.items():
        if _base_header((column or "").strip()).lower() == _SAM_CODE_COLUMN:
            cleaned = _clean(value)
            if cleaned is not None:
                return str(cleaned).strip()
    return None


# ── Per-rule value conversions (the mapping-contract `rule` strategies, R0.2/R0.3/D0b) ─

#: Gender normalization — PORTED (s5m R8.1) from h-dcn's proven importer
#: (``import_members_sheets.py`` v2.0 ``gender_mapping``), RETARGETED (R8.2) onto THIS tenant's
#: ``gender`` enum authored in ``members_config.json`` (``M``/``V``/``X``/``N`` — the four
#: choices on ``personal.gender``). Dutch ``Man``/``Vrouw`` (and the bare ``m``/``v``, plus the
#: English ``male``/``female``) → ``M``/``V``; ``anders``/``other`` → ``X`` ("Anders"); an
#: explicit "prefer not to say" → ``N``. Already-canonical ``M``/``V``/``X``/``N`` pass through
#: (matched case-folded). An UNRECOGNIZED value is kept VERBATIM (never silently forced to a
#: wrong code) so the fixed-field validation against the tenant ``gender`` choices surfaces it.
_GENDER_MAP: Mapping[str, str] = {
    # → M
    "man": "M",
    "m": "M",
    "male": "M",
    "manlijk": "M",
    "mannelijk": "M",
    "heer": "M",
    "dhr": "M",
    # → V
    "vrouw": "V",
    "v": "V",
    "f": "V",
    "female": "V",
    "vrouwelijk": "V",
    "mevrouw": "V",
    "mevr": "V",
    # → X ("Anders" / other)
    "x": "X",
    "anders": "X",
    "other": "X",
    "divers": "X",
    # → N ("Wil niet zeggen" / prefer not to say)
    "n": "N",
    "onbekend": "N",
    "unknown": "N",
    "wil niet zeggen": "N",
    "prefer not to say": "N",
    "zegt liever niet": "N",
}


def _normalize_gender(raw: Any) -> str | None:
    """Normalize a raw gender to the tenant enum (``M``/``V``/``X``/``N``), else keep verbatim."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    return _GENDER_MAP.get(s.lower(), s)


#: Magazine (``Clubblad``) → the ``magazine_pref`` enum ``Geen``/``Papier``/``Digitaal`` (R0.2).
#: PORTED (s5m R8.1) from h-dcn's ``Clubblad`` knowledge in ``import_members_sheets.py`` v2.0,
#: RETARGETED (R8.2) onto THIS tenant's ``magazine_pref`` choices in ``members_config.json``
#: (``Geen``/``Papier``/``Digitaal``). h-dcn's OLD Clubblad→membership-status rule
#: (Papier→"Sponsor" / Digitaal→"Club") is NOT copied — those were h-dcn Dutch STATUS strings
#: on the old table and are not a valid SAM ``membership_type``/``status`` in this catalog (D8);
#: only the PREFERENCE variant knowledge (which spellings mean paper vs digital vs none) is
#: reused. ``Papier``/``Digitaal`` map as-is (case/space-folded); anything meaning "none" (or
#: empty, or unrecognized) falls back to ``Geen`` (the catch-all fallback, R0.2).
_MAGAZINE_MAP: Mapping[str, str] = {
    # → Papier
    "papier": "Papier",
    "paper": "Papier",
    "print": "Papier",
    "gedrukt": "Papier",
    "op papier": "Papier",
    "papieren": "Papier",
    # → Digitaal
    "digitaal": "Digitaal",
    "digital": "Digitaal",
    "digitale": "Digitaal",
    "pdf": "Digitaal",
    "email": "Digitaal",
    "e-mail": "Digitaal",
    "online": "Digitaal",
    # → Geen (none / not wanted). Empty + unrecognized ALSO fall back to Geen (see below).
    "geen": "Geen",
    "none": "Geen",
    "nee": "Geen",
    "no": "Geen",
    "niet": "Geen",
    "n.v.t.": "Geen",
    "nvt": "Geen",
}


def _normalize_magazine(raw: Any) -> str:
    """Map a raw ``Clubblad`` value → ``magazine_pref`` enum; empty/unrecognized → ``Geen``."""
    if raw is None:
        return "Geen"
    s = str(raw).strip()
    if not s:
        return "Geen"
    return _MAGAZINE_MAP.get(s.lower(), "Geen")


#: Email "NO-VALID-EMAIL" indicators — PORTED (s5m R8.1) from h-dcn's importer: sheet cells that
#: are placeholders meaning "this member has no real email" rather than an actual address (the
#: sheet was hand-maintained, and operators typed these to mark a missing/absent address). Such
#: a value must be treated as EMPTY (the field left unset), NOT stored as if it were an address —
#: otherwise ``no@email.com`` etc. would look like a deliverable address. Matched case-folded on
#: the trimmed cell; a genuine address is never in this set. Kept as DATA (extensible), not code.
_NO_VALID_EMAIL_INDICATORS: frozenset[str] = frozenset(
    {
        "geen",
        "geen email",
        "geen e-mail",
        "geen emailadres",
        "geen e-mailadres",
        "geen mail",
        "geen geldig emailadres",
        "geen geldig e-mailadres",
        "onbekend",
        "n.v.t.",
        "nvt",
        "n/a",
        "na",
        "none",
        "no email",
        "no e-mail",
        "noemail",
        "no@email.com",
        "geen@email.com",
        "geen@geen.nl",
        "-",
        "--",
        ".",
        "x",
        "xxx",
    }
)


def _normalize_email(raw: Any) -> str | None:
    """Normalize a raw email cell; a NO-VALID-EMAIL placeholder (R8.1) is treated as empty.

    Returns the trimmed address, or ``None`` when the cell is blank OR is one of the
    :data:`_NO_VALID_EMAIL_INDICATORS` placeholders (so a fake "geen email" marker never lands
    on ``personal.email`` as if it were a real address). A genuine address passes through
    verbatim (trimmed) — this does NOT validate deliverability, only strips known placeholders.
    """
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    if s.lower() in _NO_VALID_EMAIL_INDICATORS:
        return None
    return s


# ── Column-shift detection (data-quality safeguard, ported R8.1) ──────────────────────


#: One detected COLUMN-SHIFT signal on a source row (R8.1) — a value that landed in a column it
#: does not belong in, indicating the row's cells are shifted (a hand-maintained-sheet hazard).
#: PORTED from h-dcn's importer, which detected a YEAR value sitting in ``Geslacht`` (gender) and
#: a GENDER value sitting in ``Regio`` (region). Purely a WARNING surfaced in the fidelity report
#: (like :class:`DuplicateHeaderConflict`) — it never blocks a row nor rewrites a value; the
#: operator inspects the flagged column and fixes the source. Carries the offending column (base
#: header), the suspicious value, and a short human reason.
@dataclass(frozen=True)
class ColumnShiftWarning:
    column: str
    value: str
    reason: str


#: A 4-digit year sitting where a gender is expected (``Geslacht``) — the classic shift signal.
_LOOKS_LIKE_YEAR_RE = re.compile(r"^(19|20)\d{2}$")
#: The known gender tokens (lower-cased) — a gender token sitting in ``Regio`` signals a shift.
_GENDER_TOKENS: frozenset[str] = frozenset(
    {"m", "v", "man", "vrouw", "male", "female", "x"}
)


def detect_column_shift(raw_row: Mapping[str, Any]) -> list[ColumnShiftWarning]:
    """Detect column-shift signals on a source row (data-quality safeguard, R8.1 port).

    Returns a list of :class:`ColumnShiftWarning` (empty when the row looks well-aligned). Two
    signals ported from h-dcn's importer, matched on the BASE header (so a position-tracked
    duplicate is checked too):
    - a YEAR value (``19xx``/``20xx``) in ``Geslacht`` — a birth year shifted into the gender
      column;
    - a GENDER token (``M``/``V``/``Man``/``Vrouw``/…) in ``Regio`` — a gender shifted into the
      region column.
    It only READS the row (pure) — it neither mutates nor drops anything.
    """
    warnings: list[ColumnShiftWarning] = []
    for column, value in raw_row.items():
        base = _base_header((column or "").strip()).lower()
        s = "" if value is None else str(value).strip()
        if not s:
            continue
        if base == "geslacht" and _LOOKS_LIKE_YEAR_RE.match(s):
            warnings.append(
                ColumnShiftWarning(
                    column=(column or "").strip(),
                    value=s,
                    reason="a year-like value in the gender column (Geslacht) suggests the "
                    "row's columns are shifted",
                )
            )
        elif base == "regio" and s.lower() in _GENDER_TOKENS:
            warnings.append(
                ColumnShiftWarning(
                    column=(column or "").strip(),
                    value=s,
                    reason="a gender-like value in the region column (Regio) suggests the "
                    "row's columns are shifted",
                )
            )
    return warnings


#: A simple IBAN test for the ``iban_or_payment`` conditional split (R0.3, per the CSV note):
#: a value that (space-stripped) is >= 15 chars and starts with two letters is treated as an
#: IBAN. This is deliberately loose (a data-quality heuristic, not a mod-97 validation) — the
#: point is only to route a bank number to ``iban`` and free text to ``payment_method``.
_IBAN_MIN_LEN = 15
_IBAN_HEAD_RE = re.compile(r"^[A-Za-z]{2}")


def _looks_like_iban(value: str) -> bool:
    compact = re.sub(r"\s+", "", value)
    return len(compact) >= _IBAN_MIN_LEN and bool(_IBAN_HEAD_RE.match(compact))


def _split_iban_or_payment(raw: Any) -> tuple[str | None, str | None]:
    """Split one ``Bankrekeningnummer`` value into (iban, payment_method) (R0.3 conditional split).

    - a value passing :func:`_looks_like_iban` → ``iban=value`` (compacted) + ``payment_method``
      = ``"incasso"`` (the common case is thus pre-populated for most members);
    - a non-IBAN, non-empty value → ``payment_method`` = that raw text, ``iban`` left unset;
    - an empty value → both unset (``None``, ``None``).
    """
    if raw is None:
        return (None, None)
    s = str(raw).strip()
    if not s:
        return (None, None)
    if _looks_like_iban(s):
        return (re.sub(r"\s+", "", s), "incasso")
    return (None, s)


# ── The authored mapping contract (loaded once, cached) ───────────────────────────────

#: The parsed default mapping contract, lazily loaded + cached (the transform's default when a
#: caller passes no explicit ``contract``). Loading is deferred to first use because the loader
#: (``scripts/onboarding/members/h-dcn/members_mapping_loader.py``) is NOT on the normal import
#: path — importing ``hdcn_backfill`` in the SAM Lambda runtime must never require the onboarding
#: scripts dir.
_DEFAULT_CONTRACT_CACHE: Any = None


def _load_default_contract() -> Any:
    """Load + cache the authored default :class:`MappingContract` (spec D0), lazily by path.

    The loader + CSV live under ``scripts/onboarding/members/h-dcn/`` (not a Python package), so
    this imports the module BY PATH (mirroring how the runner loads ``members_config_loader``) and
    caches the result. ``map_hdcn_row`` calls this only when its caller supplies no explicit ``contract`` —
    the runner (task 6) will pass the already-loaded contract, avoiding the re-load.
    """
    global _DEFAULT_CONTRACT_CACHE
    if _DEFAULT_CONTRACT_CACHE is None:
        import importlib.util

        _hdcn_dir = os.path.join(
            os.path.dirname(
                os.path.dirname(
                    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                )
            ),
            "scripts",
            "onboarding",
            "members",
            "h-dcn",
        )
        _loader_path = os.path.join(_hdcn_dir, "members_mapping_loader.py")
        # The mapping loader imports its sibling ``members_config_loader`` as a top-level name for
        # the drift guard, so the onboarding scripts dir must be importable while we load it.
        if _hdcn_dir not in sys.path:
            sys.path.insert(0, _hdcn_dir)
        # Reuse an already-imported loader if present (e.g. the tests import it directly). Else
        # import it BY PATH and REGISTER it in ``sys.modules`` BEFORE ``exec_module`` — ``@dataclass``
        # resolves its module via ``sys.modules[cls.__module__]`` during class creation, so an
        # unregistered module makes that lookup return ``None`` (an ``AttributeError`` on load).
        _module = sys.modules.get("members_mapping_loader")
        if _module is None:
            _spec = importlib.util.spec_from_file_location(
                "members_mapping_loader", _loader_path
            )
            _module = importlib.util.module_from_spec(_spec)
            sys.modules["members_mapping_loader"] = _module
            _spec.loader.exec_module(_module)  # type: ignore[union-attr]
        _DEFAULT_CONTRACT_CACHE = _module.load_mapping_contract()
    return _DEFAULT_CONTRACT_CACHE


#: One reported duplicate-header conflict (R1.6): two DIFFERENT non-empty values shared a base
#: header, the first-in-column-order was KEPT, and this is the losing column (its INDEXED name,
#: e.g. ``E-mailadres#34``) + the base header + the kept vs dropped values, so the fidelity
#: report can show the operator exactly which column lost and reconcile the source.
@dataclass(frozen=True)
class DuplicateHeaderConflict:
    base_header: str
    losing_column: str
    kept_value: str
    dropped_value: str
