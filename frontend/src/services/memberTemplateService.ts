/**
 * memberTemplateService — authenticated client for the Members mail-template routes
 * (pivot-output-actions R2, design §3 + §5).
 *
 * Thin wrapper over `apiService.authenticated*` that drives the on-plane template store:
 *   - `GET    /members/templates`        — list the tenant's templates (metadata)
 *   - `GET    /members/templates/{id}`   — one template (incl. per-language body HTML)
 *   - `POST   /members/templates`        — create a template
 *   - `PUT    /members/templates/{id}`   — update a template
 *   - `DELETE /members/templates/{id}`   — delete a template
 *   - `POST   /members/templates/{id}/ai-improve` — improve a template with a free model
 *
 * The backend (SAM Members Lambda, task 2.3) answers with the API response & error standard
 * v1.0 (steering 37): success `{ success: true, data }`, error
 * `{ success: false, error, code?, params? }` with the real HTTP status. The caller localizes
 * by the machine `code`; this service never throws for an HTTP error status — it parses a
 * non-2xx response into a typed `{ ok: false, status, error, code }` result so the UI can
 * branch. A genuine network/parse failure still rejects.
 *
 * The route 2.3 is being built concurrently; this client codes strictly against the design §3
 * contract + the task 2.2 `TemplateService._serialize` metadata shape (template_id, name,
 * languages, merge_fields, logo_asset_ref, origin, created_by, created_at, updated_at). The
 * list serializer carries subject + body KEY only; a GET-by-id additionally resolves the body
 * HTML text per language (so the compose picker can seed the body) — this client reads
 * `body_html` when present and otherwise seeds subject-only.
 *
 * NO member PII is ever sent to `ai-improve`: the request carries only the template content +
 * a free-text instruction (R2) — the backend adapter is fail-closed on the model choice.
 *
 * @module services/memberTemplateService
 * @see .kiro/specs/Members/pivot-output-actions (design §3, §5; requirements R2)
 */

// Members templates live on the SAM Members API (NOT Flask), so these calls MUST go through
// membersRequest (which prefixes VITE_MEMBERS_API_BASE_URL) — not the Flask apiService client,
// whose relative paths hit the dev server and return index.html (empty picker bug).
import { membersRequest } from './membersApiService';

/** The base route for the Members template surface (design §3). */
const TEMPLATES_ENDPOINT = '/members/templates';

/** `origin` of a template: a tenant-authored template vs a shipped/prefab one. */
export type TemplateOrigin = 'user' | 'preset';

/**
 * The template `kind` discriminator (labels sub-spec R-L1). `"mail"` is the historical
 * HTML-body template; `"label"` is an address-label template whose content is `lines` (ordered
 * lines of pivot-result field keys). The field is OPTIONAL on the wire: an absent/undefined
 * `kind` means `"mail"`, so every existing mail template keeps working unchanged.
 */
export type TemplateKind = 'mail' | 'label';

/**
 * One language variant of a template as the backend serializes it. The list/metadata shape
 * carries `subject` + the body `s3_body_key` ref; a GET-by-id additionally resolves `body_html`
 * (the actual body text) so the compose picker can seed the editable body. Either may be absent
 * depending on the endpoint, so both are optional on the DTO.
 */
export interface TemplateLanguageDto {
  /** The subject line for this language (always present on a stored variant). */
  subject: string;
  /** The S3 body-object key (metadata ref; present on list + get). */
  s3_body_key?: string;
  /** The resolved body HTML text (present on GET-by-id so the picker can seed the body). */
  body_html?: string;
}

