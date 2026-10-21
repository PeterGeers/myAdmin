# Implementation Plan — Application Form Builder (tenant-admin authoring UI)

- Status: **Draft** (tasks phase — build gated on user approval of requirements + design).

## Overview

- Follows `requirements.md` (R1–R9, E1–E6) and `design.md` (§3/§5/§10 seams, Phase-0 spikes S1–S5).
- Plane split: most work is **frontend** (`frontend/src/components/TenantAdmin/MembersConfig/`,
  tests per `33-frontend-testing`); a small **SAM** change hardens the write path
  (`sam/members/domain/config_write_service.py`, tests `sam/tests/` via `sam/pytest.ini`) and
  optionally exposes the format-token set + embed-origin CORS. **No Flask work** — config authoring is
  SAM-owned; the Flask projection path is retired and must not be revived.
- Tests are paired INTO each phase (change-with-tests, steering 34/30/33) — not deferred.
- Each task cites the requirement(s)/decision(s) it satisfies and the design seam it builds on.
- Tasks are chunked < 1 day; each phase carries a rough estimate (steering 40).
- Checkbox vocabulary: `[ ]` = not started · `[x]` = done · `❌` = blocked/failed.
- **Governance DoD (steering 40):** Phase 6 corrects the stale spec-10 D18 assumption + updates
  end-user docs in the SAME change; if the embed-origin CORS lands it deploys via the codified
  `deploy-sam-members.yml` pipeline (steering 43), never hand-typed.

---

## Tasks

### Phase 0 — Design spikes — DONE (S1–S5 resolved 2026-10-21, user-answered; design §9)

- [x] 0.1 **S1/S4 — RESOLVED.** Preview = an `<iframe>` to the CloudFront-hosted public form (no new
  route; last-saved state). Format tokens = serve `field_formats.known_tokens()` from the module (in
  `GET /members/field-config` metadata or `GET /members/field-formats`).
- [x] 0.2 **S3 — RESOLVED.** `application_embed_origins: string[]` on `config#mail` (via
  `PUT /members/config/mail`) feeds BOTH the CloudFront form's CSP `frame-ancestors` (a
  `viewer-response` function + the KVS pattern) AND the SAM public API CORS. No admin-SPA hosting
  migration (separate ADR — design §9.1).
- [x] 0.3 **S2/S5 — RESOLVED.** Preview is last-saved (save-then-reload the iframe). ONE Reply-To for
  all in v1; `application_scope_copy` + `mail_reply_to_default` stay on the Mail sub-tab (one
  `config#mail` home); the builder references them.

---

### Phase 1 — SAM write-path validation hardening (R8) — ~1–1.5 days · PARALLEL

- [x] 1.1 `config_write_service.py` — add a per-field application-attribute validator invoked from
  `_validate_fields_body` over BOTH `fields` and `overrides` specs: subset ⊆ the field's own choices
  (R8.1a); `format.checker ∈ field_formats.known_tokens()` and `format` well-formed `{checker,params?}`
  (R8.1b); `application_required=false` cannot relax a platform-required field (R8.1c). Collect +
  raise `ConfigWriteValidationError` keyed to the field (R8.3). Mirror the retired Flask
  `_validate_application_attrs` rules (R8.4).
- [x] 1.2 `config_write_service.py` — `_validate_mail_body`: when a `consent_notice` is PRESENT but
  malformed (blank version / no non-blank locale text) REJECT with a clear error instead of silently
  omitting (R8.2); a truly absent notice still writes nothing (back-compatible).
- [x] 1.3 (If S4 = serve tokens) expose `field_formats.known_tokens()` to the frontend — add it to the
  `GET /members/field-config` response metadata (or a tiny `GET /members/field-formats`). (Depends 0.1.)
- [x] 1.4 Tests (`sam/tests/`): reject subset⊄choices, unknown checker, malformed `format`,
  platform-required relax, malformed-but-intended consent notice — each with the standard envelope +
  stable code; a coherent `config#fields`/`config#mail` body still writes; an un-authored tenant
  writes back-compatible defaults (R9.2).

### Phase 2 — Builder scaffold + field list (R1, R2) — ~2 days

- [x] 2.1 `ApplicationFormBuilder.tsx` — the sub-tab root: load the resolved field config
  (`getMembersFieldConfig`) + `config#mail`; hold ONE working `field_overlay` copy; lay out the four
  panel slots; wire the single commit (`saveMembersParameter('field_overlay', …)`). (R1.3, §3.1.)
