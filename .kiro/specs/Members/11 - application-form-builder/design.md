# Design Document

## Application Form Builder (tenant-admin authoring UI) — Design

- Status: **Draft** (design phase — follows `requirements.md` R1–R9, E1–E6)
- Plane: **Frontend** (tenant-admin UI) + a small **SAM** hardening (`sam/members/`, data account
  `nonprofit-deploy`). **No Flask work** — member config authoring is SAM-owned (Parameter redesign
  spec 02); the Flask `field_overlay` parameter + projection path is retired for authoring.
- Governing steering: `38-sam-module-field-config` (SAM-owned `config#*`, one authoring surface,
  versioned/observable projection), `35-sam-module-architecture-sam` (handler→service→repository
  layering; the public edge is a governed exception, spec 10), `37-shared-building-blocks` (API
  response/error standard v1.0), `33-frontend-testing`, `34-backend-testing`, `40-spec-workflow`.

This design turns the requirements into concrete components and contracts. It **reuses** the existing
SAM write path (`PUT /members/config/{configId}`), the existing frontend config services
(`membersConfigService` / `membersConfigApi` / `overlayModel`), the public form renderer
(`ApplicationFormRenderer`, spec 10), and the SAM `field_formats` registry — adding a focused
authoring view and a small validation step, not parallel machinery.

---

## 1. Architecture overview

```
Tenant-admin Members TabPanel (TenantAdminDashboard.tsx)
  └─ nested <Tabs>: Field configuration · Membership types · Mail · [NEW] Application form
                                                                        │
                                               ApplicationFormBuilder.tsx (new)
             ┌───────────────────────────┬───────────────────┬───────────────┬──────────────┐
             │ Field list + per-field    │ Form-shell panel  │ Readiness     │ Live preview  │
             │ attribute controls (R2/R3)│ (slug/embed/consent, R5) │ panel (R6) │ (R7)       │
             └───────────┬───────────────┴─────────┬─────────┴───────┬───────┴──────┬────────┘
                         │ working field_overlay   │ config#mail body │ readiness    │ public
                         │ (overlayModel helpers)   │                  │ signal       │ field-config
                         ▼                          ▼                  ▼              ▼
          saveMembersParameter('field_overlay')  writeConfig('mail')  getFieldConfig  preview read
                         │                          │                  (config_status) (R7 OQ1)
                         ▼                          ▼
          PUT /members/config/fields          PUT /members/config/mail      (SAM Members API,
                         │                          │                        VITE_MEMBERS_API_BASE_URL,
                         ▼                          ▼                        Bearer, members:admin)
             ConfigWriteService._validate_fields_body (+ R8 app-attr validation)
             ConfigWriteService._validate_mail_body   (+ R8 consent validation)
                         │
                         ▼
             MembersConfigWriteRepository.put_config → governance_projection (config#fields / config#mail)
                         │
                         ▼
             SAM read: projection_config_reader / FieldResolver → ApplicationService.get_public_field_config
                         │
                         └──► public form (spec 10) renders the authored config, unchanged
```

**Key property:** the builder is a focused *view* over data the Field-configuration and Mail editors
already own. It commits the SAME `config#fields` and `config#mail` objects through the SAME two SAM
writes. One row, one authoring surface per row (steering 38 rule 5) — the builder just exposes the
application slice.

---

## 2. Data model (unchanged rows; the builder authors existing attributes)

No new rows, no new store. The builder authors attributes that ALREADY exist on two SAM-owned rows.

### 2.1 `config#fields` — per-field application attributes (already pass-through)
The `field_overlay` object the frontend commits:
```
field_overlay = {
  functional_groups: [ { key, label_nl?, label_en?, order? }, … ],
  fields:          { [fieldKey]:   FieldDef },   // tenant-added variable fields
  fixed_overrides: { [dottedKey]:  FieldDef },   // overrides of platform base fields (alias of `overrides`)
}
FieldDef += {
  application_visible?:  boolean,            // R2/R3 — on the public form?
  application_required?: boolean,            // R3.1 — required ON the form (tighten only)
  application_choices?:  string[] | null,    // R3.2 — enum subset; null/absent = full set
  format?: { checker: string, params?: object } | null,  // R3.3 — platform-known token
}
```
- `ConfigWriteService._validate_fields_body` already carries each `FieldDef` **verbatim** into the
  stored row (it shape-checks containers, not leaves), so these four keys already persist today.
