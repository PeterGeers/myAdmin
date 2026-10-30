/**
 * Derive the `config#scope` dimension set FROM the resolved field configuration (spec 03b — BU-6,
 * Req 4.1/4.2). Pure, no network, no React.
 *
 * ## Why this module exists
 *
 * 03b makes a scope-backed field a NORMAL ENUM: its dropdown vocabulary is its own inline `options`,
 * authored in the field editor — the ONE authoring surface (the standalone scope-dimensions editor
 * was retired). The access-control dimension (`config#scope` on SAM, mirrored into the Flask
 * `members.scope_dimensions` validator copy) is therefore no longer authored independently; it is
 * DERIVED from each scope-axis field's own option VALUES on save. This module is that derivation —
 * the one place that turns "the field's options" into "the scope dimension set", so the authoritative
 * SAM `config#scope` write and the Flask mirror both consume the SAME derived set.
 *
 * ## What it does
 *
 * Given the RESOLVED field config (`GET /members/field-config`), for every field that is a scope
 * AXIS (`scope.enabled` truthy) it emits one {@link ScopeDimension}:
 *
 *  - `key`      — the field's `key` (the dimension key the `ScopeGrant` / access readers key on);
 *  - `label`    — the field's own label (per-language or plain), carried through for display;
 *  - `enabled`  — always `true` (only enabled axes are emitted);
 *  - `values`   — the field's option VALUES (the ONE vocabulary) in option order, de-duplicated.
 *  - `required_for` — carried through from the field's `scope.required_for` when present (the
 *                     access readers consume it; absent → omitted).
 *
 * A field with `scope.enabled` falsy (or no `scope`) is NOT a scope axis and is skipped. The result
 * is ordered by field key for a stable, diff-friendly dimension set. An empty result ( `[]` ) is a
 * valid tenant-wide scope (no dimensions) — the SAM writer accepts it.
 *
 * The frontend is the ONLY cross-plane coordinator (steering 35/39 — SAM and Flask never call each
 * other at runtime). The save path writes the derived set to SAM `config#scope` FIRST (authoritative)
 * and THEN mirrors the SAME set into the Flask `members.scope_dimensions` validator copy; this module
 * produces the set both calls share.
 */
import type {
  FieldConfig,
  FieldConfigField,
  ScopeDimension,
  EnumOptionConfig,
} from '../../../types/members';

/** True when a resolved field is a SCOPE AXIS: it carries `scope` whose `enabled` is truthy. */
function isScopeAxis(field: FieldConfigField): boolean {
  const scope = field.scope;
  return !!scope && scope.enabled === true;
}

/**
 * Extract the stored VALUE from one resolved option entry. An option is either a bare string value
 * or a rich `{ value, label{nl,en}, roles? }` entry; both carry the language-neutral `value` key
 * the member record stores (the dimension values are those keys, never the per-language label).
 * Returns `undefined` for a malformed entry (filtered out by the caller).
 */
function optionValue(opt: string | EnumOptionConfig): string | undefined {
  if (typeof opt === 'string') return opt.trim() ? opt : undefined;
  if (opt && typeof opt === 'object' && typeof opt.value === 'string') {
    return opt.value.trim() ? opt.value : undefined;
  }
  return undefined;
}

/**
 * The option VALUES of a resolved field, in option order, de-duplicated (keeping first occurrence).
 * An absent/empty options list yields `[]` — a scope axis with no authored values (valid; the
 * dimension simply offers nothing until the admin adds an option).
 */
function fieldOptionValues(field: FieldConfigField): string[] {
  const opts = field.options ?? [];
  const seen = new Set<string>();
  const values: string[] = [];
  for (const opt of opts) {
    const v = optionValue(opt);
    if (v !== undefined && !seen.has(v)) {
      seen.add(v);
      values.push(v);
    }
  }
  return values;
}

/**
 * Derive the `config#scope` dimension set from the resolved field config (Req 4.1/4.2).
 *
 * Returns ONE {@link ScopeDimension} per scope-axis field, each carrying the field's option VALUES
 * as its `values` (the ONE vocabulary). Ordered by field `key` for a stable, diff-friendly set.
 * A `null`/absent config, or one with no scope-axis fields, yields `[]` (tenant-wide — a valid
 * scope the SAM writer accepts).
 *
 * This is a DERIVATION (it flows FROM the admin's authored options, the one binding 03b keeps — Req
 * 4); it does not overrule the admin. The caller writes the result to SAM `config#scope` first, then
 * mirrors it into the Flask validator copy.
 */
export function deriveScopeDimensions(
  cfg: FieldConfig | null | undefined,
): ScopeDimension[] {
  const fields = cfg?.fields ?? [];
  const dimensions: ScopeDimension[] = [];

  for (const field of fields) {
    if (!field?.key || !isScopeAxis(field)) continue;

    const dim: ScopeDimension = {
      key: field.key,
      enabled: true,
      values: fieldOptionValues(field),
    };
    if (field.label !== undefined && field.label !== null) {
      dim.label = field.label;
    }
    // `required_for` is carried through on the dimension when the field authored it, so the access
    // readers (SAM `resolve_scope_access` / the Flask grant validators) keep the same roles gate.
    const requiredFor = field.scope?.required_for;
    if (Array.isArray(requiredFor) && requiredFor.length > 0) {
      (dim as ScopeDimension & { required_for?: string[] }).required_for = [...requiredFor];
    }

    dimensions.push(dim);
  }

  dimensions.sort((a, b) => a.key.localeCompare(b.key));
  return dimensions;
}
