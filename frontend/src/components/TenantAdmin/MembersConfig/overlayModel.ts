/**
 * Pure working-model for the single `field_overlay` object (Members config redesign Phase 3,
 * step 11 — task 4.0).
 *
 * The whole group → field → attribute drill-down (tasks 4.4–4.8) authors the ONE `field_overlay`
 * working object — this module is the IN-MEMORY WORKING BUFFER for the editor (spec 03 task 5.2).
 * Every modal mutation goes through a PURE `(overlay, …) → overlay'` helper here — no network, no
 * React, no hidden state. The editor holds one working copy and these helpers transform it; on Save
 * the editor DIFFS the working copy against the loaded baseline into an identity-keyed Change-Op
 * list (`deriveFieldConfigChangeOps` → `saveFieldConfigChangeOps` → `PUT /members/config/fields`).
 *
 * NOTE (spec 03 task 5.2): these helpers NO LONGER assemble a whole object for the server. The
 * retired whole-object write (PUT the entire overlay back WHOLE, the catalog-truncation root cause)
 * is gone; `withSlices` below is purely a BUFFER-REBUILD primitive the pure helpers share, not a
 * server payload builder. The three-map / dotted-`{group}.{key}` layout a base-field override is
 * keyed under is a BUFFER DETAIL only — it never crosses the wire (the Change-Op builder strips it
 * to the bare identity and the server owns storage placement, steering 39). Keeping the buffer pure
 * makes the drill-down trivially unit-testable.
 *
 * The stored shape (verified in code — `MembersConfigEditor` + the single-save suite fixture):
 *
 *   field_overlay = {
 *     functional_groups: Array<{ key, label_en?, label_nl?, order? }>,   // an ordered LIST
 *     fields:           { [fieldKey]: FieldDef },                        // a keyed MAP
 *     fixed_overrides:  { [dottedKey]: FieldDef },                       // a keyed MAP
 *   }
 *
 * where a `FieldDef` carries the per-field attributes authored by the modal:
 * `{ type?, label_en?, label_nl?, required?, visible?, functional_group?, choices?, order?,
 *    scope?, read_only?, … }`. A field authored under `fields` is a tenant-added field; a dotted
 * entry under `fixed_overrides` re-presents a platform base field (R1.2 provenance derivation lives
 * on the SERVER — this module only authors the overlay the server resolves).
 *
 * Design rules this module enforces:
 *  - **Immutable:** every helper returns a NEW overlay; the input is never mutated.
 *  - **Derived order (`38` rule 2):** group order is `(group.order, key)`; field order within a
 *    group is `(field.order, key)`. NO new absolute-position field is introduced.
 *  - **Delete-group only when empty (R4.2):** `deleteGroup` refuses a group that still has fields
 *    (the UI disables the control; this is the authoritative in-model guard; the Flask validator
 *    remains authoritative on save).
 *  - **Move-to-group (R4.3):** reassigns a field's `functional_group` only.
 */

import type { MembersConfigValue } from '../../../types/membersConfig';

// ---------------------------------------------------------------------------
// Working-model shapes (a thin, well-typed VIEW over the raw field_overlay JSON)
// ---------------------------------------------------------------------------

/** A functional group as stored in `field_overlay.functional_groups` (an ordered list entry). */
export interface OverlayGroup {
  key: string;
  label_en?: string;
  label_nl?: string;
  order?: number;
  /** Any other authored attributes are preserved verbatim on read/write. */
  [k: string]: MembersConfigValue | undefined;
}