/** A template as returned by the list / get endpoints (metadata; design §2.2 / task 2.2). */
export interface MemberTemplateDto {
  /** The server-chosen opaque id (sort-key id). */
  template_id: string;
  /** The user-authored, non-blank template name (presentation + picker label). */
  name: string;
  /** Per-language variants keyed by language code (e.g. `nl`, `en`). */
  languages: Record<string, TemplateLanguageDto>;
  /** The ordered merge-field keys the body uses (e.g. `["first_name"]`). */
  merge_fields: string[];
  /** Optional reference into the asset/branding system for a header logo. */
  logo_asset_ref: string | null;
  /** `user` (default) or `preset`. */
  origin: TemplateOrigin;
  /**
   * The template kind (labels sub-spec R-L1). OPTIONAL: absent/undefined ⇒ `"mail"` (so an
   * existing mail template, which carries no `kind`, keeps working). `"label"` marks an
   * address-label template whose content is {@link MemberTemplateDto.lines}.
   */
  kind?: TemplateKind;
  /**
   * The LABEL content model (labels sub-spec R-L1), present only for a `kind: "label"`
   * template: an ordered list of lines, each line a list of pivot-result field keys (a
   * multi-key line is space-joined at compose time). Absent/undefined for a mail template.
   */
  lines?: string[][];
  /** The verified Cognito `sub` of the creator (attribution only). */
  created_by: string;
  /** ISO-8601 UTC timestamps stamped by the service. */
  created_at: string;
  updated_at: string;
}

/**
 * One language variant to WRITE on create/update. Carries the subject + the body HTML TEXT
 * (`body_html`) — the backend computes the canonical S3 key and stores the body under it, so
 * the client never deals in keys on write (design §5 / task 2.2 `create_template`).
 */
export interface TemplateLanguageInput {
  subject: string;
  body_html: string;
}

/** The create/update request body (domain fields only; tenant + author come from the token). */
export interface MemberTemplateInput {
  /** The template name (required, non-blank). */
  name: string;
  /**
   * The template kind (labels sub-spec R-L1). OPTIONAL: omit (or `"mail"`) for the historical
   * HTML-body template so existing mail-write callers are unchanged; `"label"` writes an
   * address-label template whose content is {@link MemberTemplateInput.lines}.
   */
  kind?: TemplateKind;
  /**
   * Per-language `{subject, body_html}` variants (at least one usable variant required for a
   * MAIL template). OPTIONAL so a `kind: "label"` template — which has no mail body — can be
   * written without a languages map; a mail write still carries it.
   */
  languages?: Record<string, TemplateLanguageInput>;
  /**
   * The LABEL content model (labels sub-spec R-L1), for a `kind: "label"` write: an ordered
   * list of lines, each line a list of pivot-result field keys. Omit for a mail template.
   */
  lines?: string[][];
  /**
   * Optional explicit merge-field keys. When omitted the backend discovers them from the body
   * `{{ placeholders }}` — so a caller usually leaves this unset.
   */
  merge_fields?: string[];
  /** Optional logo asset reference. */
  logo_asset_ref?: string | null;
}

/** The AI-improve request (R2): template content + a free-text instruction. NO member PII. */
export interface TemplateAiImproveInput {
  /** The language variant to improve (e.g. `nl` / `en`). */
  lang: string;
  /** A free-text instruction, e.g. "make it warmer and shorter". */
  instruction: string;
}

/** The AI-improve result: the improved subject + body for the requested language. */
export interface TemplateAiImproveResult {
  lang: string;
  subject: string;
  body_html: string;
  /** The free model that produced the improvement (audit/telemetry). */
  model_used?: string;
}

/**
 * A parsed service outcome. `ok` is the success discriminator; on failure the backend's machine
 * `code` (API standard v1.0) is surfaced so the UI can localize via `t(code, params)`.
 */
export type TemplateServiceResult<T> =
  | { ok: true; data: T }
  | {
    ok: false;
    status: number;
    error: string;
    code?: string;
    params?: Record<string, unknown>;
  };

/** The envelope the Members Lambda returns (API response & error standard v1.0, steering 37). */
interface ApiEnvelope<T> {
  success?: boolean;
  data?: T;
  error?: string;
  message?: string;
  code?: string;
  params?: Record<string, unknown>;
}

