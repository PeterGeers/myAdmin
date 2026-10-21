/**
 * Pure form helpers for the Application Form Builder's form-shell panel
 * (`ApplicationFormShellPanel`, spec 11 task 3.2; R5.1/R5.2/R5.3, design §2.3/§3.1/§6).
 *
 * These live in their OWN module (not the component file) so the component file exports ONLY a
 * React component — the Vite/React Fast-Refresh requirement the Mail function already follows
 * (`mailConfigForm.ts`). Keeping the slug/URL derivation, the embed snippet, the consent-version
 * bump, and the `config#mail` working-body assembly here also makes them directly unit-testable
 * without rendering.
 *
 * ## What this panel authors (design §2.3 / §3.1)
 *
 * The form shell authors the FORM-level settings onto the ONE SAM-owned `config#mail` row — the
 * SAME row the Mail sub-tab owns (one authoring surface per row, steering 38 rule 5):
 *  - `consent_notice {version, text{nl,en}}` — the versioned bilingual consent notice (R5.3), the
 *    version BUMPED whenever the text changes;
 *  - `application_embed_origins: string[]` — the allowed embedding origin(s) (R5.2); empty =
 *    standalone (no embedding).
 *
 * The public slug/URL is DERIVED + DISPLAYED only (E4/R5.1) — the slug itself stays with the
 * Landing Page editor, so the panel never authors it.
 *
 * ## Preserve-not-clobber (R5.5)
 *
 * The form-shell mail settings commit through the EXISTING `PUT /members/config/mail` write as ONE
 * `config#mail` object. Because the Mail sub-tab also owns scalars on that row (`mail_enabled`,
 * `mail_certified`, `mail_domain`, `mail_local_part`, `mail_reply_to_default`,
 * `application_scope_copy`), the builder SEEDS its working body from the loaded `mail_config` and
 * carries those scalars through VERBATIM, overlaying only the two attributes it authors. A mail
 * save from the builder therefore never wipes a value the Mail sub-tab set.
 */
import type { MembersMailConfigBody } from '../../../services/membersConfigService';
import type { FieldConfig } from '../../../types/members';

/** How the public form is embedded (R5.2). */
export type EmbedMode = 'standalone' | 'iframe';

/** The host suffix the public application form is served under (spec 10 D19 — `<slug>.jabaki.nl`). */
export const PUBLIC_FORM_HOST_SUFFIX = 'jabaki.nl';

/** The flat panel state the form-shell UI binds to. */
export interface ShellFormValues {
  /** The resolved landing-page slug (null/absent = no public address yet, R5.1). */
  slug: string | null;
  /** standalone (own page) or iframe-embedded (R5.2). */
  embedMode: EmbedMode;
  /** The allowed embedding origin(s) — authored onto `application_embed_origins` (R5.2). */
  embedOrigins: string[];
  /** The consent-notice version id (bumped on text change, R5.3). */
  consentVersion: string;
  /** The consent-notice NL body (R5.3). */
  consentTextNl: string;
  /** The consent-notice EN body (R5.3). */
  consentTextEn: string;
}

/**
 * Derive the public application-form URL from the tenant's landing-page slug (E4/R5.1; spec 10
 * D19 — host-based `<slug>.jabaki.nl`). Returns `null` when no slug exists so the panel can state
 * "no public address yet" and point at the Landing Page editor rather than inventing one here.
 */
export function derivePublicUrl(slug: string | null | undefined): string | null {
  const s = (slug ?? '').trim();
  if (!s) return null;
  return `https://${s}.${PUBLIC_FORM_HOST_SUFFIX}`;
}

/**
 * The copy-ready `<iframe>` snippet referencing the public URL (R5.2). Returns an empty string
 * when there is no public URL yet (nothing to embed).
 */
export function buildIframeSnippet(publicUrl: string | null): string {
  if (!publicUrl) return '';
  return (
    `<iframe src="${publicUrl}" title="Application form" ` +
    `width="100%" height="900" style="border:0" loading="lazy"></iframe>`
  );
}

/**
 * Normalise the raw origins textarea (one origin per line / comma-separated) into a clean,
 * de-duplicated, order-preserving list of non-blank origin strings. The server re-validates the
 * origin shape authoritatively (spec 11 task 5.1) — this is author-time tidy-up only.
 */
export function parseEmbedOrigins(raw: string): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const piece of raw.split(/[\n,]/)) {
    const origin = piece.trim();
    if (!origin || seen.has(origin)) continue;
    seen.add(origin);
    out.push(origin);
  }
  return out;
}

/** The inverse of {@link parseEmbedOrigins} — a stored list back to the textarea (one per line). */
export function embedOriginsToText(origins: string[] | null | undefined): string {
  return (origins ?? []).join('\n');
}

/**
 * Map the authoritative `GET /members/field-config` `mail_config` body onto the flat form-shell
 * values, flattening the nested `consent_notice`. A missing/absent `mail_config` (older build or
 * a load failure) yields empty defaults so the panel never blocks authoring. The embed mode is
 * DERIVED: a tenant with ≥1 configured origin is treated as `iframe`, otherwise `standalone`.
 */
