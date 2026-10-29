/**
 * Derive a config#fields CHANGE-OP list by IDENTITY from a working-overlay diff (spec 03 —
 * config-fields-foolproof-crud, Phase 5 / task 5.1; steering 39).
 *
 * ## Why this module exists
 *
 * Phase 5 switches the MembersConfig configurator + the Application Form Builder off the
 * whole-object `field_overlay` write (the source of the repeated catalog-truncation bug — see
 * `.kiro/specs/Members/root-cause-analysis.md`) and onto the SERVER-OWNED Change-Op write
 * (`PUT /members/config/fields` with an `ops` list — backend task 2.7). The client now sends INTENT
 * BY IDENTITY and lets the server decide storage placement; it NEVER sends a whole catalog and
 * NEVER reconstructs a `{group}.{key}` storage key (steering 39 — the physical two-map / dotted-key
 * layout stays inside the repository).
 *
 * ## What it does (pure, no network, no React)
 *
 * Given the BASELINE overlay (the state last loaded from the server) and the WORKING overlay (after
 * the modals' in-memory edits), it DIFFS the two and emits one Change-Op per changed identity:
 *
 *  - a group added/changed  → `set_group`  (identity = the bare group key; attrs ⊆ {label, order});
 *  - a group removed        → `delete_group`;
 *  - a field added/changed under `fields`          → `set_field` (+ `set_field_application` for the
 *                                                     four form attrs), identity = the BARE key;
 *  - a base-field override added/changed under `fixed_overrides` → `set_field` (+
 *                                                     `set_field_application`), identity = the BARE
 *                                                     key (the dotted `{group}.{key}` storage key is
 *                                                     stripped to its bare key — the SERVER re-places it);
 *  - a `fields` field removed       → `delete_field`;
 *  - a `fixed_overrides` entry removed → `reset_field` (revert the base override).
 *
 * The DEFINITION attrs and the four APPLICATION attrs are split into DISJOINT ops (`set_field` vs
 * `set_field_application`) to match the backend's disjoint op surfaces (design C1). The flat working
 * `label_en` / `label_nl` inputs are FOLDED into the `label: { nl, en }` object the Change-Op
 * surface accepts (the server no longer folds a per-locale pair).
 *
 * This module is the REPLACEMENT for the whole-object server write (the three-slice `field_overlay`
 * body PUT WHOLE, now retired — spec 03 task 5.2). The `overlayModel` write helpers keep running as
 * the components' IN-MEMORY WORKING BUFFER (the diff baseline this module reads); only the
 * whole-object server-write assembly (`writeFieldConfig` / the `field_overlay` branch of
 * `saveMembersParameter`) was removed. `resolveWriteTarget`'s dotted `{group}.{key}` key stays as a
 * buffer-placement detail — it NEVER crosses the wire, because `bareFieldKey` strips it to the bare
 * identity here and the server owns storage placement (steering 39).
 */
import type { FieldConfigChangeOp } from '../../../services/members/membersConfigApi';
import type { MembersConfigValue } from '../../../types/membersConfig';

/** The four per-field APPLICATION attributes — the DISJOINT `set_field_application` surface. */
const APPLICATION_ATTRS = [
  'application_visible',
  'application_required',
  'application_choices',
  'format',
] as const;

/**
 * The BOOLEAN attributes whose OFF state must be emitted as an EXPLICIT `false`, never dropped as
 * `undefined` (spec 03b BU-5, Req 2 — the toggle-persistence root cause). These are the field
 * attributes an admin turns ON/OFF with a switch; a true→false transition has to reach the backend
 * as a deliberate `false` so a reload shows OFF. Every OTHER attr keeps absent-means-unchanged.
 *
 * Split by surface so each emitter only ever considers its OWN booleans:
 *  - `required`/`visible` live on the DEFINITION surface (`set_field`);
 *  - `application_visible`/`application_required` live on the APPLICATION surface
 *    (`set_field_application`).
 *
 * Why this is the ROOT fix (Req 2.4): the diff previously treated `undefined` as BOTH "unchanged"
 * and "turned off", so an OFF emitted no value and the write silently reverted on reload. By
 * diffing each boolean against the LOADED (baseline) state here — if it was truthy in the baseline
 * and is no longer truthy in the working entry, emit an explicit `false` — NO boolean attribute can
 * drop an OFF, now or for a future boolean (so 03a's `required` fix + 03b's
 * `application_visible`/`application_required` fix cannot recur a fourth time).
 */
