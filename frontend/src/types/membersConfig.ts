/**
 * Type definitions for the Members typed authoring UI (s5c tasks 2.5/2.6, C-EDITOR).
 *
 * Two families of shapes live here:
 *
 *  1. **Definitions** — served by `GET /api/config/members-parameters`. They describe
 *     WHAT controls to render for each of the three `members.*` params. The definition
 *     language extends the ledger def set (`key`, `type`, `label_en`/`label_nl`,
 *     `description`, `depends_on`, `options`, `module`) with two composite types Members
 *     needs: `list<object>` (an ordered list of records) and `map<field_def>` (a keyed
 *     map of field definitions), plus a plain nested `object`.
 *
 *  2. **Values** — the current `members.*` parameter values, read via
 *     `GET /api/tenant-admin/parameters` (namespace `members`) and saved WHOLE-object per
 *     param via `PUT`/`POST` `/api/tenant-admin/parameters` (task 2.6, Property 8: one
 *     save → one PUT → one enqueue_sync).
 */

/** Scalar + composite type discriminator used by a member-parameter definition. */
export type MembersParamType =
  | 'boolean'
  | 'string'
  | 'number'
  | 'string[]'
  | 'object'
  | 'list<object>'
  | 'map<field_def>';

/**
 * A single definition node. A node is either a scalar control (boolean/string/number/
 * string[]) or a composite that carries children:
 *  - `object`         → `object_fields` (a fixed set of typed sub-fields)
 *  - `list<object>`   → `object_fields` (the shape of each row) OR `field_def`
 *  - `map<field_def>` → `object_fields` (nested composite, e.g. functional_groups list)
 *                       OR `field_def` (the shape of each map entry's value)
 */
export interface MembersParamDefinition {
  key: string;
  type: MembersParamType;
  label_en: string;
  label_nl: string;
  description_en?: string;
  description_nl?: string;
  module?: string;
  /** Only shown when the sibling field named here is truthy (mirrors AccountModal). */
  depends_on?: string;
  /** Bare enum value list for a `string`/`string[]` control. */
  options?: string[];
  /** Child definitions for `object` / `list<object>` / nested `map<field_def>`. */
  object_fields?: MembersParamDefinition[];
  /** Child definitions describing the value shape of a `map<field_def>` / list entry. */
  field_def?: MembersParamDefinition[];
}

/**
 * A rich enum option authored as `{ value, label{nl,en}, roles? }` (R4.11/R4.12).
 * `roles` is an optional per-option role restriction — a user sees/assigns only the
 * options their role permits; an option with no `roles` is open to any editor. The
 * backend/domain layer is the authoritative gate; the editor authors the restriction.
 */
export interface EnumOption {
  value: string;
  label: { nl: string; en: string };
  roles?: string[];
}

/** Bilingual label map rendered as `label[language]` (steering 32). */
export interface BilingualLabel {
  nl: string;
  en: string;
}

/**
 * A generic JSON value node for the members.* param objects. The editor works over
 * plain JSON so it stays contract-compatible with the future generic framework.
 */
export type MembersConfigValue =
  | string
  | number
  | boolean
  | null
  | MembersConfigValue[]
  | { [k: string]: MembersConfigValue };

/** The set of resolvable field keys offered by a picker (authoring-time reference help). */
export interface FieldKeyOption {
  key: string;
  label: string;
}
