/**
 * CONFIG-DRIVEN Yup schema generator for the public member-application form (spec
 * `Members/application-app`, task 9.2; R10a.2).
 *
 * This is a PURE function: it takes the public field-config (`ApplicationFieldConfig.fields`, the
 * task-4.1 contract served by `GET /public/members/{slug}/field-config`) and produces a Yup schema
 * that mirrors the authoritative SERVER validation (R2.3). The schema is GENERATED from the SAME
 * config the renderer (task 9.1) consumes, so the two cannot drift — it is NEVER a hand-maintained
 * per-tenant schema (R10a.2).
 *
 * Mapping rules (each cites the requirement it mirrors). Every gate is expressed as a `.test(...)`
 * that reads the full flat values via `this.parent`, because the form state is keyed by the FULL
 * DOTTED key and Yup's `.when(ref)` / `.oneOf()` path resolution would treat a dot as a NESTED
 * path (so it could never resolve a flat dotted key):
 *   - `required:true`  → a presence test, GATED by `show_when` — a field hidden by an unmet
 *     condition is neither required nor validated (R4b.5 / R6.3).
 *   - enum (choice SUBSET) → a membership test restricted to the exposed application subset
 *     (mirrors server R4a.3 — a value outside the subset is rejected even if staff-valid).
 *   - `format: EMAIL`  → the shared email check (reuses the canonical `isValidEmail` regex, R7.6).
 *   - `format: IBAN`   → the shared ISO 13616 mod-97 checksum (`isValidIban`, R6.2 / R7.6).
 *   - `show_when`      → the same gating predicate the server + renderer use (R6.3).
 *
 * The server remains AUTHORITATIVE (R6.6): this schema is the accessible, client-side CONVENIENCE
 * mirror. A server 422 `errors[]` is merged back into Formik by dotted key (task 9.3) and wins on
 * any disagreement.
 *
 * ## Dotted keys + clean error paths (task-9.3 consolidation)
 *
 * The schema keys each field by its FULL DOTTED key (the renderer + submit + 422 key, R10a.3). Yup
 * escapes a path segment that contains a dot (it reports `["personal.name"]`), so {@link
 * validateApplication} runs the schema and re-keys the errors back to the PLAIN dotted key
 * (`personal.name`) — the single shape Formik, the renderer's `errors` prop, and the server's
 * `errors[].field` all share. Use `validateApplication` as Formik's `validate` so client errors and
 * server errors collide on the IDENTICAL key.
 *
 * Module boundary: 9.1 owns the renderer, 9.2 (this module) owns the schema generator; both import
 * the shared `ApplicationFieldConfig` type so the contract is single-sourced.
 */

import * as Yup from 'yup';

import { isValidEmail, isValidIban } from '../../../utils/validationHelpers';
import {
  type ApplicationField,
  applicationChoiceValues,
  formKey,
} from '../../public/application/applicationFieldConfig';

/** Translation accessor (i18n `t`). Kept minimal so the generator stays framework-light + testable. */
export type TranslateFn = (key: string) => string;

/** i18n message keys the generated schema references (the `validation` namespace, R10a.4). */
export const APPLICATION_SCHEMA_MESSAGES = {
  required: 'application.validation.required',
  email: 'application.validation.emailInvalid',
  iban: 'application.validation.ibanInvalid',
  oneOf: 'application.validation.choiceInvalid',
} as const;

/** A safe default translator (identity on the key) so the generator is usable without i18n wired. */
const identityT: TranslateFn = (key) => key;

/**
 * Evaluate a field's `show_when` against the current form values — the SAME predicate the server
 * enforces (`evaluate_show_when`) and the renderer's `evaluateShowWhen` uses: a map of
 * `{ controllingKey: expected }`, ALL of which must hold (implicit AND); `expected` is a scalar
 * (equality) or an array (membership); a controlling key resolves by its bare tail in the flat
 * Formik values. An absent/empty `show_when` means always shown.
 *
 * Exported so the renderer and the schema share ONE definition of "is this field shown" (R6.3).
 */