export function mailConfigToShellValues(
  cfg: FieldConfig | null | undefined,
  slug: string | null | undefined,
): ShellFormValues {
  const next: ShellFormValues = {
    slug: (slug ?? '').trim() || null,
    embedMode: 'standalone',
    embedOrigins: [],
    consentVersion: '',
    consentTextNl: '',
    consentTextEn: '',
  };
  const mc = cfg?.mail_config;
  if (!mc) return next;

  const notice = mc.consent_notice;
  if (notice && typeof notice.version === 'string') {
    next.consentVersion = notice.version;
    const txt = notice.text ?? {};
    if (typeof txt.nl === 'string') next.consentTextNl = txt.nl;
    if (typeof txt.en === 'string') next.consentTextEn = txt.en;
  }

  const origins = mc.application_embed_origins;
  if (Array.isArray(origins) && origins.length > 0) {
    next.embedOrigins = origins.filter((o): o is string => typeof o === 'string' && !!o.trim());
    if (next.embedOrigins.length > 0) next.embedMode = 'iframe';
  }

  return next;
}

/**
 * Compute the consent-notice version to SAVE (R5.3). The version is BUMPED (a new stable id) only
 * when the notice TEXT changed from the last-saved baseline — an existing applicant record's
 * recorded version is never retroactively changed, so a save that leaves the text untouched keeps
 * its version. A freshly authored notice with no version yet always gets one.
 *
 * The bump is a date-stamped, collision-resistant id (`vYYYYMMDD-HHMMSS`); the exact format is not
 * contractual — only that it is non-blank and changes when the text changes.
 */
export function resolveConsentVersion(
  current: ShellFormValues,
  baseline: Pick<ShellFormValues, 'consentVersion' | 'consentTextNl' | 'consentTextEn'>,
  now: Date = new Date(),
): string {
  const curVersion = current.consentVersion.trim();
  const textChanged =
    current.consentTextNl !== baseline.consentTextNl ||
    current.consentTextEn !== baseline.consentTextEn;
  // Unchanged text keeps the authored/last-saved version verbatim (never a retroactive bump).
  if (!textChanged && curVersion) return curVersion;
  // Changed text (or a first-ever notice with no version) → a fresh stamped id.
  const hasText = !!(current.consentTextNl.trim() || current.consentTextEn.trim());
  if (!hasText) return curVersion; // nothing to version yet
  return stampVersion(now);
}

/** A collision-resistant, human-readable version stamp `vYYYYMMDD-HHMMSS` (UTC). */
export function stampVersion(now: Date = new Date()): string {
  const p = (n: number, w = 2) => String(n).padStart(w, '0');
  return (
    `v${now.getUTCFullYear()}${p(now.getUTCMonth() + 1)}${p(now.getUTCDate())}-` +
    `${p(now.getUTCHours())}${p(now.getUTCMinutes())}${p(now.getUTCSeconds())}`
  );
}

/**
 * Assemble the `config#mail` body the form-shell panel commits (R5.5). It SEEDS from the loaded
 * `mail_config` so every scalar the Mail sub-tab owns (`mail_enabled`, `mail_local_part`,
 * `mail_certified`, `mail_domain`, `mail_reply_to_default`, `application_scope_copy`) is carried
 * through VERBATIM; the panel overlays ONLY the two attributes it authors:
 *  - `consent_notice` — included only when well-formed (a non-blank version AND ≥1 non-blank
 *    locale body), else omitted entirely (matching the SAM reader / Mail form shaping);
 *  - `application_embed_origins` — the embed origins when mode is `iframe` and ≥1 origin exists;
 *    standalone (or no origins) OMITS the key (= no embedding).
 */
export function toShellMailBody(
  values: ShellFormValues,
  loaded: FieldConfig['mail_config'] | null | undefined,
  consentVersionToSave: string,
): MembersMailConfigBody {
  // Seed from the loaded mail scalars so a form-shell save never clobbers the Mail sub-tab's values.
  const body: MembersMailConfigBody = {
    mail_enabled: loaded?.mail_enabled ?? false,
    mail_local_part: (loaded?.mail_local_part ?? '').trim() || 'noreply',
    mail_certified: loaded?.mail_certified ?? false,
  };
  if (loaded?.mail_domain) body.mail_domain = loaded.mail_domain;
  if (loaded?.mail_reply_to_default) body.mail_reply_to_default = loaded.mail_reply_to_default;
  if (typeof loaded?.application_scope_copy === 'boolean') {
    body.application_scope_copy = loaded.application_scope_copy;
  }

  // Consent notice — well-formed only (non-blank version + >=1 non-blank locale body), else omit.
  const version = consentVersionToSave.trim();
  const text: Record<string, string> = {};
  if (values.consentTextNl.trim()) text.nl = values.consentTextNl;
  if (values.consentTextEn.trim()) text.en = values.consentTextEn;
  if (version && Object.keys(text).length > 0) {
    body.consent_notice = { version, text };
  }

  // Embed origins — only when embedding (iframe) with >=1 origin; standalone omits the key.
  if (values.embedMode === 'iframe' && values.embedOrigins.length > 0) {
    body.application_embed_origins = values.embedOrigins;
  }

  return body;
}