/** A field definition as stored under `field_overlay.fields[key]` / `.fixed_overrides[key]`. */
export interface OverlayField {
  type?: string;
  label_en?: string;
  label_nl?: string;
  required?: boolean;
  visible?: boolean;
  read_only?: boolean;
  functional_group?: string;
  order?: number;
  /**
   * The enum vocabulary — the ONE canonical key (spec 03a / C1). The field modal authors the
   * vocabulary here as `options` and the Change-Op write emits ONLY `options` (the legacy `choices`
   * key is retired on both the write surface and the authoring buffer). Rich
   * `{ value, label{nl,en}, roles? }` entries or a bare `string[]`.
   */
  options?: MembersConfigValue;
  /**
   * The scope-axis attribute, when authored. Single-vocabulary (R3.2/R3.3): `{ enabled,
   * required_for? }` ONLY — NO `values` list. The scope VALUES ARE the field's enum values
   * (`options`); the Flask builder derives the `config#scope` dimension values from those on save
   * (R3.4). A legacy stored `scope.values` is honoured server-side as a migration fallback only.
   */
  scope?: MembersConfigValue;
  /**
   * The four per-field APPLICATION attributes authored by the Application Form Builder (spec 11,
   * design §3.1/§10). They are carried verbatim onto the ONE `field_overlay` object through the
   * SAME `overlayModel` helpers the field modal uses (no parallel write path) and read/enforced by
   * the SAM plane (`config#fields` → the public form, spec 10). The `[k: string]: …` index already
   * lets these pass through unchanged; the explicit typing is for authoring ergonomics + tests.
   */
  /** On the public application form? (R2/R3 — the on-the-form toggle). */
  application_visible?: boolean;
  /** Required ON the form (R3.1 — may TIGHTEN an optional field, never RELAX a platform-required one). */
  application_required?: boolean;
  /** Enum SUBSET of the field's own choices (R3.2); `null`/absent = the full set. */
  application_choices?: string[] | null;
  /** A platform-known validator token (R3.3); `null`/absent = no format check. */
  format?: { checker: string; params?: object } | null;
  /** Any other authored attributes are preserved verbatim. */
  [k: string]: MembersConfigValue | undefined;
}

/** Which overlay map a field lives in — a tenant-added field vs a base-field override. */
export type FieldOrigin = 'fields' | 'fixed_overrides';

/** A field paired with the overlay map it was read from (so writes target the right map). */
export interface OverlayFieldEntry {
  key: string;
  origin: FieldOrigin;
  field: OverlayField;
}

// ---------------------------------------------------------------------------
// Internal helpers (safe, defensive access over the loosely-typed JSON)
// ---------------------------------------------------------------------------

/** True for a plain object (not array / null). */
function isRecord(v: unknown): v is Record<string, MembersConfigValue> {
  return !!v && typeof v === 'object' && !Array.isArray(v);
}

/** Read the overlay as a record (an absent/garbage value becomes an empty object). */
function asOverlay(overlay: MembersConfigValue | undefined): Record<string, MembersConfigValue> {
  return isRecord(overlay) ? overlay : {};
}

/** Read a map slice (`fields` / `fixed_overrides`) as a record. */
function mapSlice(
  overlay: MembersConfigValue | undefined,
  slice: FieldOrigin,
): Record<string, MembersConfigValue> {
  const o = asOverlay(overlay);
  const m = o[slice];
  return isRecord(m) ? m : {};
}

/** Read the `functional_groups` list as an array of group records. */
function groupList(overlay: MembersConfigValue | undefined): OverlayGroup[] {
  const o = asOverlay(overlay);
  const list = o.functional_groups;
  if (!Array.isArray(list)) return [];
  return list.filter(isRecord).map((g) => ({ ...(g as OverlayGroup) }));
}

const orderOf = (v: { order?: number } | undefined): number =>
  typeof v?.order === 'number' ? v.order : Number.MAX_SAFE_INTEGER;

// ---------------------------------------------------------------------------
// READ helpers (derived views the tables render)
// ---------------------------------------------------------------------------

/**
 * The functional groups in DERIVED display order `(group.order, key)` (`38` rule 2).
 * Returns NEW objects; the overlay is not mutated.
 */
export function listGroups(overlay: MembersConfigValue | undefined): OverlayGroup[] {
  return [...groupList(overlay)].sort((a, b) => {
    const oa = orderOf(a);
    const ob = orderOf(b);
    if (oa !== ob) return oa - ob;
    return String(a.key).localeCompare(String(b.key));
  });
}

/** True when a group with this key exists in the overlay. */
export function groupExists(overlay: MembersConfigValue | undefined, key: string): boolean {
  return groupList(overlay).some((g) => g.key === key);
}

/** Every field entry across BOTH overlay maps, paired with its origin map. */
export function listAllFields(overlay: MembersConfigValue | undefined): OverlayFieldEntry[] {
  const entries: OverlayFieldEntry[] = [];
  (['fields', 'fixed_overrides'] as FieldOrigin[]).forEach((origin) => {
    const slice = mapSlice(overlay, origin);
    Object.keys(slice).forEach((key) => {
      const f = slice[key];
      if (isRecord(f)) entries.push({ key, origin, field: { ...(f as OverlayField) } });
    });
  });
  return entries;
}

/**
 * The fields assigned to a given group key, in DERIVED order `(field.order, key)`.
 * A field's group is read from its `functional_group` attribute.
 */