const DEFINITION_BOOLEAN_ATTRS = ['required', 'visible'] as const;
const APPLICATION_BOOLEAN_ATTRS = ['application_visible', 'application_required'] as const;

/**
 * The field DEFINITION attributes the `set_field` op accepts (server-owned placement).
 *
 * Single-vocabulary (spec 03a / C1): the enum vocabulary is authored and emitted under the ONE
 * canonical `options` key — `'choices'` is dropped from this surface so the write NEVER emits
 * `choices`. The editor authors `options` on the working overlay (MembersFieldModal) and the
 * read-assembly seam serves the single `options` back.
 */
const DEFINITION_ATTRS = [
  'type',
  'label',
  'order',
  'required',
  'visible',
  'options',
  'scope',
  'functional_group',
] as const;

/** The group attributes the `set_group` op accepts. */
const GROUP_ATTRS = ['label', 'order'] as const;

type Dict = Record<string, MembersConfigValue>;

function isRecord(v: unknown): v is Dict {
  return !!v && typeof v === 'object' && !Array.isArray(v);
}

function asOverlay(overlay: MembersConfigValue | undefined): Dict {
  return isRecord(overlay) ? overlay : {};
}

function mapSlice(overlay: MembersConfigValue | undefined, slice: string): Dict {
  const m = asOverlay(overlay)[slice];
  return isRecord(m) ? m : {};
}

function groupList(overlay: MembersConfigValue | undefined): Dict[] {
  const list = asOverlay(overlay).functional_groups;
  if (!Array.isArray(list)) return [];
  return list.filter(isRecord) as Dict[];
}

/**
 * Strip a storage key down to its BARE field identity. A base-field override lives under
 * `fixed_overrides` keyed by the dotted `{group}.{key}`; the Change-Op surface is identity-keyed
 * by the BARE key and the server re-derives the storage placement (steering 39 — the client never
 * reconstructs `{group}.{key}`). A `fields` entry is already bare, so this is a no-op there.
 */
export function bareFieldKey(storageKey: string): string {
  const dot = storageKey.lastIndexOf('.');
  return dot >= 0 ? storageKey.slice(dot + 1) : storageKey;
}

/**
 * Fold the flat per-locale `label_en` / `label_nl` inputs into the `label: { nl?, en? }` object the
 * Change-Op definition/group surface accepts. A pre-folded `label` object on the entry wins (a
 * reloaded entry already carries it); the flat inputs are the fresh-edit shape. Returns `undefined`
 * when neither is present (so the attr is simply not written).
 */
function foldLabel(entry: Dict): MembersConfigValue | undefined {
  const folded = isRecord(entry.label) ? { ...(entry.label as Dict) } : {};
  if (typeof entry.label_en === 'string') folded.en = entry.label_en;
  if (typeof entry.label_nl === 'string') folded.nl = entry.label_nl;
  return Object.keys(folded).length > 0 ? (folded as MembersConfigValue) : undefined;
}

/**
 * True when a field entry is SCOPE-BACKED: it carries a `scope` attr whose `enabled` is truthy.
 * A scope-backed field's vocabulary lives in the SEPARATE `config#scope` dimension (authored via
 * `PUT /members/config/config#scope`), NOT on the `config#fields` row — so its `config#fields`
 * `set_field` payload must carry NO inline `options` (the backend W2 guard rejects it). The editor
 * seeds `options` on read from the scope dimension (the C4 read seam) purely for display; re-sending
 * it on save is what trips W2. A field with no `scope`, or `scope.enabled` falsy, is NOT scope-backed
 * and keeps emitting `options` as a normal enum.
 */
function isScopeBacked(entry: Dict): boolean {
  const scope = entry.scope;
  return isRecord(scope) && !!(scope as Dict).enabled;
}

