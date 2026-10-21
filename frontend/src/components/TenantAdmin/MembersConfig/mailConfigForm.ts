/**
 * Pure form helpers for the typed Members Mail function (`MembersMailConfigEditor`).
 *
 * These live in their OWN module (not the component file) so the component file exports ONLY a
 * React component — a requirement for Vite/React Fast Refresh (a file that mixes a component with
 * plain-function exports breaks HMR with a misleading "Failed to reload … syntax errors or
 * importing non-existent modules"). Keeping the pure, side-effect-free mapping/validation here
 * also makes them directly unit-testable without rendering.
 *
 * The form keeps the two consent-notice locale bodies as FLAT strings for the controlled fields;
 * `toMailConfigBody` assembles them into the nested `consent_notice.text{nl,en}` the SAM reader
 * expects (omitting the notice when not well-formed), and `mailConfigToFormValues` flattens the
 * authoritative `GET /members/field-config` `mail_config` body back onto the form.
 */
import type { MembersMailConfigBody } from '../../../services/membersConfigService';
import type { FieldConfig } from '../../../types/members';

/** The flat Formik form shape for the Mail function. */
export interface MailFormValues {
  mail_enabled: boolean;
  mail_domain: string;
  mail_local_part: string;
  mail_certified: boolean;
  mail_reply_to_default: string;
  consent_version: string;
  consent_text_nl: string;
  consent_text_en: string;
}

export const DEFAULT_LOCAL_PART = 'noreply';

export const INITIAL_VALUES: MailFormValues = {
  mail_enabled: false,
  mail_domain: '',
  mail_local_part: DEFAULT_LOCAL_PART,
  mail_certified: false,
  mail_reply_to_default: '',
  consent_version: '',
  consent_text_nl: '',
  consent_text_en: '',
};

/** A loose, blank-tolerant email check — mirrors the sender-identities tab's pattern. */
export const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/**
 * Assemble the reader-shaped `config#mail` body from the form values. The `consent_notice`
 * attribute is INCLUDED only when well-formed — a non-blank version AND at least one non-blank
 * locale body; otherwise it is OMITTED entirely (matching the SAM reader / Flask builder shaping).
 */
export function toMailConfigBody(values: MailFormValues): MembersMailConfigBody {
  const body: MembersMailConfigBody = {
    mail_enabled: values.mail_enabled,
    mail_local_part: values.mail_local_part.trim() || DEFAULT_LOCAL_PART,
    mail_certified: values.mail_certified,
  };

  const domain = values.mail_domain.trim();
  if (domain) body.mail_domain = domain;

  const replyTo = values.mail_reply_to_default.trim();
  if (replyTo) body.mail_reply_to_default = replyTo;

  const version = values.consent_version.trim();
  const text: Record<string, string> = {};
  if (values.consent_text_nl.trim()) text.nl = values.consent_text_nl;
  if (values.consent_text_en.trim()) text.en = values.consent_text_en;
  // Well-formed = a non-blank version AND >= 1 non-blank locale body; else omit the attribute.
  if (version && Object.keys(text).length > 0) {
    body.consent_notice = { version, text };
  }

  return body;
}

/**
 * Map the authoritative `GET /members/field-config` `mail_config` body onto the flat Formik form
 * values. A missing/absent `mail_config` (older module build or load failure) yields the
 * fail-closed defaults (INITIAL_VALUES), so the form never blocks authoring. The nested
 * `consent_notice.{version,text.nl,text.en}` is flattened onto the controlled fields.
 */
export function mailConfigToFormValues(cfg: FieldConfig | null | undefined): MailFormValues {
  const next: MailFormValues = { ...INITIAL_VALUES };
  const mc = cfg?.mail_config;
  if (!mc) {
    // Back-compat: an older build may still carry a top-level mail_enabled without mail_config.
    if (cfg && typeof cfg.mail_enabled === 'boolean') next.mail_enabled = cfg.mail_enabled;
    return next;
  }
  if (typeof mc.mail_enabled === 'boolean') next.mail_enabled = mc.mail_enabled;
  if (typeof mc.mail_certified === 'boolean') next.mail_certified = mc.mail_certified;
  if (typeof mc.mail_domain === 'string') next.mail_domain = mc.mail_domain;
  if (typeof mc.mail_local_part === 'string' && mc.mail_local_part) {
    next.mail_local_part = mc.mail_local_part;
  }
  if (typeof mc.mail_reply_to_default === 'string') {
    next.mail_reply_to_default = mc.mail_reply_to_default;
  }
  const notice = mc.consent_notice;
  if (notice && typeof notice.version === 'string') {
    next.consent_version = notice.version;
    const txt = notice.text ?? {};
    if (typeof txt.nl === 'string') next.consent_text_nl = txt.nl;
    if (typeof txt.en === 'string') next.consent_text_en = txt.en;
  }
  return next;
}