export function listFieldsInGroup(
  overlay: MembersConfigValue | undefined,
  groupKey: string,
): OverlayFieldEntry[] {
  return listAllFields(overlay)
    .filter((e) => (e.field.functional_group ?? null) === groupKey)
    .sort((a, b) => {
      const oa = orderOf(a.field);
      const ob = orderOf(b.field);
      if (oa !== ob) return oa - ob;
      return a.key.localeCompare(b.key);
    });
}

/** The number of fields assigned to a group (used by the delete-when-empty guard). */
export function groupFieldCount(overlay: MembersConfigValue | undefined, groupKey: string): number {
  return listAllFields(overlay).filter((e) => (e.field.functional_group ?? null) === groupKey)
    .length;
}

/**
 * The "ungrouped" bucket (R4.3): fields whose `functional_group` is ABSENT, or references a group
 * that is NOT a defined catalog group — surfaced, never silently dropped. Ordered `(field.order,
 * key)`. This mirrors `groupResolvedFields`'s trailing bucket, but over the WORKING overlay (so a
 * freshly-authored unresolvable reference shows immediately, before Save).
 */
export function listUngroupedFields(
  overlay: MembersConfigValue | undefined,
): OverlayFieldEntry[] {
  const defined = new Set(groupList(overlay).map((g) => g.key));
  return listAllFields(overlay)
    .filter((e) => {
      const gk = e.field.functional_group ?? null;
      return gk === null || !defined.has(gk);
    })
    .sort((a, b) => {
      const oa = orderOf(a.field);
      const ob = orderOf(b.field);
      if (oa !== ob) return oa - ob;
      return a.key.localeCompare(b.key);
    });
}

/** Find one field entry by key across both maps (null when absent). */
export function findField(
  overlay: MembersConfigValue | undefined,
  key: string,
): OverlayFieldEntry | null {
  const all = listAllFields(overlay);
  // 1) exact storage-key match (`fields[key]` bare, or `fixed_overrides` dotted `{group}.{key}`).
  const exact = all.find((e) => e.key === key);
  if (exact) return exact;
  // 2) BARE-key fallback (spec 03 bugfix): a base-field override is stored under the dotted
  //    `{group}.{key}`, but callers (move-to-group, the actions slot) address it by its BARE key.
  //    Match the dotted entry whose trailing `.key` segment equals the requested bare key so an
  //    edit/move on a base field resolves instead of silently no-op'ing. (A plain `fields` entry
  //    is already matched exactly above, so this only ever rescues a dotted override.)
  const bare = all.find((e) => e.key.includes('.') && e.key.slice(e.key.indexOf('.') + 1) === key);
  return bare ?? null;
}

// ---------------------------------------------------------------------------
// WRITE helpers (pure — each returns a NEW overlay)
// ---------------------------------------------------------------------------

/** Rebuild an overlay from its three slices, preserving any other top-level keys. */
function withSlices(
  overlay: MembersConfigValue | undefined,
  next: {
    functional_groups?: OverlayGroup[];
    fields?: Record<string, MembersConfigValue>;
    fixed_overrides?: Record<string, MembersConfigValue>;
  },
): Record<string, MembersConfigValue> {
  const o = { ...asOverlay(overlay) };
  if (next.functional_groups !== undefined) {
    o.functional_groups = next.functional_groups as unknown as MembersConfigValue;
  }
  if (next.fields !== undefined) o.fields = next.fields;
  if (next.fixed_overrides !== undefined) o.fixed_overrides = next.fixed_overrides;
  return o;
}

/**
 * CREATE a functional group. No-op (returns the overlay unchanged) when a group with the same key
 * already exists — the caller surfaces that as a validation message. Appends to the stored list;
 * display order is derived, so insertion position does not matter.
 */
export function createGroup(
  overlay: MembersConfigValue | undefined,
  group: OverlayGroup,
): MembersConfigValue {
  if (!group.key || groupExists(overlay, group.key)) {
    return asOverlay(overlay);
  }
  const groups = groupList(overlay);
  return withSlices(overlay, { functional_groups: [...groups, { ...group }] });
}