/**
 * Emit the explicit OFF (`false`) for any BOOLEAN attribute that was TRUTHY in the baseline and is
 * no longer truthy in the working entry (spec 03b BU-5 / Req 2 — the toggle root cause). Diffing
 * against the LOADED (`before`) state is what distinguishes "unchanged" (absent in both → nothing
 * written) from "turned OFF" (truthy before → `false` now), so an OFF is never dropped as a silent
 * `undefined`. A still-truthy / still-absent boolean is left to the ordinary attr copy below.
 *
 * `before` is the field's baseline entry (the state last loaded from the server), or `undefined`
 * for a genuinely NEW field (nothing was ON to turn OFF, so no explicit `false` is forced).
 */
function emitExplicitBooleanOff(
  attrs: Dict,
  entry: Dict,
  before: Dict | undefined,
  booleanAttrs: readonly string[],
): void {
  if (!before) return;
  for (const attr of booleanAttrs) {
    const wasOn = before[attr] === true;
    const nowOn = entry[attr] === true;
    if (wasOn && !nowOn) attrs[attr] = false;
  }
}

/**
 * Pick the DEFINITION attrs off a field entry, folding `label_*` → `label`. `before` is the
 * baseline entry so a boolean DEFINITION attr (`required`/`visible`) turned OFF emits an explicit
 * `false` instead of silently vanishing (Req 2.4).
 */
function definitionAttrs(entry: Dict, before?: Dict): Dict {
  const attrs: Dict = {};
  const label = foldLabel(entry);
  if (label !== undefined) attrs.label = label;
  // A scope-backed field does NOT own its vocabulary — the `config#scope` dimension does. Omit the
  // display-seeded `options` so the save can't trip the backend W2 guard (scope + options). The
  // `scope` attr itself is still emitted; only `options` is suppressed for a scope-backed field.
  const scopeBacked = isScopeBacked(entry);
  for (const attr of DEFINITION_ATTRS) {
    if (attr === 'label') continue;
    if (attr === 'options' && scopeBacked) continue;
    if (entry[attr] !== undefined) attrs[attr] = entry[attr] as MembersConfigValue;
  }
  // A true→false transition on a boolean definition attr must reach the server as an explicit false.
  emitExplicitBooleanOff(attrs, entry, before, DEFINITION_BOOLEAN_ATTRS);
  return attrs;
}

/**
 * Pick the four APPLICATION attrs off a field entry. `before` is the baseline entry so a boolean
 * APPLICATION attr (`application_visible`/`application_required`) turned OFF emits an explicit
 * `false` rather than a dropped `undefined` (Req 2.1/2.4 — the toggle-persistence root cause).
 */
function applicationAttrs(entry: Dict, before?: Dict): Dict {
  const attrs: Dict = {};
  for (const attr of APPLICATION_ATTRS) {
    if (entry[attr] !== undefined) attrs[attr] = entry[attr] as MembersConfigValue;
  }
  // A true→false transition on a boolean application attr must reach the server as an explicit false.
  emitExplicitBooleanOff(attrs, entry, before, APPLICATION_BOOLEAN_ATTRS);
  return attrs;
}

/** Pick the group attrs off a group entry, folding `label_*` → `label`. */
function groupAttrs(entry: Dict): Dict {
  const attrs: Dict = {};
  const label = foldLabel(entry);
  if (label !== undefined) attrs.label = label;
  for (const attr of GROUP_ATTRS) {
    if (attr === 'label') continue;
    if (entry[attr] !== undefined) attrs[attr] = entry[attr] as MembersConfigValue;
  }
  return attrs;
}

/** Stable JSON-equality for a diff (order-insensitive would need a sort; stored shapes are stable). */
function changed(a: MembersConfigValue | undefined, b: MembersConfigValue | undefined): boolean {
  return JSON.stringify(a ?? null) !== JSON.stringify(b ?? null);
}

/** True when `attrs` carries at least one key (an empty attrs op is never emitted). */
function nonEmpty(attrs: Dict): boolean {
  return Object.keys(attrs).length > 0;
}

/**
 * Derive the Change-Op list from (baseline overlay, working overlay). Each op is keyed by a BARE
 * domain identity (field `key` / group `group`); the server owns storage placement. The order is
 * deterministic: group ops first (so a field's target group exists), then field ops.
 *
 * `baseline` is the overlay as last loaded from the server; `working` is the edited overlay. When
 * they are identical the result is an empty list (nothing to write).
 *
 * @param baseline the server-loaded overlay (`{ fields, fixed_overrides, functional_groups }`).
 * @param working  the edited overlay in the same shape.
 */
