# Task 4.3 — applicant PII (SEC-9) + stored-XSS (SEC-10) decision record

> **DECISION RECORD for spec 14 Task 4.3** (R5.1/R5.5, R3.2, R10.9, R10.10; design SEC-9 / SEC-10,
> component C2). Records WHERE applicant-PII minimization is enforced, the retention + GDPR
> deletion path for applicant records, and HOW/where stored-XSS neutralization happens — so a
> later reviewer or producer sees the mechanism without re-deriving it. Co-located with the
> task-1.1 / task-2.1 decision records.

## Scope

The public `POST {slug}` submit (`handler/public_app.py` → `ApplicationService.create_application`
→ `MembershipService.create_application` in `domain/_membership_writes_application.py`). Task 4.1
landed the write + SEC-3 (tenant-from-marker); 4.2 landed SEC-2 server-side validation. This task
adds SEC-9 (PII minimization + retention/deletion) and SEC-10 (stored-XSS), REUSING the existing
write path rather than adding a parallel mechanism.

## SEC-9 — applicant PII minimization (VERIFIED, enforced by construction)

**Enforced at:** `MembershipService._application_selected_record(config, body)` in
`domain/_membership_writes_application.py`.

The submit persists ONLY the tenant's DECLARED/published fields — the allowlist from the resolved
field config. The mechanism is the loop itself: `_application_selected_record` iterates
`config.fields` and copies a value off the body ONLY for a field whose `application_visible` is
true. An undeclared / unexpected body key is never looked up, so it **cannot** be persisted —
minimization holds **by construction**, not by a reject list.

This is defense-in-depth WITH task 4.2: SEC-2 validation rejects an unexpected body field before
the write even runs, and even if that gate were bypassed, the field gate here still drops any
undeclared key. No gap to close — VERIFIED and covered by a test (an undeclared body field is not
persisted; see below).

**Tenant scoping:** the record is written under the marker-resolved `tenant_id` — `create_application`
stamps `record["tenant_id"] = tenant_id` (the verify-before-trust tenant from the `_slugs/{slug}`
marker body, SEC-3), and the SAM members store is `tenant_id`-partitioned (steering 39). A forged
body `tenant_id` is stripped and the resolved one stamped, so an applicant record always lands in
the owning tenant's own partition.

## SEC-9 — retention + deletion path (GDPR for EU tenants)

An applicant submission lands as a `status=application` **member record** in the tenant's own
`tenant_id`-partitioned members store. It is therefore governed by the SAME retention and erasure
machinery as any member record — there is no separate applicant store and no new infra is built
for this task.

- **Lawful basis / minimization:** consent is mandatory and recorded server-authoritatively
  (`_stamp_application_consent` — version/timestamp/locale stamped server-side, R12.1); the record
  is minimized to the published fields (above).
- **Deletion / erasure (right to be forgotten):** an application record is erased by the existing
  per-tenant member deletion path — `MembershipService.delete_member(tenant_id, member_id)`
  (`domain/_membership_writes_crud.py`) → `MembersRepository.delete_member(tenant_id, member_id)`
  (`repository/members_repository.py`), a single-partition `DeleteItem` scoped to the owning
  tenant. A staff erasure of an applicant uses this unchanged; no bespoke applicant-deletion code
  is added.
- **Retention:** retention duration is a tenant policy decision (how long un-approved applications
  are kept before purge). This task does not implement an automated purge job — it records that the
  erasure MECHANISM exists and is the deletion path. An automated retention/TTL purge, if a tenant
  requires one, is a follow-up (candidate: a DynamoDB TTL attribute on `status=application` records)
  and is explicitly OUT of scope here; flagged so it is not assumed done.

## SEC-10 — stored-XSS neutralization

**Decision: NEUTRALIZE ON WRITE (encode active content at the trust boundary).**

Design SEC-10 offered three options (store raw + encode on output / sanitize on input / neutralize
on write) and asked to decide + record. Chosen: **HTML-escape applicant free-text at the public
write** — the trust boundary the task names.

**Implemented at:** `MembershipService._neutralize_free_text(field_obj, value)`, applied to every
accepted value inside `_application_selected_record`.

- Reuses the stdlib `html.escape(value, quote=True)` (encodes `& < > " '`) — no new hand-rolled
  sanitizer. (The codebase's existing sanitizers are either output-side and plane-specific: the
  SAM email bodies already `html.escape` on output in `domain/application_messages.py`, and the
  frontend compose path uses DOMPurify in `memberMailHelpers.ts` — neither is the inbound public
  write, so a write-boundary encode is the correct, reused primitive here.)
- **Scope — free-text only, structured data never corrupted:**
  - only `str` values are touched (a typed date / number / bool / list passes through);
  - a closed-vocabulary code field (`membership_type`, a REFERENCE code) is left verbatim;
  - an enum/choice field (value constrained to a published option set) is left verbatim;
  - a valid email / IBAN / ISO date carries no HTML metacharacters, so the escape is a no-op on
    legitimate values; a value that DID carry markup is both neutralized here and rejected by the
    SEC-2 format validator, so no malformed record lands.

**Why on write (not output-only):** several first-party admin panels render values via
`dangerouslySetInnerHTML` (e.g. invoice/report/email-preview components). React auto-escapes text
nodes, but neutralizing at the trust boundary closes the remaining raw-HTML-sink path so a stored
applicant value can never execute in an admin session regardless of which renderer re-displays it.
This complements, never replaces, output-side encoding.

**Trade-off noted:** encoding on write means a value containing `&`/`<` reads back HTML-encoded in
the stored record (e.g. an admin editing it sees `&amp;`). This is acceptable for applicant
free-text on an unauthenticated public intake (safety over round-trip fidelity) and matches the
"neutralize at the trust boundary" directive. If a future requirement needs byte-exact round-trip
of applicant text, the alternative is store-raw + strict output-encoding on every admin sink — a
larger change deferred unless required.

## Tests (change-with-tests, steering 34/39)

Added to the paired test file `sam/tests/test_create_application.py` (the create_application write
path's allocated test), class `TestPiiMinimizationAndXss`:

- SEC-9: an UNDECLARED body field is not persisted (minimization).
- SEC-9: the write is scoped to the passed (marker-resolved) `tenant_id`.
- SEC-10: a `<script>`-bearing free-text value is HTML-neutralized so it cannot execute on
  admin re-display, while legitimate structured fields (email, enum `membership_type`) are
  left verbatim.

The broad submit battery (T4.5) owns the end-to-end `<script>`-neutralised-on-admin-re-display
assertion; this task's tests cover the 4.3 mechanism at the write layer without duplicating 4.5.