- [x] 2.2 Wire the sub-tab into `TenantAdminDashboard.tsx`: a 4th `<Tab>`/`<TabPanel>` in the Members
  nested `<Tabs>` (`data-testid="members-admin-application-form-tab"`), under `hasMembers`, bilingual
  label (R1.1/R1.4).
- [x] 2.3 `ApplicationFieldList.tsx` — render the resolved fields grouped by `functional_group`,
  ordered `(group.order, field.order, key)`; per-row on-the-form toggle writing `application_visible`
  via `overlayModel.upsertField`; membership-admin fields default off but toggleable; calculated/
  non-authorable fields not offerable (R2.1–R2.5). Add the 4 optional attr keys to
  `overlayModel.OverlayField`'s type.
- [x] 2.4 Tests (`frontend/`): list renders grouped/ordered from a fixture field-config; toggling sets
  `application_visible` in the one overlay; a calculated field is not offerable; one-object/one-save
  preserved (R9.1).

### Phase 3 — Per-field attributes + form-shell panel (R3, R4, R5) — ~2–3 days

- [x] 3.1 `ApplicationFieldAttributes.tsx` — for a selected on-the-form field: application-required
  toggle (disabled/forced for a platform-required field, R3.1); enum **subset picker** reusing
  `EnumOptionsEditor` constrained to the field's own choices → `application_choices` (R3.2/R4.1);
  **format** dropdown fed by the known tokens (0.1/1.3) → `format` (R3.3). All gated on
  `application_visible`; seed from current values (R3.4). Writes into the one overlay (R3.5).
- [x] 3.2 `ApplicationFormShellPanel.tsx` — display the derived public URL (CloudFront-hosted form,
  e.g. `tenant-member-application.jabaki.nl`; "no address yet" + link to Landing Page editor when
  absent, E4/R5.1); embed-mode chooser (standalone/iframe) + copy-ready `<iframe>` snippet +
  allowed-origin input → `application_embed_origins` on `config#mail` (R5.2); bilingual versioned
  **consent-notice** editor → `consent_notice {version, text{nl,en}}` on `config#mail`, bumping the
  version on change (R5.3).
- [x] 3.3 Membership-type coherence (R4): when the membership-type field is exposed, surface it as
  application-required with a non-empty subset over the live catalog; prevent an empty subset on an
  exposed-required membership-type field (R4.2); validate subset values against the catalog (R4.3).
- [x] 3.4 Commit the form-shell mail settings through the existing `writeConfig('mail', body)` — ONE
  `config#mail` object (R5.5); reference (not duplicate) `application_scope_copy` / `mail_reply_to_
  default` per 0.3 (R5.4).
- [x] 3.5 Tests (`frontend/`): required disabled for platform-required; subset only on enum fields +
  rejects a non-choice; format offers only known tokens + clears to null; consent version bumps on
  edit; embed snippet matches the public URL; all four attrs land on the right overlay entry (R9.1).

### Phase 4 — Readiness panel + live preview (R6, R7) — ~2 days

- [x] 4.1 `ApplicationReadinessPanel.tsx` — certified-sender / slug / ≥1-field-on-form summary using
  the spec-10 send-ready signal; neutral "not available" guidance (no mail-config leak) + link to
  sender verification (R6.1–R6.3).
- [x] 4.2 `ApplicationFormPreview.tsx` — an `<iframe>` to the CloudFront-hosted public form URL (S1);
  the hosted form itself shows the neutral 409 "not available" state when not send-ready (R7.1–R7.3);
  a "save to update preview" affordance reloads the iframe after a save (last-saved state, R7.4).
- [x] 4.3 Tests (`frontend/`): readiness reflects certified/slug/field states; preview renders the
  filtered schema through the shared renderer; not-send-ready → neutral state, not a half form (R9.1).

### Phase 5 — Embed-origin enforcement: CloudFront `frame-ancestors` + SAM CORS (R5.2) — ~1–1.5 days

- [x] 5.1 `config_write_service._validate_mail_body` — accept/shape `application_embed_origins` (list
  of non-blank origin strings); reject malformed. One tenant-authored list, two consumers (5.2/5.3).