- `projection_config_reader` already READS all four onto `OverlayField`/`FixedFieldOverride`/
  `ResolvedField`; `ApplicationService.get_public_field_config` already filters by them. Read side is
  done (spec 10). This spec adds the **author** of these keys (frontend) + **validation** of them on
  write (R8).

### 2.2 `config#mail` — form-shell mail settings (already authorable)
`ConfigWriteService._validate_mail_body` ALREADY accepts and shapes:
- `application_scope_copy: bool` (R5.4; spec 10 D9a) — fail-closed, only explicit `true` opens it.
- `mail_reply_to_default: str` (R5.4) — optional; omitted when blank.
- `consent_notice: { version: str, text: { <locale>: str } }` (R5.3; spec 10 D26) — shaped via
  `_shape_consent_notice`, projected only when well-formed (non-blank version + ≥1 non-blank locale).
So authoring the consent notice + scope-copy is a frontend write to the SAME `config#mail` body; the
server side exists. R8.2 only hardens the **error surfacing** when a notice is malformed-but-intended.

### 2.3 Slug / embed (form shell — RESOLVED S1/S3)
- The public form is CloudFront-hosted at a predictable name (e.g.
  `tenant-member-application.jabaki.nl`), overridable with a tenant private URL — same pattern as the
  landing pages (`infrastructure/landing-pages.tf`: S3 + CloudFront + the URL-rewrite function + the
  `myadmin-domain-slug-mapping` KVS). The builder READS/derives + DISPLAYS this public URL; it does
  not author the underlying slug (E4 — slug stays with the Landing Page editor).
- The embed **allowed origin(s)** are authored as `application_embed_origins: string[]` on
  `config#mail` via `PUT /members/config/mail`. This ONE list feeds TWO distinct enforcement points
  (they are NOT the same mechanism):
  - **`frame-ancestors`** — a `Content-Security-Policy` response header on the CloudFront-hosted FORM,
    controlling who may `<iframe>` it. Set at the edge via a `viewer-response` CloudFront function
    that looks up the tenant's origins (reusing the existing KVS pattern).
  - **CORS `Access-Control-Allow-Origin`** — on the SAM public API (spec 10 D27), controlling whose
    JS context may call the public field-config / submit endpoints.
  The admin SPA stays on GitHub Pages — this does not require an SPA hosting migration (§9.1).

---

## 3. Frontend components (the bulk of the work)

New components under `frontend/src/components/TenantAdmin/MembersConfig/` (co-located with the
existing editor; exported from the barrel `index.ts`):

