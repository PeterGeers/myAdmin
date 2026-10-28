# Requirements Document

## Introduction

The Support & Feedback module is an in-app surface that lets logged-in users of a tenant
raise a **question** or an **improvement suggestion**, discuss it in a threaded
conversation, attach screenshots, classify it by functional area, track its status, and
search across items. It is built on the **SAM + DynamoDB compute plane**, beside the
existing Members module, and follows the platform's standard SAM layering (API Gateway →
thin Lambda handler → domain service → repository → DynamoDB) with tenant isolation
enforced server-side on the `tenant_id` partition key.

This document covers the **lean first cut** only. Voting/upvotes, email notifications, and
private questions are explicitly deferred (see "Deferred / Future Extensions"); they are
recorded so the later data model can leave room, but they are not built in this cut.

### Grounding — reused SAM-plane patterns (from investigation)

These existing patterns are referenced so requirements stay grounded and the later design
can reuse them. They are context, not new requirements.

- **Layering (steering `35-sam-module-architecture-sam.md`).** A SAM module is a thin
  handler (`sam/members/handler/app.py`) that does `parse → authenticate → tenant context →
  authorize → route → delegate → respond`, a storage-agnostic domain service, and a
  repository that is the only code touching DynamoDB. The Support module mirrors this shape
  as its own module beside Members.
- **Verified-JWT + entitlement edge (`sam/shared/auth_utils.py`).** Claims come only from
  the API-Gateway Cognito authorizer's verified context (or a full RS256 verification
  fallback) — never from a client header. Roles come from `cognito:groups`; per-tenant
  capability is read from the verified `custom:entitlements` claim via `has_capability`
  (three-state: grant / authoritative-deny / "token does not answer → deny or consult
  server"). The Support module adopts this toolkit **once** at its edge.
- **Active-tenant resolution (ADR 0007).** The client sends `X-Tenant`; the edge validates
  it is in the verified entitlement's `tenant_keys` (the header selects among verified
  tenants, it never grants one). The resolved `tenant_id` is the record's only tenant
  source.
- **Tenant isolation (steering `39-backend-data-access-sam-dynamodb.md`).** `tenant_id`
  partition key + IAM `LeadingKeys`; no cross-tenant `scan`; resource name resolves
  fail-fast from an env var with no default; the repository returns a resolved domain view
  and never leaks raw record shape across its boundary.
- **Media/attachments.** The existing media-asset subsystem (`MediaAssetService`,
  `backend/src/services/media_asset/`) lives on the **Flask/MySQL plane**: it is keyed by
  `administration` (not `tenant_id`), stores to S3 via an entity-type registry, and tracks
  upload → register → reference → orphan → delete. Whether the Support module reuses this
  Flask-plane service across planes or introduces its own SAM-plane attachment repository is
  a genuine **open design question** (reuse-vs-new) that this requirements document does not
  decide. Requirements state only the observable attachment behaviour the module must
  provide (Requirement 5); the storage mechanism is a design detail.
- **Permissions.** Permissions follow `{module}_{action}`. This document proposes a
  `support_*` capability set (read / write / answer / manage) as behaviour; the exact claim
  wording and the role→capability mapping are design details.

## Glossary

- **Support_Module**: The SAM-backed Support & Feedback module (API Gateway → Lambda →
  domain service → repository → DynamoDB), deployed beside the Members module.
- **Support_Item** (or **Item**): A single user-raised entry of type `question` or
  `improvement`, owned by a tenant, with a title, body, functional area, status, optional
  attachments, and a thread of answers.
- **Answer**: A threaded reply posted against a Support_Item by a user of the same tenant.
- **Item_Type**: The kind of an item — one of `question` or `improvement`.
- **Functional_Area**: The classification bucket of an item — one of `members`, `banking`,
  `login`, `config`, `invoices`, `tax`, `str`, `sysadmin`, `other`.
- **Item_Status**: The lifecycle state of an item — one of `new`, `in-progress`,
  `answered`, `wont-fix`.
- **Accepted_Answer**: The one Answer marked as resolving the item when it is marked
  `answered`.
- **Author**: The user (verified `sub`) who created a given Support_Item or Answer.
- **Support_Role**: A role carrying elevated support capabilities (support/admin) for a
  tenant, resolved from the verified token — exact role names are a design detail.
