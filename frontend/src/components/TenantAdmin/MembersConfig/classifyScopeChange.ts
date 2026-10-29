/**
 * classifyScopeChange — the AXIS-vs-VALUE gate for a scope-field save (spec 03b BU-6, task 6.2,
 * Req 4.3/4.5/4.6). Pure, no network, no React.
 *
 * ## Why this module exists
 *
 * A scope-backed field is a normal enum whose option VALUES are the access dimension (derived into
 * `config#scope` + the Flask `members.scope_dimensions` mirror — {@link deriveScopeDimensions}). Two
 * kinds of edit to that field are NOT the same thing (owner rule, design §"Scope changes split by
 * AXIS vs VALUE"):
 *
 *  - a **VALUE** change — adding/removing an option VALUE within the SAME set of scope-axis fields —
 *    is routine and AUTO-APPLIED: one more / one fewer selectable value, a `user_tenant` grant
 *    extends or shrinks, and how the admin handles the data of a removed value is THEIR concern
 *    (the platform blocks nothing, offers no "proven" reconciliation — Req 4.5);
 *  - a **SCOPE-AXIS** change — the SET of fields with `scope.enabled=true` changes (a different field
 *    becomes the scope field, a field is added to / removed from the scope combination, or scope is
 *    turned OFF entirely) — is a STRUCTURAL change to the tenant's access model, the same decision
 *    point as onboarding a tenant. It is NOT auto-applied: the save must REFUSE atomically (persist
 *    no `scope.enabled` change) and surface "create a project with your System Administrator"
 *    (Req 4.6).
 *
 * The gate PREVENTS an incoherent mixed write: an edit that BOTH flips the axis set AND changes
 * values is classified as an AXIS change (the structural change dominates), so the two planes never
 * diverge on a half-applied axis + value write.
 *
 * ## What it does
 *
 * Given the BASELINE overlay (the state last loaded from the server) and the WORKING overlay (after
 * the modals' in-memory edits) — the SAME two overlays {@link deriveFieldConfigChangeOps} diffs — it
 * compares the set of scope-AXIS field keys (fields whose `scope.enabled` is truthy) on each side:
 *
 *  - the axis key sets are EQUAL        → `'none'` (no scope-structural change) or `'value'`
 *                                          (same axes, but at least one axis field's option VALUES
 *                                          changed) — the caller auto-applies;
 *  - the axis key sets DIFFER (incl. an empty set on either side — scope turned on/off) → `'axis'`
 *                                          — the caller refuses atomically + shows the SysAdmin msg.
 *
 * The overlay carries scope-axis fields under BOTH `fields[bareKey]` (tenant-added variable fields)
 * and `fixed_overrides["{group}.{key}"]` (base/overridden fields); both are scanned. The key used
 * for the axis SET is the field's BARE key (the `fixed_overrides` dotted key is reduced to its bare
 * tail) so the two surfaces compare on the same identity the dimension derivation keys on.
 */
import type { MembersConfigValue } from '../../../types/membersConfig';

/** The classification of a scope-relevant edit between two overlays. */
export type ScopeChangeKind = 'none' | 'value' | 'axis';

type UnknownRecord = Record<string, unknown>;

function asRecord(value: unknown): UnknownRecord | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as UnknownRecord)
    : null;
}

/** The bare field key for an overlay entry key (strips a `fixed_overrides` dotted `{group}.{key}`). */
function bareKey(entryKey: string): string {
  const dot = entryKey.lastIndexOf('.');
  return dot >= 0 ? entryKey.slice(dot + 1) : entryKey;
}

/** True when a field overlay entry declares itself a scope AXIS (`scope.enabled` truthy). */
function entryIsScopeAxis(entry: unknown): boolean {
  const rec = asRecord(entry);
  if (!rec) return false;
  const scope = asRecord(rec.scope);
  return !!scope && scope.enabled === true;
}