export function isFieldShown(
  showWhen: Record<string, unknown> | null | undefined,
  values: Record<string, unknown>,
): boolean {
  if (!showWhen) return true;
  for (const [key, expected] of Object.entries(showWhen)) {
    const actual = lookupControllingValue(values, key);
    if (Array.isArray(expected)) {
      if (!expected.map(String).includes(String(actual))) return false;
    } else if (String(actual) !== String(expected)) {
      return false;
    }
  }
  return true;
}

/**
 * Look up a controlling key in the flat Formik values. Tolerant of both key-shape directions so
 * the predicate works whether the form state is keyed by the FULL DOTTED key (the renderer + submit
 * shape, R10a.3/§3.2) or a bare tail: an exact hit wins; a dotted `show_when` key also matches its
 * bare tail in the values; a bare `show_when` key also matches a dotted value by its tail.
 */
function lookupControllingValue(values: Record<string, unknown>, key: string): unknown {
  if (key in values) return values[key];
  if (key.includes('.')) {
    const tail = key.slice(key.lastIndexOf('.') + 1);
    if (tail in values) return values[tail];
  } else {
    // Bare show_when key: match a dotted value whose tail equals it (e.g. key `payment_method`
    // against a value keyed `financial.payment_method`).
    for (const vk of Object.keys(values)) {
      if (vk.includes('.') && vk.slice(vk.lastIndexOf('.') + 1) === key) return values[vk];
    }
  }
  return undefined;
}

/** True when a value is present (a non-blank string / a non-null value). */
function isPresent(value: unknown): boolean {
  return typeof value === 'string' ? value.trim().length > 0 : value != null;
}

/** The format checker token, normalized to upper-case; `null` for an absent/unknown-shape format. */
function formatChecker(field: ApplicationField): string | null {
  const fmt = field.format;
  if (!fmt || typeof fmt.checker !== 'string' || fmt.checker.length === 0) return null;
  return fmt.checker.toUpperCase();
}

/**
 * Build the per-field Yup string schema from its config attributes (R4a/R4b/R6.3/R7).
 *
 * All gates are expressed as `.test(...)` callbacks that read the FULL flat form object via
 * `this.parent`, because the form state is keyed by the FULL DOTTED key (R10a.3 / design §3.2) and
 * Yup's `.when(ref, …)` / `.oneOf(...)` path resolution treats a dot as a NESTED path — which would
 * never resolve a flat dotted key. Reading `this.parent` keeps the dotted key literal and lets
 * every gate consult the sibling `show_when` controllers directly, so the schema mirrors the
 * server rule against the IDENTICAL value map the renderer holds and the submit sends.
 *
 * Each gate is `show_when`-aware (R4b.5 / R6.3): a field hidden by an unmet condition is neither
 * required NOR format/enum-checked, exactly as the server neither requires nor validates it.
 */
function buildFieldSchema(field: ApplicationField, t: TranslateFn): Yup.StringSchema {
  let schema = Yup.string();

  /** Whether this field is currently shown, given the full flat values Yup hands via `this.parent`. */
  const shown = (parent: unknown): boolean =>
    isFieldShown(field.show_when, (parent ?? {}) as Record<string, unknown>);

  // Format checker (EMAIL / IBAN). Unknown tokens degrade to no extra checker (R7.3). Skipped for a
  // BLANK value (presence is the required gate's job, R4b.2) AND when the field is hidden (R6.3).
  const checker = formatChecker(field);
  if (checker === 'EMAIL') {
    schema = schema.test('format-email', t(APPLICATION_SCHEMA_MESSAGES.email), function (value) {
      if (!shown(this.parent) || !isPresent(value)) return true;
      return isValidEmail(String(value));
    });
  } else if (checker === 'IBAN') {
    schema = schema.test('format-iban', t(APPLICATION_SCHEMA_MESSAGES.iban), function (value) {
      if (!shown(this.parent) || !isPresent(value)) return true;
      return isValidIban(String(value));
    });
  }

  // Enum SUBSET → membership in the exposed application subset (mirrors server R4a.3). A blank
  // value is tolerated (the required gate handles emptiness); a hidden field is not checked (R6.3);
  // a non-blank, shown value MUST be in the subset.
  const choices = applicationChoiceValues(field);
  if (choices.length > 0) {
    const allowed = new Set(choices);
    schema = schema.test('enum-subset', t(APPLICATION_SCHEMA_MESSAGES.oneOf), function (value) {
      if (!shown(this.parent) || !isPresent(value)) return true;
      return allowed.has(String(value));
    });
  }

  return schema;
}