/**
 * EDIT a group's own attributes (`key` is the identity — a key rename also reassigns the fields
 * that reference the old key, so no field is orphaned). When the group is NOT yet in the working
 * overlay — the PLATFORM BASE group case (`personal`, `motor`, …), which lives only in the server's
 * resolved `functional_groups` catalog — the edit MATERIALIZES it as a new overlay entry (a tenant
 * override of the base group's attributes). Without this, editing a base group's order/label was a
 * silent NO-OP: the modal closed, nothing was written, nothing saved (bugfix — see
 * root-cause-analysis.md; the display-side twin is the modal's `resolvedGroup` seed). Still a no-op
 * only when a rename would collide with another existing group.
 */
export function editGroup(
  overlay: MembersConfigValue | undefined,
  key: string,
  patch: Partial<OverlayGroup>,
): MembersConfigValue {
  const groups = groupList(overlay);
  const idx = groups.findIndex((g) => g.key === key);

  // Base group not yet materialized into the overlay: create the override entry from the patch.
  // (A rename of a not-yet-materialized base group keys the new entry by the renamed key and
  // re-points its fields, mirroring the in-overlay rename path below.)
  if (idx < 0) {
    const nextKey = patch.key ?? key;
    if (groups.some((g) => g.key === nextKey)) {
      // Target key already exists as a real overlay group — refuse (caller validates).
      return asOverlay(overlay);
    }
    const created = withSlices(overlay, {
      functional_groups: [...groups, { ...patch, key: nextKey } as OverlayGroup],
    });
    return nextKey !== key ? reassignGroupKey(created, key, nextKey) : created;
  }

  const nextKey = patch.key ?? key;
  if (nextKey !== key && groups.some((g) => g.key === nextKey)) {
    // A rename onto an existing key would merge two groups — refuse (caller validates).
    return asOverlay(overlay);
  }

  const nextGroups = groups.map((g, i) => (i === idx ? { ...g, ...patch, key: nextKey } : g));

  // On a key rename, re-point every field that referenced the old group key.
  if (nextKey !== key) {
    return reassignGroupKey(withSlices(overlay, { functional_groups: nextGroups }), key, nextKey);
  }
  return withSlices(overlay, { functional_groups: nextGroups });
}

/**
 * DELETE a group — ONLY when it holds no fields (R4.2). A non-empty group is returned unchanged
 * (the UI disables the control and shows the reason; the Flask validator is authoritative on save).
 * Use {@link groupFieldCount} to drive the UI's enabled/disabled state.
 */
export function deleteGroup(
  overlay: MembersConfigValue | undefined,
  key: string,
): MembersConfigValue {
  if (groupFieldCount(overlay, key) > 0) {
    return asOverlay(overlay); // guard: never delete a non-empty group
  }
  const groups = groupList(overlay).filter((g) => g.key !== key);
  return withSlices(overlay, { functional_groups: groups });
}

/**
 * CREATE a field in a given overlay map (default `fields` — a tenant-added field). No-op when the
 * key already exists in EITHER map (keys are unique across the overlay).
 */
export function createField(
  overlay: MembersConfigValue | undefined,
  key: string,
  field: OverlayField,
  origin: FieldOrigin = 'fields',
): MembersConfigValue {
  if (!key || findField(overlay, key)) return asOverlay(overlay);
  const slice = { ...mapSlice(overlay, origin) };
  slice[key] = { ...field } as MembersConfigValue;
  return withSlices(overlay, { [origin]: slice });
}

/**
 * EDIT a field's attributes (shallow-merge the patch into the stored field). Operates on whichever
 * map the field currently lives in. No-op when the field does not exist. Passing an attribute value
 * of `undefined` DELETES that attribute (see {@link deleteFieldAttribute} for the explicit form).
 */
export function editField(
  overlay: MembersConfigValue | undefined,
  key: string,
  patch: Partial<OverlayField>,
): MembersConfigValue {
  const entry = findField(overlay, key);
  if (!entry) return asOverlay(overlay);
  const slice = { ...mapSlice(overlay, entry.origin) };
  // The entry's ACTUAL storage key (dotted `{group}.{key}` for a base override) — NOT the caller's
  // key, which may be the bare form (spec 03 bugfix — findField resolves bare→dotted so a
  // move-to-group / edit on a base field no longer no-ops).
  const storageKey = entry.key;
  const merged: Record<string, MembersConfigValue> = { ...(slice[storageKey] as object) } as Record<
    string,
    MembersConfigValue
  >;
  Object.entries(patch).forEach(([k, v]) => {
    if (v === undefined) delete merged[k];
    else merged[k] = v as MembersConfigValue;
  });
  slice[storageKey] = merged;
  return withSlices(overlay, { [entry.origin]: slice });
}

