/**
 * flatViewToOverlay — reconstruct the authoring WORKING OVERLAY from the resolved Flat_View
 * (spec 03 bugfix: the 5.1↔5.3 seam).
 *
 * ## Why this exists
 *
 * Task 5.3 (steering 39) STOPPED the backend surfacing the raw `config#fields` overlay
 * (`field_overlay`) on `GET /members/field-config` — the raw storage shape must not cross the
 * repository boundary. But `MembersConfigEditor` still seeded its in-memory working overlay from
 * `resolvedConfig.field_overlay`, which is now always `undefined` → the buffer was ALWAYS empty,
 * so `editField`/`moveFieldToGroup` (which no-op when the field is absent from the overlay) did
 * nothing. Move-to-group, in particular, silently failed.
 *
 * The fix: rebuild the authoring overlay from the RESOLVED Flat_View (`fieldConfig.fields` +
 * `functional_groups`) the response DOES carry. Each resolved field is bucketed back into the
 * authoring-wire shape the differ (`deriveFieldConfigChangeOps`) and the modals expect:
 *
 *  - a tenant-added VARIABLE field (`origin: 'variable'` / `'fields'`) → `fields[bareKey]`;
 *  - a base / base-overridden field (`origin: 'fixed'` / `'fixed_overrides'`) →
 *    `fixed_overrides["{group}.{key}"]` keyed by its resolved `functional_group` (or `group`);
 *  - a CALCULATED field (`origin: 'calculated'`) is read-only and is OMITTED (never authored).
 *
 * ## Safety: why a "fat" reconstruction is harmless
 *
 * The editor seeds BOTH the working overlay AND the diff baseline from this SAME reconstruction.
 * `deriveFieldConfigChangeOps` only emits an op for an identity whose attrs CHANGED between
 * baseline and working. So a fully-populated (even "fat") buffer that is identical on both sides
 * diffs to NOTHING on load (the editor is not dirty), and a single edit/move produces exactly one
 * op for the touched field. We never re-introduce a whole-record write.
 *
 * Pure: no React, no network.
 */
import type { FieldConfig, FieldConfigField } from '../../../types/members';
import type { MembersConfigValue } from '../../../types/membersConfig';

/** Attributes carried from a resolved field into its authoring overlay entry (definition surface). */
const DEFINITION_KEYS = [
  'type',
  'label',
  'required',
  'visible',
  'order',
  'functional_group',
  'choices',
  'options',
  'scope',
] as const;

/** The four application attributes (the disjoint application surface). */
const APPLICATION_KEYS = [
  'application_visible',
  'application_required',
  'application_choices',
  'format',
] as const;

type Dict = Record<string, MembersConfigValue>;

function pick(field: FieldConfigField, keys: readonly string[]): Dict {
  const out: Dict = {};
  const rec = field as unknown as Record<string, unknown>;
  for (const k of keys) {
    const v = rec[k];
    if (v !== undefined && v !== null) out[k] = v as MembersConfigValue;
  }
  return out;
}

/**
 * Rebuild the authoring overlay (`{ fields, fixed_overrides, functional_groups }`) from the
 * resolved field config. Returns an overlay in the same wire shape the differ + modals consume.
 */
export function flatViewToOverlay(cfg: FieldConfig | null | undefined): MembersConfigValue {
  const fields: Dict = {};
  const fixed_overrides: Dict = {};

  for (const f of cfg?.fields ?? []) {
    if (!f || !f.key) continue;
    // Calculated fields are derived + read-only — never part of the authoring overlay.
    if (f.origin === 'calculated') continue;

    const entry: Dict = { ...pick(f, DEFINITION_KEYS), ...pick(f, APPLICATION_KEYS) };

    // A tenant-added variable field lives under `fields[bareKey]`; a base / overridden field is a
    // `fixed_overrides` entry keyed by the dotted `{group}.{key}` (the storage group is the field's
    // resolved functional_group, falling back to its storage `group`). The server re-derives
    // placement on write, but the buffer mirrors the stored shape so the differ keys line up.
    const isVariable = f.origin === 'variable' || f.origin === 'fields';
    if (isVariable) {
      fields[f.key] = entry;
    } else {
      const grp = (f.functional_group as string | undefined) || (f.group as string | undefined);
      const dotted = grp ? `${grp}.${f.key}` : f.key;
      fixed_overrides[dotted] = entry;
    }
  }

  // Carry the resolved functional-group catalog through verbatim (ordered list the overlay uses).
  const functional_groups = (cfg?.functional_groups ?? []).map((g) => ({
    key: g.key,
    ...(g.label !== undefined ? { label: g.label } : {}),
    ...(g.order !== undefined ? { order: g.order } : {}),
  }));

  return {
    fields,
    fixed_overrides,
    functional_groups,
  } as unknown as MembersConfigValue;
}