/**
 * Generate the Formik Yup schema FROM the public field-config (R10a.2). Pure and deterministic:
 * the same config yields the same schema. The returned object schema keys each field by its
 * canonical Formik key ({@link formKey}) — the FULL DOTTED key, the same key the renderer holds,
 * the submit sends, and the server's 422 `errors[].field` carries (R10a.3 / design §3.2).
 *
 * Required-ness is `show_when`-aware (R4b.5 / R6.3): a `required` field is demanded ONLY when it is
 * currently shown (evaluated against the full flat values via `this.parent`), so a hidden
 * conditional field is never demanded client-side, exactly as the server does not require it.
 */
export function buildApplicationValidationSchema(
  fields: ApplicationField[],
  t: TranslateFn = identityT,
): Yup.ObjectSchema<Record<string, unknown>> {
  const shape: Record<string, Yup.StringSchema> = {};

  for (const field of fields) {
    const name = formKey(field);
    let schema = buildFieldSchema(field, t);

    if (field.required) {
      const requiredMsg = t(APPLICATION_SCHEMA_MESSAGES.required);
      schema = schema.test('required-present', requiredMsg, function (value) {
        // Only demand the value when the field is actually shown (R4b.5 / R6.3).
        if (!isFieldShown(field.show_when, (this.parent ?? {}) as Record<string, unknown>)) {
          return true;
        }
        return isPresent(value);
      });
    }

    shape[name] = schema;
  }

  return Yup.object().shape(shape) as unknown as Yup.ObjectSchema<Record<string, unknown>>;
}

/**
 * Normalise a Yup error `path` back to the PLAIN dotted field key.
 *
 * A schema keyed by a dotted key (`personal.name`) makes Yup report the path in its escaped
 * bracket-string form (`["personal.name"]`) because the dot looks like a nested segment. This
 * strips that escaping so the error key equals the field's dotted `key` — the same key the renderer
 * draws errors from and the server's 422 `errors[].field` carries (R10a.3). A plain (dot-free) path
 * passes through unchanged.
 */
export function cleanErrorPath(path: string | undefined): string {
  if (!path) return '';
  // Yup escapes a dotted key as `["a.b"]` (optionally `["a.b"]["c.d"]` for nesting we don't use).
  const match = /^\["(.+)"\]$/.exec(path);
  return match ? match[1] : path;
}

/**
 * Run the generated schema against the flat (dotted-keyed) form values and return a Formik-shaped
 * error map keyed by the PLAIN dotted field key (R10a.3). This is the function the submit page uses
 * as Formik's `validate` so client Yup errors land on the SAME key as the server's 422 `errors[]`.
 *
 * Returns an empty object when everything is valid. Collects ALL field errors (`abortEarly:false`)
 * so the applicant sees every problem at once (mirrors the server's one-shot `errors[]`, R6.5).
 */
export async function validateApplication(
  schema: Yup.ObjectSchema<Record<string, unknown>>,
  values: Record<string, unknown>,
): Promise<Record<string, string>> {
  try {
    await schema.validate(values, { abortEarly: false });
    return {};
  } catch (err) {
    const e = err as Yup.ValidationError;
    const errors: Record<string, string> = {};
    const inner = e.inner && e.inner.length > 0 ? e.inner : [e];
    for (const item of inner) {
      const key = cleanErrorPath(item.path);
      if (key && !errors[key]) errors[key] = item.message;
    }
    return errors;
  }
}
