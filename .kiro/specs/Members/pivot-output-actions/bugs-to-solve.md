# Bugs to solve — pivot-output-actions TEST verification

> First-pass TEST verification of the delivery feature, run against the deployed
> `test` stack / local dev SPA, logged in as `webmaster@h-dcn.nl` (tenant `h-dcn`,
> roles: tenant-administrator + members-crud). This is the defect log that must be
> worked before production promotion. **No debugging starts until we agree scope +
> order.** Statuses are kept current as items are handled.

## Status markers
- ✅ **DONE** — fixed/verified, or confirmed not-a-bug (nothing more to do).
- 🟡 **IN PROGRESS** — actively being worked.
- 🔲 **TODO** — agreed to fix, not started.
- ⏸️ **DEFERRED** — real, but out of scope here (own spec / later).
- ⚪ **EXPECTED** — working as designed; a config/action step, not a defect.
- 📤 **FIX PENDING PUSH** — fixed locally, not yet pushed/deployed to `test`.
- 🔎 **DESIGN CONCERN** — not a quick fix; a design/simplification question for its own spec.

## Status tracker (at a glance)
| # | Item | Scope | Marker |
|---|------|-------|--------|
| 1 | Delivery editor white page (SPA crash) | pivot-output-actions | ✅ DONE (merged PR #77, deployed) |
| 2 | "Failed to save the delivery" — 422 mode | pivot-output-actions | ✅ DONE (merged PR #77, deployed) |
| 3 | mail_enabled gate — enable for h-dcn | pivot-output-actions | ✅ DONE (config#mail=true projected; sends confirmed leaving noreply@h-dcn.nl) |
| 4 | PDF-labels `to_fixed` send not fulfilled | pivot-output-actions | 🔲 TODO (synchronous SES attach, ZZP pattern — no queue/S3) |
| 5 | Tenant-admin white page — Vite 504 | environment | ✅ DONE (env, resolved) |
| 6 | Config save — `overlay.region` enum no choices | analytics-config redesign (other) | 🔎 DESIGN CONCERN (parked) |
| 7 | Analytics config over-complication (enum defs) | analytics-config redesign (other) | 🔎 DESIGN CONCERN (parked) |
| 8 | "No analytics config set" — RECURRENT | pivot-output-actions (symptom of #6/#7) | 🔎 DESIGN CONCERN (with #6/#7) |
| 9 | Mail send — WRONG sender (jabaki.nl); plane violation | → mail/ spec | 🔎 OWNED BY mail/ spec (analysis+reqs done) |
| 10 | Sender Addresses — 404/JSON + no overview/de-certify | → mail/ spec + sender-identity mgmt | 🔎 OWNED BY mail/ spec (identity mgmt out-of-scope there) |
| 11 | Parameter Management misplaced inside the SysAdmin-only block (is tenant business) | admin-config redesign (other) | 🔎 DESIGN CONCERN (Track 3) |
| 12 | members params in param table? + mail-flag value (keep/remove) | data-model + #3 fork | 🔎 DESIGN CONCERN (Track 3; gates #3) |
| 13 | Members MAIL — plane violation (send on Flask), wrong sender, no deliver-now, per-tenant sender | mail (own spec) | 🔎 DESIGN CONCERN → `mail/` spec (analysis+requirements done) |
| 14 | Deliver now (to_fixed) dumped the WHOLE raw member table (incl. IBAN) by email — PII leak | pivot-output-actions | 🟡 FRONTEND FIXED (local commit); server /deliver + scheduler path STILL leaky (deferred) |
| 15 | Pivot Views button clutter — group by workflow | pivot-output-actions (UX) | ✅ DONE (local commit: Manage set + More menus, Deliver now confirm) |
| 16 | Address labels sub-spec (R6) — generate/print from a pivot result | pivot-output-actions/labels | ✅ DONE (merged PR #83 backend; frontend local commits) |

> Legend reminder: **Scope** = which feature owns it; items marked "(other)" are NOT
> pivot-output-actions and likely belong in their own bugfix spec.

---

## 1. Delivery editor white page (SPA crash) — FIXED
- **Marker:** 🟢 PUSHED (e09d0417) → PR #77, awaiting merge to `test`.
- **Symptom:** Opening "Bezorging" (the delivery editor) rendered a white page; the whole SPA blanked.
- **Console:** `MemberDeliveryEditor.tsx: Uncaught TypeError: templates.map is not a function`.
- **Where:** Frontend — `MemberDeliveryEditor` template picker.
- **Scope:** pivot-output-actions.
- **Root cause:** `listMemberTemplates` declared `data: MemberTemplateDto[]` but `parse()` never
  guaranteed an array; a malformed success body (object / missing `data` → envelope fallback /
  null) flowed through and `.map` crashed. No error boundary → white page.
- **Fix (committed `e09d0417`):** `listMemberTemplates` coerces a non-array success `data` to `[]`;
  `MemberDeliveryEditor` loader guards with `Array.isArray`. Three regression tests added.
- **Status:** FIXED. Confirmed gone in the browser. (Still needs to be pushed to `test`.)

## 2. "Failed to save the delivery" — 422 mode rejected — FIXED
- **Marker:** 🟢 PUSHED (343f5d4e) → PR #77, awaiting merge to `test`.
- **Symptom:** Saving a delivery on a pivot → toast "Failed to save the delivery".
- **Network:** `PUT /members/analytics-sets/{id}/delivery` → **422**, body
  `{"code":"errors.analyticsset.delivery","detail":"mode must be one of: per_recipient, to_fixed"}`.
- **Where:** Frontend `putAnalyticsSetDelivery` → SAM `set_analytics_set_delivery`.
- **Scope:** pivot-output-actions.
- **Root cause:** The backend reads the PUT body AS the delivery block (`_write_body(request)` →
  `{mode, template_id, attachment, recipients, label_options}`), but the client wrapped it in
  `{ delivery: ... }`, so the server saw `mode=undefined` on the outer object. The paired test had
  codified the same wrong wrapper shape, so it passed CI while the real backend rejected it
  ("green by luck" mismatch, steering 30).
- **Fix (committed):** send the bare block; test asserts the bare block on the wire.
- **Status:** FIXED locally. Confirmed in the browser (delivery saves and reloads). **Not yet pushed to `test`.**

## 3. "Mailing is unavailable — email is not yet enabled for this organization" — EXPECTED (config step pending)
- **Marker:** ⚪ EXPECTED — needs the mail-enable action (#3), not a code fix.
- **Symptom:** On a pivot result, the Mail output action is replaced by this degradation message.
- **Where:** SAM Members edge mail gate (`is_mail_enabled`), surfaced on `fieldConfig.mail_enabled`.
- **Scope:** pivot-output-actions.
- **Classification:** NOT a bug — fail-closed `mail_enabled` gate (R0). No `config#mail` row is
  projected for `h-dcn` yet, so it resolves to `False`.
- **Action required (pre-production + to test the send path):** author `members.mail_enabled = True`
  for `h-dcn` in (Railway) MySQL, bump the tenant `updated_at`, then project via
  `scripts/onboarding/members/_generic/project-config-to-prod.py` (writes `config#mail` into the
  `nonprofit-deploy` `governance_projection`, with the `.env`-strip + STS account guard per backlog).
- **SES caveats:** send from a working `@h-dcn.nl` identity (domain verified; the `noreply@h-dcn.nl`
  identity is FAILED/disabled). Account-level BOUNCE/COMPLAINT suppression is active.
- **Status:** Open — awaiting go-ahead (writes to the real production projection).

- **WHERE THE FLAG IS (confirmed in UI + code):** `members.mail_enabled` is editable ONLY in
  Tenant-Admin → **Advanced tab → Parameter Management**, which is **SysAdmin-only**
  (`frontend/src/components/TenantAdmin/AdvancedTab.tsx` — "Raw data management (SysAdmin only)").
  - `webmaster@h-dcn.nl` (Tenant_Admin, NO SysAdmin) → does NOT see the Advanced tab / the flag.
  - `peter@pgeers.nl` (has SysAdmin) → DOES see Advanced params + the members mail flag. Confirmed.
  - This is by design: a tenant shouldn't self-authorize mass mail; enabling it is a SysAdmin/operator
    action. (Possible UX gap — no tenant-admin request path — noted for later, not a blocker.)
- **TWO-STEP ENABLE PROCEDURE for h-dcn (the per-tenant flag — mind the SELECTED tenant):**
  1. **(SysAdmin UI)** `peter@pgeers.nl` is currently on **GoodwinSolutions** — must FIRST switch the
     current tenant to **h-dcn** (it's in his tenant list), THEN Advanced → Parameter Management →
     `members.mail_enabled` → set **true** → Save. Setting it while GoodwinSolutions is current would
     enable the WRONG tenant.
  2. **(Operator / projection)** saving writes MySQL only; the SAM edge reads the projected
     `config#mail` row, and a param change does NOT auto-bump the projection version (backlog). So
     after Save, RUN THE PROJECTION SYNC for h-dcn (bump tenant `updated_at` + sync) to the real
     `nonprofit-deploy` `governance_projection`. Until then the UI shows "saved" but the edge still
     reads old/false → "Mailing unavailable" persists.
- **Verify after:** the Members edge `is_mail_enabled("h-dcn")` → true; the pivot result offers the
  Mail action instead of the degradation message.

## 4. PDF labels not rendered by the SAM worker (`_build_pdf_labels` shim) — IN-SCOPE BUG FIX
- **Marker:** 🔲 TODO — in-scope bug fix (R6); fill the deliberate worker seam.
- **Symptom:** A delivery with a `pdf_labels` attachment dead-letters; the worker never produces a
  label PDF. (The INTERACTIVE "Generate address labels" pivot action already works frontend-side.)
- **Where:** SAM worker `MailSendWorker._build_pdf_labels` — a deliberate seam that currently
  `raise MailSendPermanent("pdf_labels rendering is not available on the SAM plane yet ...")`.
- **Scope:** pivot-output-actions — IN SCOPE (R6). Correction to earlier framing: this is NOT
  deferred/out-of-scope.
- **What's already DONE (tasks.md 6.1/6.2/6.3, all `[x]`):** the frontend `AddressLabelGenerator`
  + `addressLabelService.generateAddressLabelPdf` interactive action; the shared ONE `label_options`
  model across interactive R6 and R3 `to_fixed` `pdf_labels`.
- **What's MISSING:** the SAM-plane (Python) label-PDF renderer behind `_build_pdf_labels`.
- **Nature:** a BUG FIX (fill the existing seam), NOT a redesign — BUT cross-plane: the existing
  generator is frontend TypeScript, and `backend/src`/`sam/`/frontend do not share code (steering 36
  rule 5). So the fix is a Python Avery-layout PDF generator on the SAM plane, using the existing TS
  `addressLabelService` as the reference spec + the shared `label_options`. Bounded, but real work
  (PDF lib + layout port), not a one-line wire-up.
- **Status:** TODO — in-scope bug fix for this feature (sizing: focused, cross-plane port).

- **SCOPE DECISION (user, 2026) — CORRECTED after design review:**
  - PDF-labels sent as an **email attachment to one or more FIXED external addresses** (`to_fixed`,
    e.g. yourself / a handling agent — NOT addresses from the pivot result) **IS a valid, in-scope
    use case.** It was in the ORIGINAL design (§2.1: `attachment: "csv" | "pdf_labels"`;
    `to_fixed → build attachment once → one job`). Multi-recipient `to_fixed` is already supported
    (the `recipients` list).
  - It is **always INTERACTIVE** (a browser is present when the send is created), so the PDF can be
    generated client-side.
  - **Scheduled (no-browser) PDF labels remain DEFERRED** — CSV covers the scheduled case (worker
    already builds CSV). Large-volume label printing is NOT a requirement.
- **Why it doesn't work today:** the worker's `_build_pdf_labels` is a stub (`raise MailSendPermanent`);
  the PDF renderer was never ported to the SAM plane, while CSV was built.
- **Design for the fix (architecture-consistent, NO Python PDF port):** the frontend already renders
  the PDF (`addressLabelService.generateAddressLabelPdf`). For a `to_fixed` + `pdf_labels` send:
  1. frontend generates the label PDF at send time (browser present),
  2. uploads it to **S3 `myadmin-shared`** (same bucket the design already uses for template
     bodies/logos — precedent exists),
  3. the enqueued `to_fixed` job carries the S3 KEY (not the bytes),
  4. the worker FETCHES the PDF from S3 and attaches it — the worker never renders.
  Keep `_build_pdf_labels` as a loud guard for the deferred no-browser scheduled case.
- **Care point:** design task 6.3 shares ONE `label_options` model between interactive R6 labels and
  the `to_fixed` `pdf_labels` delivery — keep that single model; the S3-handoff just adds a transport.
- **Revised nature:** an S3-handoff WIRING job (frontend upload + job carries key + worker fetch/attach).
  Bigger than "remove pdf_labels", smaller than a Python PDF port. In-scope Track 1.
- **To confirm when implementing:** does the SAM worker's IAM already allow reading `myadmin-shared`?
  (Design lists S3 `myadmin-shared` among worker resources — verify the exact GetObject grant.)

- **FINAL DESIGN (after reading the proven ZZP pattern — DROP the S3 idea):** the platform ALREADY
  has the right mechanism, and it is simple + synchronous. `SESEmailService.send_email_with_attachments`
  (`backend/src/services/ses_email_service.py`) builds a `MIMEMultipart` IN MEMORY, attaches the PDF
  bytes (`MIMEApplication`), and calls `ses.send_raw_email` SYNCHRONOUSLY, returning a real
  `{success, message_id}` / `{success:false, error}`. ZZP invoice mail
  (`invoice_email_service.send_invoice_email(..., attachments=[{filename, content(bytes),
  content_type}])`) just hands PDF bytes to it. **No queue, no S3, no stored PDF** — bytes released
  after send (exactly "no longer needed after send", as the user said).
- **So #4 = follow the ZZP pattern** for an interactive `to_fixed` + `pdf_labels` send: generate the
  label PDF and hand the bytes to a SYNCHRONOUS SES attach-send. No S3 handoff, no Python PDF renderer
  on the worker, no queue for this case.
- **The only remaining design choice (small):** which synchronous path to reuse —
  (a) the existing Flask `send_email_with_attachments`, or (b) a synchronous SES attach-send on the
  SAM side mirroring it. Both are the same MIME+`send_raw_email` shape. Decide by where the interactive
  labels action most cleanly calls (frontend already has the PDF bytes).
- **Supersedes:** the earlier "S3 handoff" and "port a PDF generator to Python" ideas — both were
  over-engineered. The queue exists to rate-pace BULK per_recipient sends, not a single interactive
  one-shot attachment send.

## 5. Tenant-admin page white page — `504 Outdated Optimize Dep` — RESOLVED (environment)
- **Marker:** ✅ DONE — environment, resolved.
- **Symptom:** Tenant-admin page rendered white.
- **Network:** `GET /node_modules/.vite/deps/react-icons_md.js` → **504 Outdated Optimize Dep**.
- **Where:** Local Vite dev server (`localhost:3000`).
- **Scope:** NOT a code issue — stale Vite dependency pre-bundle cache.
- **Fix:** stop dev server → delete `frontend/node_modules/.vite` → restart `npm run dev` → hard reload.
- **Status:** RESOLVED. Not a product defect.

## 6. Config save rejected — `overlay.region` enum has no choices — 🔎 DESIGN CONCERN (parked)
- **Marker:** 🔎 DESIGN CONCERN — part of the analytics-config over-complication (with #7); own spec.
- **Symptom:** Saving member analytics / tenant config → error toast.
- **Network:** `PUT /api/tenant-admin/parameters/694` (localhost:3000, **local Flask backend**) → **400**,
  body `{"error":"invalid members config: overlay.region: an enum variable field must declare
  choices/options","success":false}`.
- **Where:** Flask-plane `members_config_validation` (fail-fast on save).
- **Scope:** **NOT pivot-output-actions** — tenant-admin members field-overlay config (separate feature/spec).
- **Classification:** The validator is behaving CORRECTLY (it refuses an `enum` field with no
  `choices`/`options`). The real question is WHY the choices are absent in the saved payload.
- **Caveat:** This is on the **~2-day-stale local Flask backend**. Step 1 is confirming whether it
  reproduces against the deployed `test` stack / after refreshing local — it may not be a code bug at all.
- **Status:** Open — not yet investigated (held per request). Likely belongs in its own bugfix spec.

## 7. Analytics config over-complication — enum definitions re-asked in the wrong place — 🔎 DESIGN CONCERN (parked)
- **Marker:** 🔎 DESIGN CONCERN — see the shared design note below (with #6); own spec.
- **Symptom (as reported):**
  - the `region` field has ~10 enum values, but the dropdown lets you pick only the **field** `region`,
    not any of its values;
  - "clubblad paper / digital" options are not shown in the dropdown;
  - the `Name` field is missing from the dropdown.
- **Where:** Frontend tenant-admin config editor (likely `MembersFieldFormBody` / the members-config editor).
- **Scope:** **NOT pivot-output-actions** — same tenant-admin members-config feature as #6.
- **Classification:** Unknown — could be an editor rendering/mapping bug, an `h-dcn` stored-config data
  issue, or the stale local backend. Almost certainly the same underlying cause as #6.
- **Status:** Open — not yet investigated (held per request). Likely same bugfix spec as #6.

## 8. "No analytics config set; config-dependent sets are unavailable" — RECURRENT (symptom of #6/#7)
- **Marker:** 🔎 DESIGN CONCERN — recurrent symptom; investigate WITH #6/#7 (Track 3).
- **Symptom:** Opening pivot views showed "No analytics config set; config-dependent sets are
  unavailable."
- **Where:** Frontend analytics surface (designed degradation, R9.5 — a missing/unmapped analytics
  config hides the dependent sets with a bilingual reason, never an error).
- **Scope:** pivot-output-actions (message); underlying config is tenant-admin members-config.
- **Classification (UPDATED — user: this is RECURRENT):** the MESSAGE itself is the designed
  degradation, but it RECURS rather than being a one-off. The pivot DOES work at times, yet this
  message keeps reappearing — i.e. the analytics config intermittently fails to resolve. Strong
  likelihood this is a DOWNSTREAM SYMPTOM of the #6/#7 root cause: when the analytics config save
  fails (#6) or the editor produces an inconsistent config (#7), the analytics surface has no
  resolvable config and shows this. So #8 is evidence that #6/#7 is a real FUNCTIONAL problem, not
  just a UI annoyance.
- **Status:** Reclassified — investigate WITH #6/#7 as part of the config redesign (Track 3). Not a
  separate transient glitch.

## 9. CSV-attachment send: no error, but the email never arrived — OPEN (needs server-side evidence)
- **Marker:** 🔲 TODO — likely resolves once #3 (mail enable) is done; confirm via logs.
- **Symptom:** Tried to send a pivot result as a CSV attachment to self (`to_fixed`). The UI showed
  NO error, but no email arrived (not in inbox, not in spam). "Maybe not really sent."
- **Where:** SAM send path — deliver action → SQS `members-mail-send[-test]` → worker Lambda → SES.
- **Scope:** pivot-output-actions.
- **Why "no error" is expected regardless of outcome:** the deliver action is async fire-and-forget —
  it ENQUEUES the job and returns `202 Accepted` immediately; it does NOT wait for the SES send. So a
  clean UI result means the ENQUEUE succeeded, not that mail was sent. Any send failure surfaces in
  CloudWatch logs / the DLQ, never in the browser.
- **Most likely cause:** `mail_enabled` is still NOT set for h-dcn (#3). Design re-checks the gate
  SERVER-SIDE in the worker regardless of the UI, so the worker should REFUSE the send. i.e. this is
  probably #3 manifesting on the send path, not a silent drop.
- **Other candidates (only logs/queue can disambiguate):**
  1. Worker refused it (mail_enabled gate) — expected.
  2. Enqueued but the worker failed → message sitting in the DLQ.
  3. SES accepted but suppressed the recipient (account-level BOUNCE/COMPLAINT suppression is active).
  4. Genuinely sent, delayed/filtered.
- **Evidence to gather (read-only AWS CLI, when we start debugging):** worker Lambda CloudWatch logs;
  SQS `members-mail-send-test` + its DLQ depth; `aws sesv2 get-account` SentLast24Hours; SES
  suppression check for the recipient address.
- **Open question for triage:** which From/To addresses were used? (A working `@h-dcn.nl` From is
  required; `noreply@h-dcn.nl` identity is FAILED/disabled. Recipient must not be SES-suppressed.)
- **Status:** Open — not yet investigated (held per request). Very likely resolves once #3 is done;
  confirm via worker logs after enabling mail.

## 10. "Could not add sender address" — empty-body JSON parse error — OPEN (likely different feature)
- **Marker:** 🔲 TODO — investigate (other feature).
- **Symptom:** In Tenant-Admin, under the mail settings area, adding an email to **Sender Addresses**
  fails with toast "Could not add sender address" and console/error
  `Failed to execute 'json' on 'Response': Unexpected end of JSON input`.
- **Context:** While looking for where to set the `mail_enabled` flag, two mail-related buttons were
  found — **"Invoice email"** and **"Sender Addresses"**. NOTE: neither of these is the `mail_enabled`
  (SES-certified) tenant flag (#3) — they are a separate invoice/sender-address mail subsystem.
- **Where:** Frontend tenant-admin "Sender Addresses" add action → its Flask route.
- **Scope:** **Likely NOT pivot-output-actions** — invoice/sender-address mail admin (separate feature).
- **Classification:** Real bug (same CLASS as #1/#2): the client called `response.json()` on an EMPTY
  response body (no JSON returned — empty body / 204 / non-JSON error), so parsing threw. The backend
  returned no parseable body for this add action.
- **Network (captured, user "not 100% sure this is the request"):**
  `POST http://localhost:3000/members/sender-identities` → **404 Not Found** (empty body).
- **Root cause (two layers):**
  1. The route does not exist (404) — `POST /members/sender-identities` is not served at
     `localhost:3000`. NOTE the path is `/members/...` (SAM-style) hitting the local dev origin, NOT
     `/api/...` (Flask). This looks like a base-URL / path-routing mismatch (a SAM-style path aimed at
     the local origin, which has no such route) OR an unimplemented/undeployed endpoint.
  2. The client parsed `response.json()` on an EMPTY 404 body → "Unexpected end of JSON input" instead
     of a clean "not found" message (robustness gap, same class as #1/#2).
- **Caveat:** On the local (~2-day-stale) Flask backend — confirm whether it reproduces on refreshed
  local / deployed before treating as a code bug.
- **Status:** Open — not yet investigated (held per request). Needs the Network status; likely its own
  bugfix spec (not this feature).

### 10b. Sender Addresses — UI-text concerns (same mail-admin feature, NOT pivot-output-actions)
- **CORRECTION:** adding a sender address DOES NOT work — the #10 bug (404 on
  `POST /members/sender-identities` → empty-body JSON parse error) is STILL present. The UI lets you
  TYPE multiple addresses, but saving still fails. (Earlier wording "adding works" was wrong.)
- The following are CONCERNS based on the UI text / layout, NOT confirmed working behavior:
  - **No certified/verified-status overview.** The UI shows no list of which sender addresses are
    SES-verified vs pending/failed. (SES itself tracks this: `VerificationStatus`
    SUCCESS/PENDING/FAILED + `SendingEnabled` — e.g. nonprofit-deploy: `h-dcn.nl`=SUCCESS,
    `pjageers@gmail.com`=SUCCESS, `noreply@h-dcn.nl`=FAILED/disabled.)
  - **No de-certify / remove action** visible in the UI.
  - **Architectural question (user) — IMPORTANT:** is SES the SINGLE source of truth (the app
    reads/writes THROUGH to SES identities), or does the app keep its OWN sender-address store that
    can DRIFT from SES? Two-sources-of-truth risk if the latter. To verify when we debug: compare the
    app's sender list against `aws sesv2 list-email-identities` and check whether add/remove call SES
    Create/DeleteEmailIdentity vs a local table.
- **Scope:** NOT pivot-output-actions — invoice/sender-address mail admin (same feature as #10).
- **Status:** #10 add-bug STILL OPEN; 10b items are design/UX concerns. Parked for the mail-admin
  feature's own backlog/spec.

### 10c. Sender Addresses — LOADING also fails (same root as #10)
- **Symptom:** "Failed to load sender addresses" + `Unexpected token '<', "<!DOCTYPE "... is not valid
  JSON`. So the LIST/GET also fails, not just the add (#10).
- **The `<!DOCTYPE` clue:** the server returned an HTML page (a 404 / error page), not JSON; the client
  called `response.json()` on HTML → parse error on the leading `<`. Strengthens the #10 hypothesis:
  a `/members/...` (SAM-style) path hitting `localhost:3000` (dev origin with no such route) gets the
  dev server's HTML fallback → not JSON. Base-URL / routing mismatch for the sender-identities surface.
- **NOT #3:** this is the sender-addresses feature, NOT the `mail_enabled` tenant gate. Different thing.
- **Scope:** mail-admin (same feature as #10). The whole sender-addresses surface (load + add) is
  non-functional via these routes.
- **Status:** Open — same root cause as #10; parked for the mail-admin spec.

## Design note #13 (Track 3) — no single user can set the h-dcn mail flag via the UI (role gap)
Roles resolve PER ACTIVE TENANT. On **h-dcn**, `peter@pgeers.nl` resolves to `SysAdmin` + `Members_CRUD`
but **NOT `Tenant_Admin`** → the h-dcn tenant-admin area returns **Access Denied** (requires Tenant_Admin).
Meanwhile `webmaster@h-dcn.nl` DOES have `Tenant_Admin` on h-dcn but is NOT SysAdmin → cannot see the
SysAdmin-gated **Advanced parameters** editor (note #11). NET: **no single logged-in user can both be on
h-dcn AND see the Advanced parameter editor**, so there is NO working UI path to set `members.mail_enabled`
for h-dcn. (Also: the flag the user DID set via the UI landed on `scope_id='GoodwinSolutions'` — the
current tenant at save time — NOT h-dcn; param row id 731, value 'true'. Harmless but misplaced; clean up
later.)
- **Consequence:** the mail flag for h-dcn MUST be set via the OPERATOR path (direct DB + ProjectionSync),
  not the UI — which is the agreed quick fix. The UI role/gating gap is a Track 3 item (with #11).
- **Do NOT fix the gating now.**

## Design note #12 (Track 3) — do the members params belong in the `parameters` table? + mail-flag value
**User observation:** the `members` namespace shows **4 parameters** (`field_overlay`, `scope_dimensions`,
`view_contexts` = json; `mail_enabled` = boolean) — this matches `parameter_schema.py`. User questions
whether these rich members-config records belong in the generic key/value `parameters` table at all,
and suggests **modelling the members config records as part of the spec/data model** instead of the
param store. (Earlier "23 other are empty/unused" — not re-derived; the point is the members config may
be mis-homed, not the exact count.)
**Mail-flag value question (gates #3):** what is the added value of `mail_enabled`?
- Factual read: it is a per-tenant "cleared to send" interlock — hides the Mail action in the UI
  (`fieldConfig.mail_enabled`) and is re-checked server-side in the worker.
- BUT the HARD gate on sending is SES (production access + verified sender) — enforced by AWS
  regardless of the flag. So `mail_enabled` is belt-and-suspenders + a UX nicety (hide a button that
  would otherwise fail at SES).
- For a single mailing tenant (h-dcn) where SES is already the real gate, the flag may be redundant
  ceremony (and has caused repeated confusion + a projection step). Counter-argument: it lets you turn
  mail off per-tenant without touching SES, and avoids showing a button that errors — a real
  multi-tenant onboarding feature.
- **This is a FORK for #3:** (a) KEEP + enable the flag for h-dcn, or (b) REMOVE the flag + the code
  that reads it (edge, worker, UI, tests, projection) — SES becomes the single gate. Opposite paths.
- **Classification:** DESIGN CONCERN (data model + gate) — Track 3, with #6/#7/#8/#11. The data-model
  move is Track 3; the keep-vs-remove flag decision BLOCKS/REDEFINES #3.
- **Next input needed (read-only):** review design R0 rationale for WHY the flag was introduced, before
  deciding keep-vs-remove. Do NOT change code until decided.

- **EVIDENCE (user) — the 3 json params have TWO editing surfaces (duplication):** `field_overlay`,
  `scope_dimensions`, `view_contexts` appear BOTH in (1) the dedicated **Members tab** typed config
  editor in the tenant administrator AND (2) the **Advanced parameters** raw key/value view — i.e. two
  different doors to the same `members.*` param rows. This strongly supports the phase-evolution
  hypothesis (#12 / the earlier "did the SAM app define these first, then the Flask Members tab +
  pretokengen were layered on later?" question): the raw param rows look like the EARLY mechanism, and
  a purpose-built typed Members editor was added later without retiring the raw surface.
- **Hypothesis to CONFIRM in the Track 3 analysis (read-only, not now):** are both surfaces editing the
  SAME underlying rows? which spec/phase introduced the params vs the typed editor vs the pretokengen
  projection (git/spec history)? If confirmed duplicate, the redesign should pick ONE home (likely the
  typed Members model) and retire the raw-param duplication for `members.*`.
- **Still Track 3** — config-surface archaeology; do NOT fix mid-Track-1.

### HOW THE PROJECTION ACTUALLY WORKS (studied + verified against real data) — resolves the deadlock
Corrects an earlier conflation: **pretokengen is NOT involved in the mail flag.** Two distinct paths:
- **config#* path (the mail flag):** Flask `ParameterService` resolves `members.mail_enabled`
  (user→role→tenant→system→default) → `build_config_mail_row` → `ProjectionSync` writes `config#mail`
  → the Members EDGE Lambda reads it at request time. (`_projection_config_builders.py`.)
- **pretokengen path (ADR 0006):** a Cognito Pre-Token-Generation Lambda reads the projection to stamp
  a `custom:entitlements` (capabilities) claim into the TOKEN at login. About AUTH, not config params.
  Irrelevant to `mail_enabled`.

**Conflict resolution = versioned last-writer-wins, version = the TENANT ROW's revision.**
`_scope_config_version(tenant)` takes the first of `version|updated_at|revision|modified_at` off the
TENANT row (NOT the param's own change). ProjectionSync `_supersedes` writes a `config#*` row only if
its version is newer. Per-param versioning was never built (code comment: "once the trigger task 6.x
threads a param-change revision through"). **This IS the backlog's "written=0 skipped" trap:** changing
a param without bumping the tenant row leaves the version unchanged → sync skips → projection stale.

**VERIFIED against real data (read-only, test_governance_projection, nonprofit-deploy 506221081911):**
h-dcn has ONLY `config#fields`, `config#scope`, `config#views` — all version `2026-10-01T07:08:54`.
There is **NO `config#mail` row**. So the edge reads absent → fail-closed False → "Mailing unavailable"
(correct). The flag set in MySQL has NOT been projected.

**Understood, safe enable procedure for h-dcn (no longer blind):**
1. (done) `members.mail_enabled = true` in params.
2. Bump the h-dcn TENANT row `updated_at` so the version exceeds `2026-10-01T07:08:54`.
3. Run `ProjectionSync` for h-dcn (reads Railway MySQL params, writes `config#mail` + refreshes the
   other config rows at the new version into `nonprofit-deploy` test_governance_projection; use the
   `.env`-strip + STS account guard per backlog / `project-config-to-prod.py`).
4. Verify: `config#mail` row present with `mail_enabled: true` → edge offers the Mail action.

### Config-home architecture fork (CENTRAL Track 3 question) — where should members config live?
Members config (`field_overlay`, `scope_dimensions`, `view_contexts`, `mail_enabled`) is AUTHORED on
Flask and CONSUMED on the SAM plane. Three options for the mechanism:
- **Option A — status quo:** Flask `parameters` table = source of truth → projected to DynamoDB
  `config#*` rows (projection_sync) → SAM edge reads. Works, but is the over-complicated path (manual
  projection, version-bump gotcha, dual editing surfaces #12). Steering-36 compliant.
- **Option B — clean the projection / push via pretokengen:** keep "Flask authors, SAM reads a
  one-directional projection", but make it reliable/first-class (travel through the pretokengen path,
  auto-bump, no stale-projection trap). Removes the operational pain WITHOUT changing the writer model.
  Steering-36 compliant.
- **Option C — manage the parameter INSIDE the SAM plane:** SAM/Members owns its config natively
  (DynamoDB), no Flask param table, no cross-plane projection for members config. One home, one plane.
  **⚠️ CONTRADICTS steering 36** ("MySQL `parameters` is the single source of truth; Flask authors;
  SAM reads a one-directional projection; never two writers"). So C is NOT a refactor — it is a
  STEERING-LEVEL architecture change that requires revisiting steering 36 first.
- **Decision owner:** the Track 3 config-redesign spec. Inputs it must gather: phase/git history (was
  the config defined early in SAM, then Flask tab + pretokengen layered on later?), the duplicate-
  surface confirmation (#12), and a steering-36 review (does it still reflect intent?). The mail-flag
  keep-vs-remove decision rides inside this same redesign.
- **NOT a Track 1 change.** Do not implement A/B/C now.

### What it would take to REMOVE the mail flag (scoping, analysis only)
Full reference map (not an edit). Medium size, cross-plane, with a clean DI seam that helps.
- **SAM:** delete `sam/members/domain/mail_gate.py` (MailGateProvider/StaticMailGateProvider);
  `membership_service.py` (drop `mail_gate_provider` ctor param + default + field);
  `_membership_writes.py` (drop `"mail_enabled"` from field-config payload); `handler/app.py`
  (drop `_MAIL_GATE_PROVIDER` / `_ProjectionMailGateProvider` / override seam);
  `projection_config_reader.py` (drop `is_mail_enabled` + `config#mail` read); worker
  (drop server-side gate re-check if present).
- **Flask:** `parameter_schema.py` (drop `mail_enabled` schema entry);
  `_projection_config_builders.py` (drop `build_config_mail_row` + any validation);
  `projection_sync.py` (drop `config#mail` projection + export).
- **Frontend:** `types/members.ts` (drop `mail_enabled?`); `MemberPivotViews.tsx` (drop the
  `mailEnabled` gate + the `member-pivot-mail-unavailable` notice + `analytics.degradation.mailNotEnabled`
  usage) — Mail action then shows on capability (`members:export`) alone.
- **Tests (largest footprint, update in lockstep per steering 30):** DELETE
  `sam/tests/test_field_config_mail_enabled.py`; remove `is_mail_enabled` cases in
  `test_members_projection_reader.py`; remove the "mail-enabled gate" describe block + the
  `mail_enabled: true` fixture in `MemberPivotViews.test.tsx`; remove `config#mail`/
  `build_config_mail_row` cases in `test_projection_sync.py`.
- **Data:** existing projected `config#mail` rows become dead data (harmless; optional cleanup).
- **Net effect:** SES becomes the SOLE send gate; the Mail action shows on capability alone (a send
  to an SES-unready tenant would fail at SES instead of being pre-hidden). Acceptable for one mailing
  tenant; weaker for multi-tenant onboarding.
- **Size/risk:** MEDIUM (~10 source files + ~5 test files across 3 planes), low-to-medium risk. The
  `MailGateProvider` seam was built to be removable, which eases it. **Still a Track 3 deliberate
  change — NOT a Track 1 hot-fix.**

## Design note #11 (Track 3) — Parameter Management is in the wrong (SysAdmin) block
**User clarification:** there IS a legitimate **SysAdmin function block** — SysAdmin-only functions,
correctly NOT available to tenant administrators (that gating is RIGHT). The issue is narrower:
**Parameter Management / the members mail flag is TENANT business and is misplaced INSIDE that
SysAdmin-only block.** It is tenant-scoped (takes a `tenant` prop, writes `scope:'tenant'`), yet it
sits behind the SysAdmin wall (via the Advanced tab,
`frontend/src/components/TenantAdmin/AdvancedTab.tsx`), so `webmaster@h-dcn.nl` (Tenant_Admin) cannot
reach it while `peter@pgeers.nl` (SysAdmin) can. The SysAdmin BLOCK is fine; the parameter editor just
should NOT live in it — it belongs to the tenant admin.
- **Classification:** DESIGN CONCERN (admin/config surface) — Track 3, same family as #6/#7/#8. NOT a
  Track 1 blocker: for #3 the flag can be set now via the SysAdmin session that CAN see it.
- **Do NOT investigate/fix now** (per the agreed park on config-surface work).

## Design note #14 (Track 3) — address_mapping vs the "address" functional group (analytics field roles)
Labels need slot ROLES (name/street/postcode/city/country/region → field). Today that is a separate
`analytics.address_mapping`; h-dcn's is unset → the "Generate address labels" button is HIDDEN (a
CONFIG gap, not a labels bug — the labels feature is wired + client-side). But a functional group
**address** ALREADY exists (fields personal.street/postal_code/city/country). Redundant: consider
DERIVING the slot roles from the address functional group's canonical field keys (override only when
non-canonical) → removes the per-tenant mapping step. Part of the Analytics field-roles design
concern (#6/#7/#8). NOT part of the mail spec; labels are separate + working.

## Design note (shared root of #6 + #7) — analytics config is over-complicated
**User assessment (2026 TEST verification):** the whole **Members → Analytics** config area in
the Flask tenant-admin feels over-complicated, and #6 + #7 are two faces of ONE root issue.

- **Single source of truth for field/enum definitions is Field Overlay.** Fields (and enum
  choices like `region` = Noord/Zuid/Oost/West, the `clubblad_paper`/`clubblad_digital` flags,
  etc.) are defined in Flask → Tenant Administrator → Members → **Field Overlay**. Those
  definitions are then loaded into SAM Members config records (via the projection / pretokengen
  path). That is the correct, single home.
- **The problem:** the **Analytics** config surface ALSO engages with enumerated-field
  definitions — and its dropdown does NOT properly support selecting enum *values* (you can pick
  the field `region` but not its values; `clubblad` options are absent; the fixed field `Name`
  shows up where it is not expected). So it is re-asking for definitions that already live in
  Field Overlay, with a broken enum UX.
  - #6 (`overlay.region: an enum variable field must declare choices/options`, 400) is the SAVE
    side of this — the analytics config path touching enum definitions it arguably should not.
  - #7 is the EDITOR side — the dropdown mixing fixed + variable fields and not surfacing choices.
- **Preferred direction (user):** a **simple filter mechanism, like the one already working in the
  pivot tables**, instead of re-defining/selecting enum fields in the analytics config. Analytics
  should FILTER on already-defined fields, not re-author their definitions.

**Decision (user, option a):** PARK #6 + #7 as a design concern — do NOT patch here. They are a
separate feature (tenant-admin / analytics config), to be handled as **their own bugfix/redesign
spec**. Not blocking the pivot-output-actions delivery/send work. When taken up, the first step is
an analysis of the current analytics-config editor vs the working pivot-table filter, then a
simplification proposal (no code changes until agreed).

## Way forward (agreed plan, 3 tracks)
User decision on how to tackle the whole list:

**Track 1 — fix the obvious bugs (this spec, pivot-output-actions):**
- #1 delivery white page — FIXED, needs push to `test`.
- #2 delivery save 422 — FIXED, needs push to `test`.
- #3 enable+project `mail_enabled` for h-dcn — the ACTION that unblocks the real send test (#9).
- #4 — PDF-labels `to_fixed` email attachment IS in scope (interactive, 1+ fixed addresses). Fix =
  follow the proven ZZP pattern: generate PDF bytes → SYNCHRONOUS SES attach-send
  (`send_email_with_attachments`, MIME + `send_raw_email`). NO S3, NO queue, NO Python PDF port.
  Scheduled/no-browser PDF labels deferred (CSV covers scheduled).
- #9 CSV send: no mail — confirm it resolves once #3 is done (else chase worker logs).
- #10 sender-address add 404 — a mail-admin bug; fold into track 1 OR its own mail-admin spec (TBD).

**Track 2 — address labels:** user originally suggested a separate spec; on inspection #4 is an
in-scope bug fix (the generator exists frontend-side; only the SAM worker seam is empty). So UNLESS
the cross-plane port proves large, keep #4 in Track 1 rather than a new spec. Revisit if it balloons.

**Track 3 — config redesign (#6 + #7):** NOT a patch. Produce an ANALYSIS VIEW first (current
Members → Analytics config editor vs the working pivot-table filter; what's redundant with Field
Overlay), then a FORMAL redesign SPEC. No code until the analysis is agreed. Own spec.

**Not bugs / no action:** #5 (Vite env, resolved).
**Reclassified:** #8 is RECURRENT and likely a symptom of #6/#7 — folded into Track 3.

**Suggested order:** finish Track 1 fully (push #1/#2 → #3 → verify #9 → #4 → decide #10) before
opening Track 3's analysis, so we are not juggling workstreams. Track 3's analysis can start early
IF #3 turns out to be blocked by the broken config UI (#6) — but #3 can likely be done via the
parameter-store/projection path, bypassing the UI.

## Track 1 progress log
- **[2026-10-09] MAIL moved to its own spec track (DESIGN CONCERN).** The mail issues are no longer
  loose bugs — they are owned by **`.kiro/specs/Members/pivot-output-actions/mail/`**:
  - `analysis.md` — evidence-based findings + decided direction, and
  - `requirements.md` — 8 validated requirements (SAM-plane consolidation, both send modes,
    per-tenant `noreply@<tenant-domain>` sender + Reply-To=user, verification/degradation, audit,
    actionable failure feedback, TEST verification).
  Related bugs-to-solve items are SUBSUMED by this spec: **#9** (mail arrives from wrong sender
  `jabaki.nl`), **#10/#10b/#10c** (Sender Addresses broken), plus two findings logged there — the
  **Flask-plane violation** (interactive send on `/api/members/mail-set`) and the **missing
  `to_fixed` deliver-now trigger**. Key decisions locked in the mail spec: send stays on the SAM
  plane (steering 35 rule 5a); sender model (B) `noreply@<tenant-domain>` with platform fallback,
  Reply-To = the user; mail-domain is a `members.*` param in the SAME `config#mail` row as the flag.
  STILL OPEN (mail/design.md): explicit `mail_domain` vs derive; where the SES-verified truth is
  read; sync-vs-async actionable-feedback model; `per_recipient` interactive route shape.
  Status: analysis + requirements DONE; design.md NOT started.
- **[2026-10-09] ARCHITECTURE RULING (corrects my earlier wrong "use Flask/ZZP" idea).** Steering 35
  rule 5a is explicit: a SAM module's logic/data stays on the SAM plane — React → API Gateway →
  Lambda → DynamoDB; **"reuse CODE across planes if useful; NEVER reuse the other plane's STORAGE"**,
  and a SAM feature must NOT be served via a Flask/MySQL endpoint. So:
  - Members mail MUST send via the **SAM plane** (edge Lambda → service → SQS → worker → SES). Using
    the Flask backend `send_email_with_attachments` for a Members send is a PLANE VIOLATION. My
    earlier ZZP-Flask suggestion is RETRACTED.
  - The React frontend's only role is the TRIGGER (call the SAM edge endpoint) — correct per the
    layering rule; "handle it in the frontend" was never the plan (frontend can't send mail).
  - **Implication for #9 wrong-sender:** the working `per_recipient` mail arrived from `jabaki.nl`
    (the Flask SES fallback). If that send went via the FLASK path, that is itself the plane
    violation AND the cause of the wrong sender. The CORRECT SAM worker path must resolve an
    `@h-dcn.nl` sender. So fixing #9 = ensure Members mail goes through the SAM worker (not Flask),
    with proper SAM-side sender resolution — NOT reuse Flask.
  - **Implication for #9 to_fixed deliver-now:** correctly a SAM-plane gap — wire the React button →
    existing SAM `POST /members/analytics-sets/{set_id}/deliver` → SQS → worker → SES.
  - **To investigate next (read-only):** does the pivot Mail send currently call a FLASK route
    (`/api/members/mail-set`) or a SAM edge route? If Flask, that is the plane-boundary bug behind
    both the wrong sender AND why the SAM worker never ran.
- **[2026-10-09] #9 ROOT CAUSE for `to_fixed`: there is NO interactive "deliver now" action.**
  Confirmed in code + tasks.md:
  - The pivot **Mail button** sends `per_recipient` to DATASET addresses via `POST
    /api/members/mail-set` (works). The ONLY way to send to a FIXED address is to SAVE a
    `to_fixed` delivery block on a set — but **nothing in the UI executes it**.
  - "Execute" merely runs the pivot query (shows results); it does NOT run the stored delivery.
  - The frontend has `putAnalyticsSetDelivery` (save) + schedule fns, but **NO function calls
    `POST /members/analytics-sets/{set_id}/deliver`** (the run-now route). grep for `deliver`
    across `frontend/src` finds only the save/clear/schedule paths.
  - tasks.md Phase 4 (R4 execute-and-deliver) has 4.1 service / 4.2 route+queue / 4.3 worker /
    4.4 DLQ — ALL BACKEND, marked [x]. Unlike Phase 3 (3.4 "Frontend: delivery editor") and
    Phase 5 (5.4 "Frontend: schedule"), **Phase 4 has NO frontend task.** The interactive
    deliver-now trigger was never specced/built.
  - So a saved `to_fixed` delivery can only run via a SCHEDULE (R5), never interactively → the
    SAM worker never fired, queues stayed empty, nothing arrived. NOT a send failure — a MISSING
    capability.
  - (Also: stray "yes ples" text is appended to the 4.2 line in tasks.md — leftover, clean up.)
  - **Decision needed:** is interactive "deliver now" for `to_fixed` REQUIRED for prod? If yes it is
    an in-scope FEATURE ADD (wire a UI action → the existing `/deliver` route → SQS → worker). If
    scheduled-only is acceptable, document that `to_fixed` runs via a schedule, not a button.
- **[2026-10-09] #9 PARTIAL: mail ARRIVES but from the WRONG sender.** After #3 (flag on), a pivot
  mail to a dataset address DID arrive — BUT `From: support@jabaki.nl` (the SES FALLBACK sender),
  not an h-dcn (`@h-dcn.nl`) address. Signals:
  - The mail keychain works end to end (enqueue → SES → delivered). ✅
  - Sender resolution FAILED → fell back to the jabaki.nl default. For h-dcn the From MUST be an
    h-dcn verified identity (the `h-dcn.nl` domain IS SES-verified).
  - The worker Lambda STILL never ran (no log group, empty queues) → the working mail went via the
    FLASK synchronous path (`ses_email_service`/invoice-style, whose "Uses SES default
    (support@jabaki.nl)" fallback matches), NOT the SAM edge→SQS→worker path. So the DESIGNED SAM
    send pipeline is still UNEXERCISED.
  - **Links #9 ⇄ #10:** the wrong sender is the SAME root as #10 (Sender Addresses broken, 404) —
    h-dcn has no working configured/verified sender, so the send falls back to jabaki.nl. This is a
    PROD-BLOCKER for trust: members would get mail from `support@jabaki.nl`, not their club.
  - **Open:** (a) which send path does the pivot Mail action actually use (Flask vs SAM worker)? (b)
    how is the From resolved and why does it fall back? (c) fix sender config for h-dcn so From =
    `@h-dcn.nl`. Needs #10 resolved.
- **[done 2026-10-09] #3 ENABLED for h-dcn (operator path):** the UI-set flag had landed on
  `scope_id='GoodwinSolutions'` (wrong tenant) — found via local MySQL read. Operator fix:
  (1) set `members.mail_enabled=true` for `scope_id='h-dcn'` in local TEST MySQL (row 734);
  (2) bump `tenants.updated_at` for h-dcn (version guard); (3) ran ProjectionSync →
  `test_governance_projection` (nonprofit-deploy, STS-guarded, re-strip-after-import fix for the
  load_dotenv endpoint clobber). Result: `written=9`, **`config#mail` = {mail_enabled: True}** at
  version `2026-10-09T12:28:16`. VERIFIED in the projection. Awaiting UI re-verify (edge may cache
  per token → hard refresh / re-login).
- **[done] Pushed #1 (e09d0417) + #2 (343f5d4e)** to `docs/members-ledenadministratie-refresh`.
  Both are in **PR #77** → base `test` (OPEN, MERGEABLE). PR also carries the stale-label test fix
  (4b788d68). Title/body updated to list all three.
  - **Deploy reality (steering 43):** #1/#2 are FRONTEND-ONLY (no SAM, no Flask backend).
    There is NO hosted TEST frontend — the TEST frontend IS the local dev server
    (`localhost:3000`, `VITE_APP_ENV=test`). So the fixes are ALREADY effective for TEST
    (local), and merging #77 to `test` triggers NO frontend deploy (`deploy-frontend.yml`
    fires only on push to `main` → GitHub Pages = PRODUCTION SPA).
  - Therefore merging #77 to `test` is just LANDING the commits on `test` (a staging step
    toward the eventual `test → main` promotion), not a deploy. The frontend fixes reach
    PRODUCTION only via the `test → main` merge (the promotion runbook).
  - Next (user decision): merge #77 to `test` to stage it; actual prod effect comes at
    `test → main`.
- **[todo] #3** enable+project `mail_enabled` for h-dcn (writes real projection — confirm first).
- **[todo] #9** re-verify CSV send after #3 (worker logs if still no mail).
- **[todo] #4** PDF-labels `to_fixed` synchronous attach-send (ZZP pattern).
- **[todo] #10** sender-address 404 (decide: fold here or mail-admin spec).

---

## Summary / proposed handling (for agreement — nothing actioned yet)
- **Real pivot-output-actions bugs found by this test:** #1 (fixed), #2 (fixed, unpushed).
- **Expected / not bugs:** #3 (config step pending — an action), #5 (environment, resolved).
- **Recurrent, folded into Track 3:** #8 ('no analytics config' recurs — likely a symptom of #6/#7).
- **In-scope bug fix:** #4 — PDF labels on the SAM worker (fill `_build_pdf_labels`; cross-plane port).
- **Design concern, parked (own spec):** #6 + #7 — ONE root issue: the Members → Analytics config
  is over-complicated and re-asks for enum definitions that belong in Field Overlay; prefer a
  pivot-style filter. See the Design note above. NOT blocking this feature.
- **Required pre-production step regardless:** #3 — enable + project `mail_enabled` for `h-dcn`
  (also unlocks the real send test).
- **New this pass:** #8 (transient 'no analytics config' — pivot works, likely not a defect); #9
  (CSV send: no error but no mail — almost certainly #3 server-side gate; confirm via worker logs).
- **Also found:** #10 (sender-address add → empty-body JSON parse error) — separate mail
  subsystem, NOT the `mail_enabled` flag; likely its own bugfix spec. Need the Network status.

### Open decisions
1. Keep testing and append newly found items to this log before any debugging?
2. Agree #6/#7 are a separate bugfix spec (not blocking this feature)?
3. Push the committed #2 fix (and #1) to `test` now, or hold all pushes until we batch-debug?
4. Enable `mail_enabled` for `h-dcn` now, or after the frontend fixes land?

---

## 14. "Deliver now" (to_fixed) emailed the ENTIRE raw member table incl. IBAN — PII LEAK
- **Marker:** 🟡 FRONTEND FIXED (local commit `c3a9795bc`); server path STILL leaky (deferred by user).
- **Symptom:** Clicking "Deliver now" on a saved set with a `to_fixed` delivery emailed a CSV
  containing EVERY member of the tenant with ALL raw fields (`personal`/`membership`/`overlay`,
  including `iban`, `birth_date`, `sk`, `scope_values`) — NOT the 9 filtered rows / selected
  columns of the open pivot. Confirmed from a received email.
- **Where / root cause (SAM):** the saved-set deliver path `ExecuteAndDeliverService.execute_and_deliver`
  re-fetches `list_members(tenant)` (ALL members) and runs the injected `PivotRunner`, which in
  production is `_PassThroughPivotRunner` (`handler/_dispatch.py`) — it IGNORES the set definition and
  returns the rows unchanged. The worker's `_rows_to_csv_bytes` then serializes the union of ALL raw
  keys (no filter, no column projection, no PII guard). Both the HTTP `/deliver` route and the
  EventBridge scheduler funnel through this same path.
- **Scope:** pivot-output-actions.
- **FIX DONE (frontend, local commit `c3a9795bc`):** "Deliver now" no longer calls the saved-set
  `/deliver` route. It now behaves exactly like "Export CSV → Email" — it sends the CURRENT on-screen
  result rows (`exportRows`, already filtered + projected to the result columns) to the set's stored
  fixed recipients via the proven ad-hoc path (`sendAdHocMail`, `to_fixed` + `attachment:'csv'`). No
  server-side recompute. A confirm dialog was later added (commit `c4dfef2e7`) so the send is never
  fired blind.
- **STILL OPEN (server-side, user chose "leave as-is" for now):** the `/deliver` route + the scheduler
  (`scheduler_app.py` → same `get_execute_and_deliver_service`) still use `_PassThroughPivotRunner`, so
  a DIRECT POST to `/members/analytics-sets/{id}/deliver` (members:export) OR an ACTIVE schedule on a
  `to_fixed` set would still dump the raw table — unattended, in the scheduler's case. One backend fix
  closes both doors: either (a) a real runner that applies the set filter + projects to the result
  columns, or (b) fail-closed refusal of the to_fixed/CSV path until a real runner exists.
- **Status:** Frontend leak CLOSED (local, not pushed). Server path a KNOWN deferred risk — low
  practical exposure while no `to_fixed` set has an active schedule.

## 15. Pivot Views button clutter — regroup by workflow — DONE (local)
- **Marker:** ✅ DONE (local commit `c4dfef2e7`), frontend-only.
- **Symptom:** ~11 buttons visible at once on the Pivot Views panel, grouped by implementation
  history rather than task — confusing.
- **Fix:** per the redesign proposal (`pivot-views-ui-redesign-proposal.md`): a "Manage set" menu
  collapses the six set-management actions; a "More" menu holds All sets + Mail status; Deliver now
  stays in the menu with a confirm dialog. Every gate/testid preserved. 82/82 tests green.
- **Status:** DONE locally; not pushed. Frontend-only; no deploy needed.

## 16. Address labels from a pivot result (R6) — DONE
- **Marker:** ✅ DONE — backend merged (PR #83, deployed to TEST); frontend local commits
  (`121c0a81e`, `ad749558a`, …).
- **Summary:** the `labels/` sub-spec — a label template (`kind:"label"`, ordered lines of result
  field keys) stored in the existing `template#` store; a "Generate labels" action composes the
  current pivot result via `composeLabelLines` (NO analytics.config) onto a chosen Avery format,
  downloadable/printable. Unified template editor (mail + label by `kind`). Emailing the label PDF
  is DEFERRED (see #4).
- **Status:** DONE. Browser end-to-end verification (task 4.1) is the user's to confirm.