export function deriveFieldConfigChangeOps(
  baseline: MembersConfigValue | undefined,
  working: MembersConfigValue | undefined,
): FieldConfigChangeOp[] {
  const ops: FieldConfigChangeOp[] = [];

  // ── Groups (functional_groups LIST, keyed by `key`) ──────────────────────────────────
  const baseGroups = new Map(groupList(baseline).map((g) => [String(g.key), g]));
  const workGroups = new Map(groupList(working).map((g) => [String(g.key), g]));

  for (const [key, entry] of workGroups) {
    if (!key) continue;
    const before = baseGroups.get(key);
    const isNew = !before;
    if (isNew || changed(groupAttrs(before!) as MembersConfigValue, groupAttrs(entry) as MembersConfigValue)) {
      const attrs = groupAttrs(entry);
      if (nonEmpty(attrs)) {
        ops.push({ op: 'set_group', group: key, attrs });
      } else if (isNew) {
        // A genuinely NEW group with no label/order would otherwise derive empty attrs and be
        // silently dropped (the Change-Op surface needs at least one attr). Materialize it with an
        // empty label object so the identity is created server-side rather than lost — the admin
        // can fill the label/order later. (An EXISTING group reverting to no attrs is a no-op.)
        ops.push({ op: 'set_group', group: key, attrs: { label: {} } });
      }
    }
  }
  for (const key of baseGroups.keys()) {
    if (key && !workGroups.has(key)) ops.push({ op: 'delete_group', group: key });
  }

  // ── Fields across BOTH storage maps, diffed by BARE identity ─────────────────────────
  // A field may live under `fields` (variable, bare key) or `fixed_overrides` (base override,
  // dotted `{group}.{key}`). We diff per storage map but EMIT by bare identity — the server
  // re-derives the storage placement, so the client never sends a dotted key (steering 39).
  const emitFieldOps = (
    baseSlice: Dict,
    workSlice: Dict,
    removeOp: (key: string) => FieldConfigChangeOp,
  ) => {
    for (const storageKey of Object.keys(workSlice)) {
      const entry = workSlice[storageKey];
      if (!isRecord(entry)) continue;
      const before = isRecord(baseSlice[storageKey]) ? (baseSlice[storageKey] as Dict) : undefined;
      const key = bareFieldKey(storageKey);
      if (!key) continue;

      // DEFINITION op — emitted when the definition surface changed (or the field is new). The
      // working `defAttrs` is diffed AGAINST the baseline so a boolean turned OFF emits an explicit
      // `false`; the baseline's own attrs (`beforeDef`) are picked WITHOUT a before (pure snapshot).
      const defAttrs = definitionAttrs(entry, before);
      const beforeDef = before ? definitionAttrs(before) : undefined;
      if (!before || changed(defAttrs as MembersConfigValue, beforeDef as MembersConfigValue)) {
        if (nonEmpty(defAttrs)) ops.push({ op: 'set_field', key, attrs: defAttrs });
      }

      // APPLICATION op — the disjoint four-attr surface, emitted when it changed (or is new). Same
      // baseline-diff so an application boolean turned OFF emits `false` (never a dropped undefined).
      const appAttrs = applicationAttrs(entry, before);
      const beforeApp = before ? applicationAttrs(before) : undefined;
      if (changed(appAttrs as MembersConfigValue, beforeApp as MembersConfigValue) && nonEmpty(appAttrs)) {
        ops.push({ op: 'set_field_application', key, attrs: appAttrs });
      }
    }
    for (const storageKey of Object.keys(baseSlice)) {
      if (!(storageKey in workSlice)) {
        const key = bareFieldKey(storageKey);
        if (key) ops.push(removeOp(key));
      }
    }
  };

  // Variable fields removed → delete_field; base overrides removed → reset_field (revert override).
  emitFieldOps(mapSlice(baseline, 'fields'), mapSlice(working, 'fields'), (key) => ({
    op: 'delete_field',
    key,
  }));
  emitFieldOps(
    mapSlice(baseline, 'fixed_overrides'),
    mapSlice(working, 'fixed_overrides'),
    (key) => ({ op: 'reset_field', key }),
  );

  return ops;
}