/** Extract an overlay entry's option VALUES (the one vocabulary), order-preserving, de-duplicated. */
function entryOptionValues(entry: unknown): string[] {
  const rec = asRecord(entry);
  if (!rec) return [];
  const opts = rec.options;
  if (!Array.isArray(opts)) return [];
  const seen = new Set<string>();
  const values: string[] = [];
  for (const opt of opts) {
    let v: string | undefined;
    if (typeof opt === 'string') v = opt.trim() ? opt : undefined;
    else {
      const o = asRecord(opt);
      if (o && typeof o.value === 'string' && o.value.trim()) v = o.value;
    }
    if (v !== undefined && !seen.has(v)) {
      seen.add(v);
      values.push(v);
    }
  }
  return values;
}

/**
 * Walk an overlay's `fields` + `fixed_overrides` and collect, keyed by BARE field key, the option
 * VALUES of every scope-AXIS field. A non-axis field is omitted (so the returned map's KEY SET is
 * exactly the scope-axis set). Later entries do not override earlier ones for the same bare key —
 * a field cannot legitimately appear on both surfaces, and the first-wins read is deterministic.
 */
function scopeAxisValuesByKey(overlay: MembersConfigValue | null | undefined): Map<string, string[]> {
  const result = new Map<string, string[]>();
  const root = asRecord(overlay);
  if (!root) return result;

  for (const surfaceKey of ['fields', 'fixed_overrides'] as const) {
    const surface = asRecord(root[surfaceKey]);
    if (!surface) continue;
    for (const [entryKey, entry] of Object.entries(surface)) {
      if (!entryIsScopeAxis(entry)) continue;
      const key = bareKey(entryKey);
      if (!result.has(key)) result.set(key, entryOptionValues(entry));
    }
  }
  return result;
}

/** True when two string sets (as sorted arrays) are equal. */
function sameKeySet(a: Map<string, string[]>, b: Map<string, string[]>): boolean {
  if (a.size !== b.size) return false;
  for (const k of a.keys()) if (!b.has(k)) return false;
  return true;
}

/** True when the ordered-but-set-compared values of a dimension are equal between baseline/working. */
function sameValues(a: string[], b: string[]): boolean {
  if (a.length !== b.length) return false;
  const bs = new Set(b);
  return a.every((v) => bs.has(v));
}

/**
 * Classify the scope-relevant change between the baseline (loaded) overlay and the working (edited)
 * overlay (spec 03b BU-6, Req 4.3/4.5/4.6).
 *
 *  - `'axis'`  — the SET of scope-axis field keys differs (a field became / stopped being a scope
 *                axis, incl. scope turned fully off/on). The caller MUST refuse atomically and
 *                surface the SysAdmin-project message; it persists NO scope change. An edit that
 *                ALSO changes values is still `'axis'` — the structural change dominates, which is
 *                what prevents an incoherent mixed write.
 *  - `'value'` — the axis key set is UNCHANGED but at least one axis field's option VALUES changed.
 *                The caller auto-applies on both planes (grants extend/shrink).
 *  - `'none'`  — no scope-axis field changed its membership OR its values (a non-scope edit, or a
 *                save that did not touch scope). The caller skips the scope sync entirely.
 */
export function classifyScopeChange(
  baseline: MembersConfigValue | null | undefined,
  working: MembersConfigValue | null | undefined,
): ScopeChangeKind {
  const base = scopeAxisValuesByKey(baseline);
  const next = scopeAxisValuesByKey(working);

  // Axis set changed (a different field is the scope axis, a combination changed, or scope was
  // turned on/off) → structural access-model change: refuse atomically (Req 4.6). This dominates a
  // concurrent value change so the two planes never diverge on a half-applied mixed write.
  if (!sameKeySet(base, next)) return 'axis';

  // Same axis set — did any axis field's option VALUES change? That auto-applies (Req 4.5).
  for (const [key, values] of next) {
    if (!sameValues(base.get(key) ?? [], values)) return 'value';
  }

  return 'none';
}