/** Parse a `Response` into a `TemplateServiceResult<T>`, tolerating a missing/invalid body. */
async function parse<T>(res: Response): Promise<TemplateServiceResult<T>> {
  const body = (await res.json().catch(() => ({}))) as ApiEnvelope<T>;

  if (!res.ok || body.success === false) {
    return {
      ok: false,
      status: res.status,
      error: body.error || body.message || `Request failed with status ${res.status}`,
      code: body.code,
      params: body.params,
    };
  }

  // Success: the standard wraps the payload in `data`; tolerate a bare body for resilience.
  const data = (body.data !== undefined ? body.data : (body as unknown)) as T;
  return { ok: true, data };
}

/**
 * List the tenant's templates (metadata only).
 *
 * The success payload is GUARANTEED to be an array: a well-formed response carries
 * `data: MemberTemplateDto[]`, but a malformed/legacy body (an object, `null`, or a
 * missing `data` that `parse` falls back to the whole envelope for) is coerced to `[]`
 * here so callers can safely `.map` without a runtime crash. A failed result is passed
 * through unchanged so the caller can still branch on `ok === false`.
 */
export async function listMemberTemplates(): Promise<
  TemplateServiceResult<MemberTemplateDto[]>
> {
  const res = await membersRequest(TEMPLATES_ENDPOINT, { method: 'GET' });
  const result = await parse<MemberTemplateDto[]>(res);
  if (result.ok && !Array.isArray(result.data)) {
    return { ok: true, data: [] };
  }
  return result;
}

/**
 * Fetch one template by id — this resolves the per-language body HTML (`body_html`) so the
 * compose picker can seed the editable body, not just the subject.
 */
export async function getMemberTemplate(
  templateId: string,
): Promise<TemplateServiceResult<MemberTemplateDto>> {
  const res = await membersRequest(
    `${TEMPLATES_ENDPOINT}/${encodeURIComponent(templateId)}`,
    { method: 'GET' },
  );
  return parse<MemberTemplateDto>(res);
}

/** Create a template. */
export async function createMemberTemplate(
  input: MemberTemplateInput,
): Promise<TemplateServiceResult<MemberTemplateDto>> {
  const res = await membersRequest(TEMPLATES_ENDPOINT, {
    method: 'POST',
    body: JSON.stringify(input),
  });
  return parse<MemberTemplateDto>(res);
}

/** Update an existing template. */
export async function updateMemberTemplate(
  templateId: string,
  input: MemberTemplateInput,
): Promise<TemplateServiceResult<MemberTemplateDto>> {
  const res = await membersRequest(
    `${TEMPLATES_ENDPOINT}/${encodeURIComponent(templateId)}`,
    { method: 'PUT', body: JSON.stringify(input) },
  );
  return parse<MemberTemplateDto>(res);
}

/** Delete a template. */
export async function deleteMemberTemplate(
  templateId: string,
): Promise<TemplateServiceResult<MemberTemplateDto>> {
  const res = await membersRequest(
    `${TEMPLATES_ENDPOINT}/${encodeURIComponent(templateId)}`,
    { method: 'DELETE' },
  );
  return parse<MemberTemplateDto>(res);
}

/**
 * Improve a template language with a free, allow-listed model (R2). The request carries only
 * the template content + instruction — never member data. On an OpenRouter error / a disallowed
 * model the backend fails closed with a machine `code`; the caller keeps the un-improved
 * template (design §9) and surfaces the code — never a crash.
 */
export async function aiImproveMemberTemplate(
  templateId: string,
  input: TemplateAiImproveInput,
): Promise<TemplateServiceResult<TemplateAiImproveResult>> {
  const res = await membersRequest(
    `${TEMPLATES_ENDPOINT}/${encodeURIComponent(templateId)}/ai-improve`,
    { method: 'POST', body: JSON.stringify(input) },
  );
  return parse<TemplateAiImproveResult>(res);
}
