/**
 * `applyApiError` — the shared frontend consumer of a thrown {@link ApiError} (API response &
 * error standard v1.0, steering `37`; C3). It turns the structured envelope into user-visible
 * surfacing: LOCALIZED inline field errors (422) matched to form fields, a summary toast, and
 * transition reasons (409) — with graceful fallbacks so a genuine network failure or an unknown
 * code still shows something sensible.
 *
 * Resolution rule (per the spec):
 *  - a field-error line   = `t(entry.code, entry.params) || entry.detail`
 *  - a matched field      → inline via `setFieldError(field, line)`; an UNMATCHED field folds
 *                           into the summary toast (so the user still sees it)
 *  - the summary toast    = `t(code, params)` || joined reasons/unmatched-lines || `error`
 *                           (the backend English message) || `t('errors:api.unknownError')`
 *  - `reasons[]` entries  → the summary toast (legacy `reasons: string[]` tolerated)
 *  - a non-`ApiError`     (network throw, unexpected) → `t('errors:api.serverError')`
 *
 * Codes are `errors`-namespace keys resolved as `t('errors:<path>', params)` — the first dot of
 * the backend's dotted code becomes the i18n `namespace:path` separator, so the helper works no
 * matter which default namespace the calling component's `t` is bound to.
 */

import { ApiError, type FieldErrorEntry, type ReasonEntry } from './ApiError';

/** A minimal translate function (react-i18next's `t`, narrowed to what we use). */
export type TranslateFn = (key: string, options?: Record<string, unknown>) => string;

/** A minimal toast function (Chakra's `useToast()` return, narrowed). */
export type ToastFn = (opts: {
  title: string;
  status?: 'error' | 'warning' | 'info' | 'success';
}) => void;

export interface ApplyApiErrorOptions {
  toast: ToastFn;
  t: TranslateFn;
  /**
   * Set an inline error on a form field (e.g. Formik's `setFieldError`). Receives the DOTTED
   * field key exactly as the backend sent it (`personal.first_name`); the caller maps it to its
   * own field naming if needed. When omitted, every field error folds into the summary toast.
   */
  setFieldError?: (field: string, message: string) => void;
  /**
   * Field keys the form actually has (dotted, as the backend sends them). When provided, an
   * `errors[]` entry whose `field` is NOT in this set folds into the summary toast instead of
   * being dropped. When omitted, ALL entries are treated as matchable.
   */
  knownFields?: Iterable<string>;
  /**
   * Map the backend's DOTTED field key (`personal.first_name`) to the form's OWN field name.
   * Many forms name their inputs by the bare key (`first_name`), so a mapper bridges the two.
   * Return `undefined` to declare the field unmatched (folds into the toast). When omitted, the
   * dotted key is passed to `setFieldError` verbatim (and matched against `knownFields` as-is).
   */
  fieldNameFor?: (dottedField: string) => string | undefined;
}

/**
 * Resolve a backend dotted code to localized copy: the first dot becomes the i18n
 * `namespace:path` separator (e.g. `errors.validation.required` → `errors:validation.required`).
 * Returns `''` when the key cannot be resolved so the caller falls back to the English `detail`.
 *
 * i18next, on an UNRESOLVED key, echoes it back — but it may echo either the full `namespace:path`
 * key OR just the `path` portion (when the namespace does not exist). We treat BOTH echoes as
 * "no copy" so a made-up code never leaks a half-key into the UI.
 */
function resolveCode(t: TranslateFn, code: string, params?: Record<string, unknown>): string {
  const firstDot = code.indexOf('.');
  const path = firstDot === -1 ? code : code.slice(firstDot + 1);
  const key = firstDot === -1 ? code : `${code.slice(0, firstDot)}:${path}`;
  const text = t(key, params);
  if (!text || text === key || text === path) return '';
  return text;
}

/** One field-error line: localized `code` copy, else the backend English `detail`. */
function fieldLine(t: TranslateFn, entry: FieldErrorEntry): string {
  return resolveCode(t, entry.code, entry.params) || entry.detail;
}

/** One reason line: localized `code` copy, else the backend English `detail` (or the raw string). */
function reasonLine(t: TranslateFn, reason: ReasonEntry | string): string {
  if (typeof reason === 'string') return reason;
  return resolveCode(t, reason.code, reason.params) || reason.detail;
}

/**
 * Surface an error to the user. Pass the caught value directly — a non-{@link ApiError} (a
 * network/unexpected throw) degrades to the localized server-error toast.
 */
export function applyApiError(err: unknown, opts: ApplyApiErrorOptions): void {
  const { toast, t, setFieldError, knownFields, fieldNameFor } = opts;

  // Not a structured API error (network failure, thrown non-Error, etc.) → localized fallback.
  if (!(err instanceof ApiError)) {
    toast({ title: t('errors:api.serverError'), status: 'error' });
    return;
  }

  const known = knownFields ? new Set(knownFields) : null;
  const unmatchedLines: string[] = [];

  // 1) Per-field errors (422): inline where matchable, else fold into the summary.
  if (err.hasFieldErrors()) {
    for (const entry of err.errors!) {
      const line = fieldLine(t, entry);
      // Resolve the form's field name: a mapper (dotted → own name) wins; else the dotted key.
      // A mapper returning undefined, or a key not in `knownFields`, means "not on this form".
      const formField = fieldNameFor ? fieldNameFor(entry.field) : entry.field;
      const matchable =
        !!setFieldError &&
        formField !== undefined &&
        (known ? known.has(entry.field) : true);
      if (matchable) {
        setFieldError(formField, line);
      } else {
        unmatchedLines.push(line);
      }
    }
  }

  // 2) Reasons (409 transition denial): always summary-level (not tied to a field).
  const reasonLines = err.hasReasons()
    ? (err.reasons as (ReasonEntry | string)[]).map((r) => reasonLine(t, r))
    : [];

  // 3) The summary toast — ALWAYS shown for an ApiError (the inline field errors are additive,
  //    per R3/task 4.4: "the matching field error INLINE + a toast"). Prefer the top-level code's
  //    localized copy; else the joined reasons/unmatched lines; else the backend English `error`;
  //    else a generic fallback.
  const summaryFromCode = err.code ? resolveCode(t, err.code, err.params) : '';
  const summaryFromLines = [...reasonLines, ...unmatchedLines].filter(Boolean).join(' ');
  const title =
    summaryFromCode ||
    summaryFromLines ||
    err.message ||
    t('errors:api.unknownError');
  toast({ title, status: 'error' });
}