- **Attachment**: A screenshot/image associated with an item or an answer.
- **Tenant**: An isolated customer boundary identified by `tenant_id`; h-dcn is the first
  tenant and the module must generalize to any tenant.
- **Verified_Identity**: The caller's `sub` / `email` / `groups` derived only from the
  verified token (`sam/shared/auth_utils.get_verified_identity`).
- **support_read / support_write / support_answer / support_manage**: The proposed
  `support_*` capability set (names illustrative; exact wording is a design detail).

## Requirements

### Requirement 1: Authenticated, tenant-scoped access

**User Story:** As a logged-in user of a tenant, I want the Support module to recognize who
I am and which tenant I am acting in, so that I only ever see and act on my own tenant's
support items.

#### Acceptance Criteria

1. WHEN a request arrives at the Support_Module, THE Support_Module SHALL derive the
   caller's identity and roles only from the verified token (API-Gateway authorizer context
   or a full RS256 verification).
2. IF a request carries no valid verified token, THEN THE Support_Module SHALL reject the
   request with a 401 response and perform no read or write.
3. WHEN a request is authenticated, THE Support_Module SHALL resolve the active tenant from
   the `X-Tenant` selection validated against the verified entitlement's `tenant_keys`.
4. IF the selected tenant is not present in the verified entitlement's `tenant_keys`, OR no
   tenant is selected while the caller is entitled to more than one tenant, THEN THE
   Support_Module SHALL reject the request with a 403 response.
5. THE Support_Module SHALL derive the record's `tenant_id` only from the resolved verified
   tenant and never from the request body or an unverified header.

### Requirement 2: Create a question or improvement item

**User Story:** As a logged-in user, I want to post a question or an improvement
suggestion, so that I can get help or propose a change.

#### Acceptance Criteria

1. WHEN a user with the `support_write` capability submits an item with a non-empty title,
   a non-empty body, and an Item_Type of `question` or `improvement`, THE Support_Module
   SHALL create a Support_Item scoped to the active tenant.
2. WHEN a Support_Item is created, THE Support_Module SHALL record the creating user as the
   Author, set the Item_Status to `new`, and store the creation timestamp.
3. WHEN a Support_Item is created, THE Support_Module SHALL assign the Functional_Area
   supplied by the user, defaulting to `other` when none is supplied.
4. IF an item submission has an empty title, an empty body, or an Item_Type outside
   {`question`, `improvement`}, THEN THE Support_Module SHALL reject the submission with a
   400 response and create no record.
5. IF the caller lacks the `support_write` capability for the active tenant, THEN THE
   Support_Module SHALL reject the submission with a 403 response and create no record.

### Requirement 3: Threaded answers and replies

**User Story:** As a user in a tenant, I want to answer or reply to a support item, so that
anyone in my tenant can help resolve it (not only the item owner).

#### Acceptance Criteria

1. WHEN a user with the `support_answer` capability posts a non-empty Answer against a
   Support_Item in their active tenant, THE Support_Module SHALL append the Answer to that
   item's thread and record the posting user as the Answer Author and the posting timestamp.
2. THE Support_Module SHALL allow any user of the same tenant holding `support_answer` to
   post an Answer, independent of whether that user is the item Author.
3. WHEN a Support_Item's thread is retrieved, THE Support_Module SHALL return its Answers in
   ascending order of their posting timestamp.
4. IF an Answer body is empty, THEN THE Support_Module SHALL reject the Answer with a 400
   response and append nothing to the thread.
5. IF a user attempts to post an Answer to a Support_Item that does not exist in the active
   tenant, THEN THE Support_Module SHALL reject the request with a 404 response.

### Requirement 4: Mark an item answered with an accepted answer

**User Story:** As the item author or a support/admin user, I want to mark an item as
answered and select the accepted answer, so that the resolution is recorded.

#### Acceptance Criteria

1. WHEN the item Author, or a user holding the `support_manage` capability, marks a
   Support_Item as answered and selects one existing Answer in that item's thread, THE
   Support_Module SHALL set the Item_Status to `answered` and record the selected Answer as
   the Accepted_Answer.