| Component | Responsibility |
| --- | --- |
| `ApplicationFormBuilder.tsx` | The sub-tab root. Loads the resolved field config + `config#mail`; owns ONE working `field_overlay` copy; lays out the four panels; commits via `saveMembersParameter`/`writeConfig`. |
| `ApplicationFieldList.tsx` | R2 — the grouped, ordered field list with the on-the-form toggle per row; drives selection into the working overlay via `overlayModel.upsertField`. |
| `ApplicationFieldAttributes.tsx` | R3/R4 — for a selected on-the-form field: application-required toggle (disabled when platform-required), the enum **subset picker** (reuses `EnumOptionsEditor` constrained to the field's own choices), the **format** dropdown (fed by the SAM known tokens). |
| `ApplicationFormShellPanel.tsx` | R5 — public URL display (derived from slug), embed-mode chooser + iframe snippet + allowed-origin input, and the bilingual **consent-notice** editor (versioned). |
| `ApplicationReadinessPanel.tsx` | R6 — certified-sender / slug / ≥1-field summary; neutral "not available" guidance; link to sender verification. |
| `ApplicationFormPreview.tsx` | R7 — renders the public form via the spec-10 `ApplicationFormRenderer` over the public field-config read (OQ1). |

**Integration point:** in `TenantAdminDashboard.tsx`, inside the `hasMembers` TabPanel's nested
`<Tabs>`, add a fourth `<Tab>` ("Aanmeldformulier" / "Application form", `data-testid=
"members-admin-application-form-tab"`) and a matching `<TabPanel>` rendering
`<ApplicationFormBuilder tenant={currentTenant} />`.

### 3.1 The one-object/one-save contract (steering 38 rule 5)
The builder reuses `overlayModel`'s pure helpers (`findField`/`upsertField`/`createField`) exactly as
`MembersFieldModal` does: every attribute toggle transforms the one working `field_overlay` object;
the builder commits it once via `saveMembersParameter('field_overlay', overlay)` →
`writeFieldConfig` → `PUT /members/config/fields`. No per-field network calls. `config#mail` edits
likewise commit once via `writeConfig('mail', body)` (the Mail editor's existing path).

`overlayModel.OverlayField` must gain the four optional attribute keys in its type (it already carries
`[k: string]: MembersConfigValue | undefined` so values pass through verbatim; the explicit typing is
for authoring ergonomics + tests).

---

## 4. Frontend service + data contracts (reused)

- **Load field list:** `getMembersFieldConfig()` / `getFieldConfig()` → `GET /members/field-config`
  (SAM). Returns the resolved field set + `config_status`. The builder reads each field's current
  four application attributes from this to seed the controls.
- **Load mail config:** the Mail editor's existing `config#mail` read (`membersConfigApi`) for
  `application_scope_copy` / `mail_reply_to_default` / `consent_notice` current values.
- **Known format tokens (R3.3):** the SAM `field_formats` registry (`EMAIL`, `IBAN` today) must be
  reachable to the builder. Options:
  - (a) ship a small static list in the frontend mirroring the registry (simplest; risks drift), or
  - (b) serve the token list from the module — e.g. include it in the `GET /members/field-config`
    response metadata or a tiny `GET /members/field-formats`. **Recommendation: (b)** so the dropdown
    is always in lockstep with the platform registry. Design pins the exact carrier in tasks.
- **Save field overlay:** `saveMembersParameter('field_overlay', overlay)` → `writeFieldConfig` →
  `PUT /members/config/fields`. Authoritative; returns the new row version; no projection wait.
- **Save mail config:** `writeConfig('mail', body)` → `PUT /members/config/mail`.
- **Preview (R7 — RESOLVED S1/S2):** an `<iframe>` pointed at the CloudFront-hosted public form URL.
  No new read route; the preview reflects the LIVE (last-saved) config. The builder reloads the
  iframe after a save ("save to update preview").

---

## 5. SAM write-path validation (R8) — the only backend change

Extend `sam/members/domain/config_write_service.py`:

### 5.1 `config#fields` application-attribute validation (R8.1)
Add a per-field validation pass invoked from `_validate_fields_body` (over both `fields` and
`overrides` specs). For each field spec carrying any application attribute:
1. **subset ⊆ choices (R8.1a):** when `application_choices` is present it must be a list whose every
   entry is a valid choice of the field's own resolved choices (`options[].value` / `choices`). A
   subset on a field with no choices, or an entry not in choices, → `ConfigWriteValidationError`.
2. **known checker (R8.1b):** when `format` is present it must be a mapping `{checker, params?}` whose
   `checker` is in the SAM registry's `known_tokens()` (`field_formats.known_tokens()`). Else reject.
3. **no relax (R8.1c):** a field the platform marks `required` may not carry
   `application_required = false`. The platform-required set is the module's existing authority
   (the resolver's required-fixed keys); reject a relax.

This is the SAM equivalent of the retired Flask `members_config_validation._validate_application_attrs`
(R8.4) — same three rules, now enforced by the authoritative author. Errors are collected and returned
in the standard config-write error envelope (R8.3), keyed to the offending field.

### 5.2 `config#mail` consent validation (R8.2)
`_validate_mail_body` already shapes `consent_notice` and **omits** it when malformed. R8.2 changes
this to: when the body **intends** a consent notice (a `consent_notice` key is present and non-empty)
but it is malformed (blank version, or no non-blank locale text), REJECT with a clear
`ConfigWriteValidationError` rather than silently omitting — so an admin's broken notice surfaces
instead of vanishing. A truly absent notice (key omitted) still writes nothing (back-compatible).

### 5.3 No new route, no new capability
Both validations hang off the EXISTING `PUT /members/config/{configId}` path (`members:admin`-gated,
tenant from the token). No route, capability, or template change for the validation itself. The embed
allowed-origins carrier (§2.3/OQ3) may add a `config#mail` attribute + a public-API template read —
pinned in Phase 0 / §7.

---

## 6. Readiness + preview behavior

- **Readiness (R6):** reuse the public edge's send-ready signal (spec 10 `application_readiness
  .is_send_ready`): certified sender (`mail_certified` + `mail_domain`) AND a resolvable slug. The
  panel computes it from the loaded `config#mail` + slug presence; it SHALL NOT re-derive mail
  internals into the UI beyond the boolean states (no domain leak in any public-facing string).
- **Preview (R7 — RESOLVED S1/S2):** an `<iframe>` to the CloudFront-hosted public form. Because it IS
  the real form, the preview and the live form are the SAME code path by construction (no separate
  renderer wiring). A not-send-ready tenant's hosted form shows the neutral 409 "not available" state
  (R7.3). The preview reflects last-saved config; the builder reloads the iframe after each save.

---

## 7. Governance / definition-of-done

- This spec changes NO steering by itself, but it CORRECTS a stale assumption: spec 10's D18 ("Flask
  authors + projects the application attributes") is superseded — authoring is SAM-owned. Add a short
  note to spec 10's `findings.md` (or a cross-link) recording that the authoring counterpart is spec
  11 and targets the SAM write path. If `38-sam-module-field-config.md`'s "Related" line still implies
  Flask writes `config#*`, fix that stale line in the same change (it is already noted stale).
- If the embed allowed-origin is added as a `config#mail` attribute + a public-API CORS read (§2.3),
  that touches `sam/members/template.yaml` (the spec-10 public API, D27) and is part of this spec's
  Phase for the form shell — codified deploy via `deploy-sam-members.yml` (steering 43), not hand-typed.
- End-user docs: extend the tenant-admin docs with "configure your application form" (the builder) as
  a companion to spec 10's applicant + staff-review docs.

---

## 8. Correctness properties

1. **One authoring surface per row (steering 38 rule 5):** the builder and the Field-configuration
   editor both author `config#fields`; the builder and the Mail editor both author `config#mail` —
   via the SAME single writes. No parallel write path, no second store.
2. **Server authoritative (R8):** the SAM write rejects an incoherent application config fail-loud;
   the UI's disabling of a relax/invalid-subset is convenience, never the only guard.
3. **No boundary mix / no Flask revival:** all authoring + reads are SAM; the retired Flask projection
   is not touched or revived.
4. **Preview parity:** the preview renders through the public renderer over the real public contract,
   so what the admin previews is what an applicant gets (zero drift).
5. **Tenant isolation:** every read/write is `members:admin`-gated with the tenant from the verified
   JWT; the builder never addresses another tenant's config.

---

## 9. Resolved design decisions (were Phase-0 spikes; user-answered 2026-10-21)

All five are now DECIDED from the spec-10 findings answers; none blocks the architecture.

- **S1 (OQ1) — RESOLVED: preview = the CloudFront-hosted public form, in an iframe.** The
  application form is hosted on CloudFront at a predictable name (e.g.
  `tenant-member-application.jabaki.nl`), overridable with a tenant's private URL (same pattern as the
  landing pages, `infrastructure/landing-pages.tf`). The builder's live preview is simply an
  `<iframe>` pointed at that hosted URL — NO new authenticated preview route. The preview therefore
  shows the LIVE (last-saved) `config#fields`, which dovetails with S2. → R7.
- **S2 (OQ2) — RESOLVED: preview is last-saved; save-then-preview.** The builder does NOT mirror the
  server's `get_public_field_config` filter client-side. The admin edits, SAVES (the one
  `config#fields` write), and the preview iframe reloads the hosted form to reflect it. In TEST,
  applications land in test SAM and are trivially deletable; in PROD a Tenant_Admin editing their own
  form is expected. The builder shows a clear "save to update preview" affordance. → R7.4.
- **S3 (OQ3) — RESOLVED: host the form on CloudFront; embed control is `frame-ancestors`, not CORS.**
  The "allowed embedding origin" is enforced by a **Content-Security-Policy `frame-ancestors`**
  response header on the CloudFront-hosted FORM (who may put the form in an `<iframe>`) — distinct
  from CORS, which governs whose JS may CALL the SAM public API. One tenant-authored list,
  `application_embed_origins: string[]`, authored onto `config#mail` via `PUT /members/config/mail`,
  feeds BOTH: (a) the CloudFront form response `frame-ancestors`, and (b) the SAM public API
  `Access-Control-Allow-Origin`. Dynamic per-tenant `frame-ancestors` at the edge reuses the EXISTING
  CloudFront KVS pattern (`myadmin-domain-slug-mapping`) + a `viewer-response` function. This does NOT
  require migrating the admin SPA off GitHub Pages (see §9.1). → R5.2.
- **S4 (R3.3 carrier) — RESOLVED: serve `known_tokens()` from the module.** The format dropdown is fed
  by the SAM `field_formats.known_tokens()` set, exposed in the `GET /members/field-config` response
  metadata (or a tiny `GET /members/field-formats`) so the dropdown never drifts from the platform
  registry. → R3.3.
- **S5 (OQ4) — RESOLVED: ONE Reply-To for all (v1); Mail sub-tab owns `config#mail`.** There is no
  requirement forcing per-scope Reply-To. The spec-10 "Reply-To = the notified admin set" (D8/D24) is
  simplified: the tenant's standard `config#mail` sender story — certified From, anonymous/noreply
  sender, and a single populated `mail_reply_to_default` — is the v1 model. `application_scope_copy`
  stays an optional CC toggle that does NOT change Reply-To. All three live on the EXISTING Mail
  sub-tab (one authoring home for `config#mail`, steering 38 rule 5); the builder only
  DISPLAYS/references them in its readiness panel. Per-scope Reply-To is a future additive
  enhancement, not v1. → R5.4.

### 9.1 Out-of-scope note — admin SPA on GitHub Pages vs CloudFront
The admin SPA + docs are hosted on GitHub Pages (`petergeers.github.io/myAdmin/`); the public
landing pages (and now the application form) are on CloudFront. The embed concern (S3) is about the
PUBLIC FORM only (CloudFront) — it does NOT require moving the admin SPA. Migrating the SPA to
CloudFront has independent merit (custom CSP/HSTS headers, one hosting model, no `github.io`
redirect-URL quirks in Cognito, a hosted TEST frontend which does not exist today), but it is a
SEPARATE infrastructure decision with its own migration (ACM cert, OAC, deploy pipeline swap from
`deploy-pages` to S3 + invalidation, Cognito callback updates). It is explicitly NOT coupled to this
spec; capture it as its own ADR/spec if pursued.

---

## 10. Insertion points (seams this builds on)

| New piece | File(s) | Add / modify | Mirror / precedent |
| --- | --- | --- | --- |
| Builder sub-tab | `frontend/.../TenantAdmin/TenantAdminDashboard.tsx` | Add a 4th `<Tab>`/`<TabPanel>` in the Members nested `<Tabs>` | the existing Field-config / Membership-types / Mail sub-tabs |
| Builder components | new `frontend/.../MembersConfig/ApplicationFormBuilder.tsx` (+ the 5 sub-components); barrel `index.ts` | New authoring view over the working overlay + config#mail | `MembersConfigEditor` + `MembersFieldModal` + `MembersMailConfigEditor` |
| Overlay typing | `frontend/.../MembersConfig/overlayModel.ts` | Add the 4 optional app-attr keys to `OverlayField`; helpers unchanged (verbatim pass-through) | the existing `scope`/`choices` keys |
| Field-list + attrs | reuse `overlayModel.upsertField`, `EnumOptionsEditor` | Author the 4 attrs into the one overlay | `MembersFieldModal`'s `buildField`/`handleSave` |
| Preview | `<iframe>` → the CloudFront-hosted public form URL (S1) | Embed the real hosted form read-only; reload after save | the landing-page CloudFront hosting (`infrastructure/landing-pages.tf`) |
| Embed `frame-ancestors` | `infrastructure/*.tf` (form CloudFront dist + a `viewer-response` function) + the KVS pattern | Set per-tenant CSP `frame-ancestors` from `application_embed_origins` | the `myadmin-domain-slug-mapping` KVS + `public_pages_url_rewrite` function |
| Known tokens read | SAM `sam/members/domain/field_formats.py::known_tokens` + a carrier (S4) | Expose the token set to the builder | `get_field_config` metadata |
| App-attr write validation | `sam/members/domain/config_write_service.py` (`_validate_fields_body` + a new per-field app-attr check) | Reject subset⊄choices / unknown checker / relax | retired Flask `members_config_validation._validate_application_attrs` |
| Consent validation | `sam/members/domain/config_write_service.py` (`_validate_mail_body` / `_shape_consent_notice`) | Reject a malformed-but-intended notice instead of omitting | the existing shaper |
| Embed origins (S3) | `sam/members/domain/config_write_service.py` (`_validate_mail_body`); `sam/members/template.yaml` (public API CORS read) | New `application_embed_origins` attr + CORS wiring | the spec-10 public API (D27) |

## 11. Testing strategy

- **Frontend** (`33-frontend-testing`): builder authors the four attrs into the overlay (subset only
  on enum fields; required disabled for platform-required; format dropdown only known tokens);
  one-object/one-save; consent-notice version bumps on change; readiness states; preview consumes the
  real contract; axe over the builder.
- **SAM** (`34-backend-testing`, `sam/tests/`): `ConfigWriteService` rejects subset⊄choices, unknown
  checker, platform-required relax, malformed consent; coherent body writes; defaults still write.
- Paired in the same change (change-with-tests, steering 30/34). No Flask tests (no Flask change).
