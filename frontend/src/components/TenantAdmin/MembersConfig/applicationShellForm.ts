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
import {
  IFRAME_RESIZE_MESSAGE_TYPE,
  IFRAME_RESIZE_SOURCE,
} from '../../public/application/iframeResize';

/** How the public form is embedded (R5.2). */
export type EmbedMode = 'standalone' | 'iframe';

/** The host suffix the public application form is served under (spec 10 D19 — `<slug>.jabaki.nl`). */
export const PUBLIC_FORM_HOST_SUFFIX = 'jabaki.nl';

/**
 * The CONFIRMED v1 external embedding targets (R5.2b / E4b, spec 11 task 3.2). These are the two
 * origins the product owner confirmed for day-one iframe embedding:
 *  - `https://sites.google.com` — a Google Workspace Site (served at `sites.google.com/<domain>/…`
 *    but still origin `https://sites.google.com`, so one entry covers all of a tenant's Sites embeds);
 *  - `https://portal.h-dcn.nl` — the h-dcn event portal.
 *
 * The allowed-origin editor is SEEDED with these when a tenant has authored no origins yet, so the
 * admin starts from the known-good targets instead of a blank list (they remain fully editable —
 * an origin can be removed, and the server re-validates the shape authoritatively, task 5.1). An
 * origin here is the ORIGIN only (scheme + host [+ port]); the path is never matched (R5.2c).
 */
export const CONFIRMED_EMBED_ORIGINS: readonly string[] = [
  'https://sites.google.com',
  'https://portal.h-dcn.nl',
];

/**
 * The PATH the public application form is served under, UNDER the tenant's landing-page host
 * (`<slug>.jabaki.nl/apply`). The landing page itself owns `/` on that host, so the form lives
 * at a dedicated path — the CloudFront `*.jabaki.nl` rewrite already resolves this non-file path
 * to the slug's SPA `index.html`, which now mounts the application-form route.
 */
export const APPLICATION_FORM_PATH = '/apply';