2. IF a user who is neither the item Author nor a holder of `support_manage` attempts to
   mark an item answered, THEN THE Support_Module SHALL reject the request with a 403
   response and leave the Item_Status unchanged.
3. IF the selected Accepted_Answer does not belong to the item's thread, THEN THE
   Support_Module SHALL reject the request with a 400 response and leave the Item_Status
   unchanged.
4. WHEN a Support_Item's Item_Status is changed to `answered`, THE Support_Module SHALL
   record the resolving user and the resolution timestamp.

### Requirement 5: Screenshot/image attachments

**User Story:** As a user, I want to attach screenshots to an item or an answer, so that I
can show the problem or the suggested change visually.

#### Acceptance Criteria

1. WHEN a user attaches one or more image files to a Support_Item or an Answer they are
   permitted to create, THE Support_Module SHALL store each Attachment and associate it with
   that item or answer under the active tenant.
2. WHEN a Support_Item or Answer with Attachments is retrieved, THE Support_Module SHALL
   return a reference for each Attachment that the frontend can use to display the image.
3. IF an attached file's type is not an accepted image type, THEN THE Support_Module SHALL
   reject that Attachment with a 400 response and store no file for it.
4. IF an attached file exceeds the configured maximum image size, THEN THE Support_Module
   SHALL reject that Attachment with a 400 response and store no file for it.
5. THE Support_Module SHALL scope every Attachment to the owning item's tenant so an
   Attachment is reachable only within the tenant that owns the item.

> **Open design question (do not resolve in requirements):** whether attachments reuse the
> existing Flask-plane `MediaAssetService` (S3, `administration`-keyed, entity-type
> registry) across the plane boundary, or the Support module introduces its own SAM-plane
> attachment repository keyed by `tenant_id`. Steering `35`/`39` discourages a SAM module
> persisting through another plane's storage endpoint; the design phase decides reuse-vs-new
> and records the trade-off.

### Requirement 6: Classify and regroup by functional area

**User Story:** As a user, I want to classify an item by functional area and change that
classification later, so that items are organized by the part of the app they relate to.

#### Acceptance Criteria

1. THE Support_Module SHALL constrain a Support_Item's Functional_Area to exactly one of
   `members`, `banking`, `login`, `config`, `invoices`, `tax`, `str`, `sysadmin`, `other`.
2. WHEN a user with the `support_write` capability changes the Functional_Area of a
   Support_Item in their active tenant to another allowed value, THE Support_Module SHALL
   update the item's Functional_Area.
3. WHEN items are listed grouped by Functional_Area, THE Support_Module SHALL return each
   Support_Item under its current Functional_Area.
4. IF a Functional_Area value outside the allowed set is supplied, THEN THE Support_Module
   SHALL reject the change with a 400 response and leave the Functional_Area unchanged.

### Requirement 7: Status tracking

**User Story:** As a user or support/admin, I want each item to carry a status, so that I
can see whether it is new, being worked on, answered, or won't be fixed.

#### Acceptance Criteria

1. THE Support_Module SHALL constrain a Support_Item's Item_Status to exactly one of `new`,
   `in-progress`, `answered`, `wont-fix`.
2. WHEN a user holding the `support_manage` capability changes a Support_Item's Item_Status
   to another allowed value, THE Support_Module SHALL update the Item_Status and record the
   changing user and the change timestamp.
3. IF a status change is requested by a user who lacks the required capability to change
   status, THEN THE Support_Module SHALL reject the change with a 403 response and leave the
   Item_Status unchanged.
4. IF an Item_Status value outside the allowed set is supplied, THEN THE Support_Module
   SHALL reject the change with a 400 response and leave the Item_Status unchanged.

### Requirement 8: Search across items

**User Story:** As a user, I want to search support items by text, area, and status, so
that I can quickly find relevant items in my tenant.

#### Acceptance Criteria

1. WHEN a user with the `support_read` capability searches within their active tenant, THE
   Support_Module SHALL return only Support_Items belonging to that tenant.
2. WHEN a search includes a text query, THE Support_Module SHALL return Support_Items whose
   title or body matches the query.
3. WHEN a search includes a Functional_Area filter, THE Support_Module SHALL return only
   Support_Items whose Functional_Area equals the requested value.
