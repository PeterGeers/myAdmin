/**
 * Pure readiness helpers for the Application Form Builder's readiness panel
 * (`ApplicationReadinessPanel`, spec 11 task 4.1; R6.1–R6.3, design §6 / §10).
 *
 * These live in their OWN module (not the component file) so the component file exports ONLY a
 * React component — the Vite/React Fast-Refresh requirement the Mail/shell helpers already follow
 * (`mailConfigForm.ts` / `applicationShellForm.ts`). Keeping the three boolean checks + the
 * aggregate here also makes them directly unit-testable without rendering.
 *
 * ## What "send-ready" means (design §6; the spec-10 signal)
 *
 * The builder reuses the public edge's send-ready signal (spec 10
 * `application_readiness.is_send_ready`): a tenant is send-ready IFF it has a **certified sender**
 * — `mail_certified === true` AND a non-blank `mail_domain` — AND a **resolvable slug**. The panel
 * computes these booleans from the already-loaded `config#mail` body + the slug presence; it does
 * NOT re-derive mail internals into the UI beyond the boolean states (NO domain leak in any
 * public-facing string — the panel's guidance stays neutral, R6.2).
 *
 * The builder ALSO shows a third authoring signal the public gate does not itself check —
 * whether at least one field is **on the form** (R6.1) — so the admin understands an empty form
 * won't collect anything. That is an authoring-completeness hint, distinct from the two mail/slug
 * facts the public `is_send_ready` predicate gates on.
 *
 * ## If the field-config carries the signal, thread it (back-compatible)
 *
 * `FieldConfig` does not expose an `application_readiness`/`is_send_ready` field today (the signal
 * is a SAM-plane predicate over `config#mail`, not served to the admin field-config read). Should
 * a future module build add it, {@link computeReadiness} prefers that served boolean for the
 * certified-sender fact over the local `mail_config` derivation — so the panel and the live form
 * never disagree. Absent, it falls back to the local `mail_certified` + `mail_domain` derivation.
 */
import type { MembersConfigValue } from '../../../types/membersConfig';
import type { FieldConfig, FieldConfigField } from '../../../types/members';
import { findField } from './overlayModel';

/** The three readiness facts the panel surfaces (R6.1), each a plain boolean. */
export interface ReadinessState {
  /** The tenant has a certified sender (`mail_certified` + a non-blank `mail_domain`), R6.1. */
  certifiedSender: boolean;
  /** A public slug exists (the form has a resolvable public address), R6.1. */
  slugPresent: boolean;
  /** At least one field is on the public form (`application_visible`), R6.1. */
  hasFieldOnForm: boolean;
  /**
   * The aggregate the public edge gates on (spec 10 `is_send_ready`): certified sender AND a
   * resolvable slug. NOTE it does NOT include {@link hasFieldOnForm} — that is an authoring-
   * completeness hint, not part of the public send-ready predicate (design §6).
   */
  isSendReady: boolean;
}

/**
 * The origin-aware overlay key a field's application attribute is authored under — mirrors
 * `ApplicationFieldList.writeTarget`. A base / base_overridden field authors under
 * `fixed_overrides[{group}.{key}]`; a tenant-added field under `fields[key]`.
 */
function overlayKeyFor(field: FieldConfigField): string {
  const isBase =
    field.origin === 'fixed' ||
    field.provenance === 'base' ||
    field.provenance === 'base_overridden';
  if (isBase) {
    const group = typeof field.group === 'string' && field.group ? field.group : '';
    return group ? `${group}.${field.key}` : field.key;
  }
  return field.key;
}

/**
 * Is this resolved field ON the public form? Precedence mirrors `ApplicationFieldList.isOnForm`
 * exactly so the panel's count can never disagree with the list's toggles:
 *  1. the WORKING overlay's authored `application_visible` (an unsaved toggle wins — by the
 *     origin-aware override key or the bare key);
 *  2. the resolved field's served `application_visible`;
 *  3. default OFF (membership-admin fields and everything else start off, R2.4/R2.3).
 */
function fieldIsOnForm(
  overlay: MembersConfigValue | undefined,
  field: FieldConfigField,
): boolean {
  const authored =
    findField(overlay, overlayKeyFor(field))?.field.application_visible ??
    findField(overlay, field.key)?.field.application_visible;
  if (typeof authored === 'boolean') return authored;
  const served = (field as { application_visible?: boolean }).application_visible;
  if (typeof served === 'boolean') return served;
  return false;
}

/**
 * Whether the loaded `mail_config` describes a CERTIFIED SENDER (the spec-10 pair): a
 * `mail_certified === true` AND a non-blank `mail_domain`. Fail-closed on every missing fact (no
 * mail config, not certified, blank domain → not certified), matching the SAM `is_send_ready`
 * predicate. Never surfaces WHICH fact is missing — the caller's guidance stays neutral (R6.2).
 */
export function hasCertifiedSender(
  mailConfig: FieldConfig['mail_config'] | null | undefined,
): boolean {
  if (!mailConfig) return false;
  if (mailConfig.mail_certified !== true) return false;
  const domain = mailConfig.mail_domain;
  return typeof domain === 'string' && domain.trim().length > 0;
}

/** Whether a non-blank public slug exists (the form has a resolvable public address, R6.1). */
export function hasSlug(slug: string | null | undefined): boolean {
  return typeof slug === 'string' && slug.trim().length > 0;
}

/** Count the fields currently ON the public form (overlay-authored ⊕ served, R6.1). */
export function countFieldsOnForm(
  fieldConfig: FieldConfig | null | undefined,
  overlay: MembersConfigValue | undefined,
): number {
  const fields = fieldConfig?.fields;
  if (!Array.isArray(fields)) return 0;
  return fields.reduce((n, f) => (fieldIsOnForm(overlay, f) ? n + 1 : n), 0);
}

/**
 * Compute the full {@link ReadinessState} from the loaded field config, the working overlay, and
 * the slug (R6.1/R6.3). The certified-sender fact prefers a future served
 * `application_readiness`/`is_send_ready` boolean when the field-config carries one (so the panel
 * and the live form never disagree), else derives it locally from `mail_config` — both
 * back-compatible. `isSendReady` is the public gate (certified sender AND slug), DELIBERATELY
 * excluding the authoring-only "≥1 field on the form" hint (design §6).
 */
export function computeReadiness(
  fieldConfig: FieldConfig | null | undefined,
  overlay: MembersConfigValue | undefined,
  slug: string | null | undefined,
): ReadinessState {
  // Prefer a served readiness signal when the module exposes one (back-compatible); else derive.
  const served = (fieldConfig as { application_readiness?: { is_send_ready?: boolean } } | null)
    ?.application_readiness;
  const certifiedSender =
    typeof served?.is_send_ready === 'boolean'
      ? served.is_send_ready
      : hasCertifiedSender(fieldConfig?.mail_config);
  const slugPresent = hasSlug(slug);
  const hasFieldOnForm = countFieldsOnForm(fieldConfig, overlay) > 0;
  return {
    certifiedSender,
    slugPresent,
    hasFieldOnForm,
    // The public send-ready gate (spec 10): certified sender AND a resolvable slug.
    isSendReady: certifiedSender && slugPresent,
  };
}