- [x] 5.2 **CloudFront `frame-ancestors`** — host the application form on the landing-page CloudFront
  pattern (`infrastructure/*.tf`); add a `viewer-response` CloudFront function that sets
  `Content-Security-Policy: frame-ancestors <tenant origins>` from `application_embed_origins`, looked
  up via the existing KVS pattern (`myadmin-domain-slug-mapping` precedent). Standalone (no origins)
  omits the header / `frame-ancestors 'none'`.
- [x] 5.3 **SAM public API CORS** — the spec-10 public API (`sam/members/template.yaml`, D27) sets
  `Access-Control-Allow-Origin` from the same `application_embed_origins`. Deploy via
  `deploy-sam-members.yml` (steering 43).
- [x] 5.4 Tests: malformed origins rejected (`sam/tests/`); the public API reflects the allowed origin
  in CORS headers; the CloudFront function emits the expected `frame-ancestors` for a configured
  tenant and omits/denies for an unconfigured one.

### Phase 6 — Accessibility, docs, governance (R-NFR, steering 38/40/43) — ~1 day

- [x] 6.1 Accessibility pass over the builder (Chakra `FormControl` label/aria wiring, keyboard
  operreadiness, focus, nl/en `lang`); axe gate in the frontend tests (R9.1 / NFR).
- [x] 6.2 **Governance:** correct the stale spec-10 D18 assumption — add a note to
  `.kiro/specs/Members/10 - application-app/findings.md` (or a cross-link) that the authoring
  counterpart is spec 11 and targets the SAM write path; fix the stale "Flask writes config#*" line in
  `38-sam-module-field-config.md` "Related" if still present (same change).
- [x] 6.3 **Docs:** extend the tenant-admin docs with "Configure your application form" (the builder),
  companion to spec 10's applicant + staff-review docs.
- [x] 6.4 **Quality gates (steering 43):** run the paired frontend + SAM tests for changed files;
  ensure CodeQL + GitGuardian green on the PR. Deploy the SAM change (1.x, optional 5.x) via the
  codified `deploy-sam-members.yml` pipeline; the frontend rides the frontend deploy path.

---

## Task Dependency Graph

Waves execute in order; tasks within a wave may run in parallel.

```json
{
  "waves": [
    { "id": 1, "tasks": ["1.1", "1.2", "1.3", "2.1", "2.2"] },
    { "id": 2, "tasks": ["1.4", "2.3"] },
    { "id": 3, "tasks": ["2.4", "3.1", "3.2", "5.1"] },
    { "id": 4, "tasks": ["3.3", "3.4", "4.1", "5.2", "5.3"] },
    { "id": 5, "tasks": ["3.5", "4.2", "5.4"] },
    { "id": 6, "tasks": ["4.3", "6.1"] },
    { "id": 7, "tasks": ["6.2", "6.3", "6.4"] }
  ]
}
```

(Phase 0 is DONE — spikes S1–S5 resolved — and omitted from the waves.)

Phase-level sequencing (`->` = "must precede"):

```
Phase 1 (SAM hardening) - PARALLEL with the frontend scaffold; 1.3 feeds 3.1 (format tokens)
Phase 2 (scaffold + field list) -> Phase 3 (attributes + shell) -> Phase 4 (readiness + preview)
Phase 5 (embed frame-ancestors + CORS) - after 5.1; 3.2 authors the origins the edge enforces
Phase 6 (a11y, docs, governance) - LAST; closes the DoD
```

Critical path to "an admin can author the application form end to end": **2 -> 3 -> 4**, with **1**
(SAM hardening) landing in parallel so the authoritative author rejects an incoherent body before the
UI relies on it.

## Notes

- **Definition of done:** R1–R9 covered by passing tests (frontend + `sam/tests`); the SAM write
  rejects incoherent application config fail-loud (R8); the stale spec-10 D18 assumption corrected +
  end-user docs written; deployed via the codified pipeline (steering 43). No Flask change, no Flask
  projection revived.
- **Change-with-tests:** every task touching a component/service/validator updates its paired test(s)
  in the SAME change (steering 30/33/34).
- **Reuse, don't reinvent:** the builder authors the SAME `config#fields` / `config#mail` objects as
  the existing Field-configuration / Mail editors, through the SAME SAM writes, and previews through
  the SAME `ApplicationFormRenderer` — one authoring surface per row, one rendering path.