/** The flat panel state the form-shell UI binds to. */
export interface ShellFormValues {
  /**
   * The resolved FORM slug (spec 12 R4 — the form's OWN public slug on `config#fields`, falling
   * back to the landing slug for an older build). `null`/absent = no public address yet (R4.4).
   */
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
 * Derive the public application-FORM URL (E4/R5.1): the tenant's landing-page host PLUS the
 * dedicated {@link APPLICATION_FORM_PATH} (`<slug>.jabaki.nl/apply`). This is what the builder's
 * preview iframe + the copy-ready embed snippet point at — the landing page owns `/`, the form
 * owns `/apply`. Returns `null` when no slug exists (no public address yet).
 */
export function deriveApplicationFormUrl(slug: string | null | undefined): string | null {
  const base = derivePublicUrl(slug);
  return base ? `${base}${APPLICATION_FORM_PATH}` : null;
}

/**
 * A stable DOM id the generated snippet puts on the `<iframe>` so the paired resize listener can
 * find exactly THIS iframe (and not resize some other frame on a busy host page).
 */
export const IFRAME_EMBED_ELEMENT_ID = 'myadmin-application-form-iframe';

/**
 * The initial fallback height (px) of the embedded iframe BEFORE the first `postMessage` height
 * arrives — also the no-JS fixed-height fallback for hosts where parent JS is not allowed. Tall
 * enough that a typical form is usable even if the resize handshake never runs.
 */
export const IFRAME_FALLBACK_HEIGHT = 900;

/**
 * Derive the ORIGIN (scheme + host [+ port]) of the hosted form from its public URL. The resize
 * listener pins `event.origin` to EXACTLY this origin (CWE-346) so it accepts a height message ONLY
 * from the embedded form, never from any other `postMessage` sender on the host page. Returns null
 * when the URL cannot be parsed (then {@link buildIframeSnippet} emits the plain, no-JS iframe).
 */
export function deriveFrameOrigin(publicUrl: string | null): string | null {
  if (!publicUrl) return null;
  try {
    return new URL(publicUrl).origin;
  } catch {
    return null;
  }
}

/**
 * Build the parent-side resize-listener `<script>` that pairs with the hosted form's height
 * broadcast ({@link import('../../public/application/iframeResize')}). It is ORIGIN-SCOPED and
 * SHAPE-VALIDATED (secure-postMessage practice, CWE-346):
 *  - it accepts a message ONLY when `event.origin === <frameOrigin>` (the hosted form's own
 *    origin) — never a wildcard, so no other sender on the host page can drive the resize;
 *  - it accepts ONLY a message whose `type`/`source` match the form's tokens and whose `height` is
 *    a finite non-negative number — ignoring the ocean of unrelated postMessage traffic;
 *  - it resizes ONLY the specific iframe (`#IFRAME_EMBED_ELEMENT_ID`), nothing else on the page.
 *
 * Returns an empty string when the frame origin is unknown (the snippet then omits the script and
 * relies on the fixed-height fallback).
 */
export function buildIframeResizeListenerScript(frameOrigin: string | null): string {
  if (!frameOrigin) return '';
  // Emit the constants as JSON string literals so the embedded script stays in lockstep with the
  // hosted form's tokens and cannot be broken by a quoting slip.
  const originLit = JSON.stringify(frameOrigin);
  const typeLit = JSON.stringify(IFRAME_RESIZE_MESSAGE_TYPE);
  const sourceLit = JSON.stringify(IFRAME_RESIZE_SOURCE);
  const idLit = JSON.stringify(IFRAME_EMBED_ELEMENT_ID);
  return (
    '<script>\n' +
    '(function () {\n' +
    `  var ORIGIN = ${originLit};\n` +
    '  window.addEventListener("message", function (event) {\n' +
    '    if (event.origin !== ORIGIN) return;\n' +
    '    var data = event.data;\n' +
    `    if (!data || data.type !== ${typeLit} || data.source !== ${sourceLit}) return;\n` +
    '    var h = data.height;\n' +
    '    if (typeof h !== "number" || !isFinite(h) || h < 0) return;\n' +
    `    var frame = document.getElementById(${idLit});\n` +
    '    if (frame) frame.style.height = Math.ceil(h) + "px";\n' +
    '  });\n' +
    '})();\n' +
    '</script>'
  );
}

/**
 * The copy-ready `<iframe>` snippet referencing the public URL (R5.2), now RESPONSIVE (E4b / task
 * 5.4): the hosted form posts its content height, and the snippet carries an origin-scoped listener
 * ({@link buildIframeResizeListenerScript}) that resizes the iframe to fit — so the form is not
 * clipped inside a sandboxed gadget (Google Sites). The iframe starts at {@link
 * IFRAME_FALLBACK_HEIGHT} as the no-JS fixed-height fallback for hosts where parent JS is not
 * allowed; the listener only ever GROWS/shrinks it to the real height when messages flow.
 *
 * Returns an empty string when there is no public URL yet (nothing to embed).
 */
export function buildIframeSnippet(publicUrl: string | null): string {
  if (!publicUrl) return '';
  const iframe =
    `<iframe id="${IFRAME_EMBED_ELEMENT_ID}" src="${publicUrl}" title="Application form" ` +
    `width="100%" height="${IFRAME_FALLBACK_HEIGHT}" style="border:0;width:100%" ` +
    `loading="lazy"></iframe>`;
  const script = buildIframeResizeListenerScript(deriveFrameOrigin(publicUrl));
  return script ? `${iframe}\n${script}` : iframe;
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
 * Resolve the FORM slug the public URL is derived from (spec 12 R4 / Phase 1). The slug is now data
 * on the SAM `config#fields` row (`cfg.slug`) — the form's OWN public address, independent of the
 * tenant's landing-page slug and free to differ from the tenant NAME. Prefer that FORM slug when
 * present; fall back to a caller-supplied slug (the landing slug the builder loaded best-effort —
 * back-compat for an older module build that does not yet serve `config#fields.slug`). A blank/
 * absent value on both yields `null` so the panel states the form has no public address yet (R4.4).
 */
export function deriveFormSlug(
  cfg: FieldConfig | null | undefined,
  fallbackSlug: string | null | undefined,
): string | null {
  const form = (cfg?.slug ?? '').trim();
  if (form) return form;
  return (fallbackSlug ?? '').trim() || null;
}

/**
 * Map the authoritative `GET /members/field-config` `mail_config` body onto the flat form-shell
 * values, flattening the nested `consent_notice`. A missing/absent `mail_config` (older build or
 * a load failure) yields defaults so the panel never blocks authoring. The embed mode is DERIVED:
 * a tenant with ≥1 configured origin is treated as `iframe`, otherwise `standalone`.
 *
 * The public slug is the FORM slug on `config#fields` (spec 12 R4), resolved via
 * {@link deriveFormSlug}: `cfg.slug` wins when present, else the caller-supplied `slug` fallback
 * (the landing slug, back-compat). So once a form authors its own slug the panel shows the FORM's
 * address, not the landing one.
 *
 * The allowed-origin list is SEEDED with the {@link CONFIRMED_EMBED_ORIGINS} when the tenant has
 * authored NO origins yet (R5.2b): the admin starts the iframe editor from the known-good targets
 * rather than a blank list. The seed does NOT flip the mode to `iframe` (standalone stays the
 * default) and {@link toShellMailBody} still OMITS origins while standalone — so a tenant who never
 * enables embedding writes nothing, back-compatible. A tenant WITH stored origins keeps exactly
 * their list (the seed never overrides an authored value).
 */
export function mailConfigToShellValues(
  cfg: FieldConfig | null | undefined,
  slug: string | null | undefined,
): ShellFormValues {
  const next: ShellFormValues = {
    slug: deriveFormSlug(cfg, slug),
    embedMode: 'standalone',
    embedOrigins: [...CONFIRMED_EMBED_ORIGINS],
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
  if (Array.isArray(origins)) {
    const stored = origins.filter((o): o is string => typeof o === 'string' && !!o.trim());
    if (stored.length > 0) {
      // An authored list wins verbatim; its presence derives iframe mode. The seed is only a
      // starting point for a tenant who has authored none.
      next.embedOrigins = stored;
      next.embedMode = 'iframe';
    }
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