4. WHEN a search includes an Item_Status filter, THE Support_Module SHALL return only
   Support_Items whose Item_Status equals the requested value.
5. WHEN a search includes more than one filter, THE Support_Module SHALL return only
   Support_Items that satisfy every supplied filter.

### Requirement 9: Server-enforced tenant isolation

**User Story:** As a tenant, I want every support operation scoped to my tenant on the
server, so that no user can read or change another tenant's support items.

#### Acceptance Criteria

1. THE Support_Module SHALL persist every Support_Item, Answer, and Attachment under the
   resolved `tenant_id` partition key.
2. WHEN the Support_Module reads Support_Items, Answers, or Attachments, THE Support_Module
   SHALL return only records whose `tenant_id` equals the active tenant.
3. IF a user requests a Support_Item, Answer, or Attachment that belongs to a different
   tenant than the active tenant, THEN THE Support_Module SHALL respond as if the record
   does not exist (404) and disclose no cross-tenant data.
4. THE Support_Module SHALL enforce tenant scoping in the repository layer using the
   `tenant_id` partition key, not only in the handler or domain service.
5. THE Support_Module SHALL resolve its DynamoDB table name fail-fast from an environment
   variable with no default.

### Requirement 10: Support capability set

**User Story:** As a platform operator, I want Support capabilities to follow the
`{module}_{action}` convention, so that authorization is consistent with the rest of the
platform.

#### Acceptance Criteria

1. THE Support_Module SHALL authorize reads and searches by a `support_read` capability.
2. THE Support_Module SHALL authorize item creation and functional-area changes by a
   `support_write` capability.
3. THE Support_Module SHALL authorize posting answers by a `support_answer` capability.
4. THE Support_Module SHALL authorize status changes and administrative resolution by a
   `support_manage` capability.
5. THE Support_Module SHALL read each capability only from the caller's verified
   entitlement for the active tenant and SHALL deny the action when the verified token does
   not grant it.

> The exact capability claim wording and the role→capability mapping (for example, which
> Cognito group maps to `support_manage`) are design details, not fixed by this document.

### Requirement 11: Dutch-primary, bilingual user interface

**User Story:** As a Dutch-speaking user of the tenant, I want the Support module's
interface in Dutch, so that I can use it in my own language, while the app's existing
bilingual convention is preserved.

#### Acceptance Criteria

1. THE Support_Module frontend SHALL present all user-facing text (labels, buttons,
   placeholders, status names, functional-area names, validation and toast messages)
   through the application's existing i18next localization layer, with **Dutch (`nl`) as
   the primary/default language** and English (`en`) provided alongside.
2. THE Support_Module SHALL NOT hardcode user-facing strings in a single language in the
   components; every such string SHALL resolve from an i18next resource key (consistent with
   the Members surface convention).
3. WHEN the active UI language is Dutch, THE Support_Module SHALL render every user-facing
   string in Dutch (no English fallback visible for a key that has a Dutch value).
4. WHEN a user-facing string has no value for the active language, THE Support_Module SHALL
   fall back in the order active-locale → `nl` → `en` → the key, so a missing translation
   never renders blank.
5. THE server-side enumerations the UI displays (Item_Type, Item_Status, Functional_Area)
   SHALL remain stable machine values (e.g. `new`, `members`); their Dutch/English display
   labels SHALL be resolved in the frontend i18next layer, not stored as localized text on
   the record.

> Scope note: this requirement governs the **module UI language only**. The spec documents
> themselves (requirements/design/tasks) stay in English by the user's choice; this is not a
> contradiction — it mirrors the rest of the codebase, where code/specs are English and the
> shipped UI is Dutch-primary bilingual.

## Deferred / Future Extensions

The following are **out of scope** for this first cut and are recorded so the data model and
design can leave room ("extend when needed"). They MUST NOT be built as part of this cut.

- **Voting / upvotes** on items or answers (ranking, "most wanted" ordering).
- **Email notifications** on new items, new answers, or status changes (would reuse the
  SAM mail-send queue + worker, best-effort posture).
- **Private questions** (visibility scoping narrower than the whole tenant — e.g. author +
  support role only).

The design SHOULD leave the data model open to these (for example, not precluding a later
`votes` attribute, a notification offload hook, or a per-item visibility field) without
implementing them now.
