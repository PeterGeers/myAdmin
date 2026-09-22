/**
 * scopeFuzzyFilter (s5d task 6.3)
 *
 * A diacritic/spacing-tolerant TYPEAHEAD filter over a dimension's canonical
 * value list — the FIRST link of the design's chain:
 *
 *     fuzzy FINDS → canonical STORES → exact ENFORCES
 *
 * The filter is an AUTHORING CONVENIENCE ONLY (R5.4): it narrows WHICH canonical
 * values are shown in the picker, but the values it returns are the ORIGINAL,
 * UNCHANGED canonical values (R5.3). Selecting a filtered result therefore always
 * stores the canonical value — fuzzy never alters what is PUT.
 *
 * The fold used for MATCHING mirrors the backend `scope_canon`
 * (`sam/members/domain/scope_canon.py` / `backend/src/services/scope_canon.py`):
 *   1. NFKD normalize (decompose base letter + combining diacritic),
 *   2. strip combining marks (diacritic-fold: `é`→`e`, `â`→`a`, `ý`→`y`),
 *   3. lowercase (locale-independent),
 *   4. fold every run of space / `-` / `/` (and surrounding whitespace) to ONE space,
 *   5. trim.
 * Both the query and each candidate value are folded, then matched by SUBSTRING —
 * enough for a diacritic/spacing-tolerant typeahead (the design asks for fold-then-
 * substring, not full edit-distance fuzzy). So "noord holl" matches "Noord-Holland",
 * "friesland" matches "Friesland", and a diacritic query matches its unaccented
 * value and vice-versa.
 *
 * Pure and deterministic: same input → same output, no I/O.
 *
 * _Requirements: R5.3, R5.4_
 */

/** A run of any separator char (space, `-`, `/`) or surrounding whitespace. */
const SEPARATOR_RUN = /[\s\-/]+/g;

/**
 * Fold a scope value/query to the canonical MATCH form, mirroring the backend
 * `scope_canon`: NFKD → strip diacritics → lowercase → fold separators → trim.
 *
 * Used ONLY for comparison — never for what is stored/returned.
 */
export function scopeCanonFold(value: string): string {
  return value
    .normalize('NFKD')
    // Strip combining marks (Unicode "Mark, Nonspacing" — the diacritic-fold).
    .replace(/\p{Mn}+/gu, '')
    .toLowerCase()
    .replace(SEPARATOR_RUN, ' ')
    .trim();
}

/**
 * Diacritic/spacing-tolerant typeahead filter over a canonical value list.
 *
 * Returns the subset of `values` whose folded form contains the folded query,
 * in the ORIGINAL order and with the ORIGINAL (canonical) spelling. An empty /
 * whitespace-only query returns ALL values unchanged. No match returns `[]`.
 *
 * The returned strings are the untouched canonical values — the fold is applied
 * only to the match, so selecting a result stores the canonical value (R5.3).
 */
export function fuzzyFilterValues(values: string[], query: string): string[] {
  const foldedQuery = scopeCanonFold(query);
  if (!foldedQuery) return values;
  return values.filter((value) => scopeCanonFold(value).includes(foldedQuery));
}
