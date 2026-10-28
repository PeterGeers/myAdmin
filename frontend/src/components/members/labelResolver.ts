/**
 * labelResolver — the ONE shared localized-label resolver for the members / public
 * surfaces (code-quality-fixes-2026-10-28 task 1).
 *
 * This collapses the 8 near-identical `resolveLabel` copies that had grown across the
 * members and public-application frontend into a single util. Diffing the copies
 * surfaced TWO genuine, test-pinned behavioral variants that must both be preserved:
 *
 *   1. **i18n-contract order** (`active → en → nl → key`) with a BLANK value at any tier
 *      treated as ABSENT (never render ""). This is the Option-(b) i18n contract (R3.5)
 *      that mirrors the SAM `LABEL_FALLBACK_ORDER = ("en", "nl")`
 *      (`sam/members/domain/attribute_catalog.py`) so the serializer and the frontend
 *      resolve a missing locale the SAME way. Used by `fieldForm.ts` and the public
 *      `applicationForm.model.ts`.
 *
 *   2. **checklist order** (`active → nl → en → key`) with a plain-string label passed
 *      THROUGH as-is (even when empty). This is the checklist/analytics convention
 *      lifted out of `MemberFieldPicker` (R4.1 / R2.4 / R4.5), used by the field
 *      checklist, the analytics overview/pivot helpers and the analytics page.
 *
 * Rather than silently pick one and change observable output, the per-site nuance is
 * preserved behind an `order` param (and the matching empty-string handling). Call sites
 * keep their exact prior behavior by choosing the order; the default is the i18n contract.
 *
 * @module components/members/labelResolver
 */

import type { LocalizedLabel } from '../../types/members';

/**
 * The locale-independent fallback tail.
 *
 * - `'en-first'` (default): active locale → `en` → `nl` → fallback, and a BLANK value at
 *   any tier (including a plain empty-string label) is treated as absent so the next tier
 *   fills it — the serializer-matching i18n contract (R3.5).
 * - `'nl-first'`: active locale → `nl` → `en` → fallback, and a NON-EMPTY plain-string
 *   label is returned verbatim — the checklist/analytics convention (R4.1). (An empty-string
 *   label is falsy and still resolves to the fallback via the shared `!label` guard, exactly
 *   as the original checklist copy did.)
 */
export type LabelFallbackOrder = 'en-first' | 'nl-first';

/**
 * Resolve a possibly-localized label to a plain string for the current language, else the
 * `fallback` (the canonical key) — NEVER blank in the default `'en-first'` order.
 *
 * @param label    a localized `{nl,en,…}` record, a plain string, or `undefined`
 * @param lang     the active language code (the `label` key to prefer)
 * @param fallback the canonical key rendered when no locale resolves (never blank)
 * @param order    the fallback tail + empty-string handling (see {@link LabelFallbackOrder});
 *                 defaults to `'en-first'` (the serializer-matching i18n contract)
 */
export function resolveLabel(
  label: string | LocalizedLabel | undefined,
  lang: string,
  fallback: string,
  order: LabelFallbackOrder = 'en-first',
): string {
  // A falsy label (undefined / empty string) resolves to the fallback in BOTH orders —
  // this guard is the empty-string handling both former copies shared.
  if (!label) return fallback;
  if (typeof label === 'string') {
    // `label` is a non-empty string here; `|| fallback` is a redundant safety net kept
    // to match the former en-first copy byte-for-byte.
    return order === 'en-first' ? label || fallback : label;
  }
  const active = label[lang];
  return order === 'en-first'
    ? active || label.en || label.nl || fallback
    : active || label.nl || label.en || fallback;
}