/**
 * UPSERT (create-or-edit) a field into a SPECIFIC overlay slice — the origin-aware write-back the
 * field modal routes through (remediation task 2.2, R1). The WRITE target per field is
 * provenance/origin-dependent: a tenant-ADDED field is authored under `fields[key]`; a
 * base / base_overridden field's presentation override is authored under
 * `fixed_overrides[dottedKey]`; a calculated field is read-only and never written (the modal
 * guards that before calling this helper).
 *
 * The slice is chosen by the caller (`origin`), with one deliberate exception preserving existing
 * behaviour: if the field ALREADY lives in a slice, the edit stays in THAT slice regardless of the
 * requested `origin` — a field a tenant previously authored under `fields` keeps being edited there
 * (so a base field already overridden under `fixed_overrides`, or a tenant field under `fields`, is
 * never duplicated across both maps). The first time a base field is edited (no overlay entry yet)
 * it is CREATED under the requested `origin` (`fixed_overrides`), seeding its presentation override.
 *
 * Pure — returns a NEW overlay; the single-save contract is unchanged (one `onChange` → one commit →
 * one request). Passing an attribute value of `undefined` in the patch DELETES that attribute (same
 * semantics as {@link editField}).
 */
export function upsertField(
  overlay: MembersConfigValue | undefined,
  key: string,
  patch: Partial<OverlayField>,
  origin: FieldOrigin = 'fields',
): MembersConfigValue {
  if (!key) return asOverlay(overlay);
  const existing = findField(overlay, key);
  if (existing) {
    // Edit in place — a field already in a slice is never moved to the other map.
    return editField(overlay, key, patch);
  }
  // First write — create in the requested slice with the (undefined-stripped) patch.
  const field: OverlayField = {};
  Object.entries(patch).forEach(([k, v]) => {
    if (v !== undefined) (field as Record<string, MembersConfigValue>)[k] = v as MembersConfigValue;
  });
  return createField(overlay, key, field, origin);
}

/** DELETE a field entirely (from whichever map it lives in). No-op when absent. */
export function deleteField(
  overlay: MembersConfigValue | undefined,
  key: string,
): MembersConfigValue {
  const entry = findField(overlay, key);
  if (!entry) return asOverlay(overlay);
  const slice = { ...mapSlice(overlay, entry.origin) };
  // Use the entry's ACTUAL storage key (dotted for a base override), not the caller's key, which
  // may be the bare form (spec 03 bugfix — findField now resolves bare→dotted).
  delete slice[entry.key];
  return withSlices(overlay, { [entry.origin]: slice });
}

/**
 * SET (add or edit) a single attribute on a field. Thin wrapper over {@link editField} for the
 * modal's per-attribute add/edit affordances.
 */
export function setFieldAttribute(
  overlay: MembersConfigValue | undefined,
  key: string,
  attr: string,
  value: MembersConfigValue,
): MembersConfigValue {
  return editField(overlay, key, { [attr]: value } as Partial<OverlayField>);
}

/** DELETE a single attribute from a field (the modal's per-attribute remove affordance). */
export function deleteFieldAttribute(
  overlay: MembersConfigValue | undefined,
  key: string,
  attr: string,
): MembersConfigValue {
  return editField(overlay, key, { [attr]: undefined } as Partial<OverlayField>);
}

/**
 * MOVE a field to another group (R4.3) — reassigns ONLY its `functional_group` attribute. The
 * caller offers only catalog-resolvable groups in the picker; this helper does not itself validate
 * the target so an already-authored unresolvable reference can still be re-pointed. No-op when the
 * field does not exist.
 */
export function moveFieldToGroup(
  overlay: MembersConfigValue | undefined,
  key: string,
  targetGroupKey: string,
): MembersConfigValue {
  return editField(overlay, key, { functional_group: targetGroupKey });
}

/**
 * Internal: re-point every field whose `functional_group` references `fromKey` to `toKey` (used by
 * {@link editGroup} on a group-key rename so no field is orphaned).
 */
function reassignGroupKey(
  overlay: MembersConfigValue | undefined,
  fromKey: string,
  toKey: string,
): MembersConfigValue {
  let next: MembersConfigValue = asOverlay(overlay);
  listAllFields(next)
    .filter((e) => (e.field.functional_group ?? null) === fromKey)
    .forEach((e) => {
      next = editField(next, e.key, { functional_group: toKey });
    });
  return next;
}
