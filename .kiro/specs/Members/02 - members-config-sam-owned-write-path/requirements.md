# Requirements Document

## Introduction

This feature introduces a **net-new, SAM-owned write path** for exactly three tenant-level
`governance_projection` rows — `config#fields`, `config#scope`, and `config#mail`. Today every
projection row is authored on the Flask plane: the myAdmin frontend edits MySQL `members.*`
parameters and a one-directional `ProjectionSync` (MySQL → DynamoDB, no back-sync) stamps the
resulting rows onto the projection, which the SAM Members plane reads read-only.

Phase 1 makes DynamoDB `governance_projection` the **system-of-record** for those three
`config#*` rows. The single myAdmin frontend will write them directly to the SAM plane
(API Gateway → Members Lambda edge → config-write domain service → new write repository →
DynamoDB), the corresponding MySQL `members.*` params and the three `ProjectionSync` config
builders are retired, and the existing read reader (`MembersProjectionReader`) keeps serving
the rows unchanged because the written row shape is preserved.

The cutover is **sequenced per record** — one `config#*` row migrates at a time
(`config#fields` → `config#scope` → `config#mail`) using a strict ordered handoff in which SAM
owns the row **before** Flask stops writing it. After Phase 1 the projection table is a
**split-ownership** table: SAM writes `config#fields/scope/mail`; `ProjectionSync` (Flask) still
writes `tenant`, `module#`, `role#`, `scopegrant#`. All writes target `nonprofit-deploy`
(`506221081911`), `eu-west-1`. This spec consumes SAM-plane capabilities defined by
`35-sam-module-architecture-sam.md` rather than redefining them, and honors the Flask-plane
conventions in `30-backend-api-flask-mysql.md` and the CI/CD contract in `43-cicd-deploys.md`.

The authoring model is **one typed door per concern**: after a `members.*` key migrates to SAM,
its single authoring door is a SAM-owned typed function (a new typed Mail function for
`config#mail`; the existing typed field/scope editor for `config#fields` / `config#scope`), and
the Advanced raw parameter editor offers no write path for any `members.*` key. This closes the
two-writers-one-config hazard in which a logical config could be written both from the raw
MySQL editor and from the SAM plane.

The scope is **LOCKED to Phase 1**. `tenant`, `module#<name>`, `role#<email>#<role>`, and
`scopegrant#<email>#<dimension>` remain MySQL-owned / ProjectionSync-written and are deferred to
a later spec. Invoice SES verification (`SenderSettingsTab`) stays on the Flask/SES plane and
must not be touched. Members SES sender-address identities (`MemberSenderIdentitiesTab`) stay on
their existing Flask route and are not part of the SAM `config#mail` write.

## Glossary

- **Governance_Projection**: The DynamoDB table (`governance_projection` in PROD,
  `test_governance_projection` in TEST) holding `config#*`, `tenant`, `module#`, `role#`, and
  `scopegrant#` rows, resolved at runtime via the `GOVERNANCE_PROJECTION_TABLE` environment
  variable.
- **SAM_Write_Path**: The net-new write pipeline on the SAM plane — API Gateway PUT route →
  Members Lambda edge → config-write domain service → `MembersConfigWriteRepository` → DynamoDB.
- **Members_Config_Write_Repository**: The net-new boto3-backed writer
  (`sam/members/repository/projection_config_write_repository.py`) that performs a versioned
  `put_item` on the three SAM-owned `config#*` rows.
- **Members_Projection_Reader**: The existing read-only reader
  (`sam/members/repository/projection_config_reader.py`) that serves `config#fields`,
  `config#scope`, and `config#mail` and is preserved unchanged.
- **Config_Write_Service**: The SAM config-write domain service that validates the request body,
  computes the write stamp, and delegates to Members_Config_Write_Repository.
- **Projection_Sync**: The Flask one-directional MySQL → DynamoDB synchronizer
  (`backend/src/services/projection_sync.py`) whose `config#*` builders are retired per record.
- **Members_Config_Service**: The frontend service (`frontend/src/services/membersConfigService.ts`)
  that saves config, repointed per record from Flask to the SAM_Write_Path.
- **Split_Ownership**: The post-Phase-1 state in which the Governance_Projection table has two
  distinct writers partitioned cleanly by sort-key prefix — SAM writes `config#fields/scope/mail`,
  Projection_Sync writes `tenant`/`module#`/`role#`/`scopegrant#`.
- **Per_Record_Cutover**: The strict ordered handoff by which a single `config#*` row is migrated
  (SAM write path live and read-back verified in PROD, then data migration, then frontend repoint,
  then Projection_Sync builder removal) before the next record begins.
- **Safety_Gate**: The non-negotiable rule that the Projection_Sync builder removal for a record
  is never merged to `main` until the SAM write path for that record is verified live in PROD —
  guaranteeing the row always has exactly one authoritative writer (never zero).
- **Version_Stamp**: The row-level monotonic ISO-8601 write stamp (`VERSION_ATTR`) applied by the
  SAM write path on every `config#*` put. It is an ordering/when-last-written marker only — it does
  not gate what the reader can read and does not encode a config schema or shape version (there is
  no schema/release version system).
- **Consent_Notice_Version**: The domain-level `application_consent_notice.version` carried inside
  the `config#mail` row body, which is kept separate from the Version_Stamp.
- **Config_Views_Residue**: The retired `config#views` sort key — never authored by any writer;
  cleanup is delete-only residue removal.
- **View_Contexts_Residue**: The retired `members.view_contexts` MySQL parameter (named
  column-layout presets for the Members overview). It has no authoring editor and is authored
  nowhere; its per-context `page_size` value was previously re-homed to a single tenant-level
  `default_page_size` scalar on `config#fields`, but `default_page_size` is now itself fully
  retired in favor of the per-user runtime Rows_Per_Page_Selector (Requirement 25) — no tenant
  rows-per-page default is carried on `config#fields` or migrated to SAM. Its physical cleanup is
  delete-only — the MySQL rows are removed via
  `backend/src/migrations/retire_members_view_contexts.py` and any stale `config#views` DynamoDB
  residue via Config_Views_Residue removal.
- **Rows_Per_Page_Selector**: The per-user runtime control on the Members table that chooses how
  many rows a page shows (options 50, 100, 250, 500, and Max), mirroring the FIN Transactions
  rows-per-page dropdown pattern adapted for DynamoDB. The fixed options apply a DynamoDB Query
  `Limit`; Max omits `Limit` so DynamoDB returns one page up to its natural ~1 MB response
  boundary (Max is one Query page, not all rows). It is a per-user runtime choice, not a
  tenant-authored config value. A persisted per-user default MAY supply the selector's initial
  value but is not required; a platform fallback supplies the initial pre-selected option
  otherwise.
- **Cursor_Paging**: The DynamoDB-native prev/next paging model used by the Members table, based
  on the `LastEvaluatedKey` cursor rather than SQL-style offset or jump-to-page. It applies to
  every Rows_Per_Page_Selector option including Max: Next is enabled only when the last query
  returned a `LastEvaluatedKey`, and Prev is enabled only when a previous-page cursor exists.
- **Session_Columns**: The separate, still-live per-user column chooser
  (`frontend/src/components/.../ColumnChooser.tsx` with `getColumnPreferences` /
  `saveColumnPreferences`) that stores a user's chosen columns as a per-user preference. It is
  distinct from View_Contexts_Residue and is neither tenant config nor a `members.*` parameter;
  this feature leaves it unchanged.
- **Tenant_Admin**: The entitlement a caller must hold for the resolved `tenant_id` to write any
  SAM-owned config row.
- **Single_Authoring_Door**: The guarantee that every `members.*` key has exactly one authoring
  surface; after a key migrates to SAM that door is the SAM-owned typed function, and no raw or
  MySQL door remains for it.
- **Typed_Mail_Function**: The net-new dedicated Mail function (one screen under Members Tenant
  Admin) that is the single authoring door for all Members `config#mail` scalars
  (`mail_enabled`, `mail_domain`, `mail_local_part`, `mail_certified`, `mail_reply_to_default`,
  `application_consent_notice`), built with typed Chakra form fields, Formik/Yup validation, and
  bilingual labels per `32-frontend-ui.md` — not a raw JSON grid.
- **Members_Config_Editor**: The existing typed field/scope editor that owns `field_overlay`
  (`config#fields`) and `scope_dimensions` (`config#scope`), repointed to the SAM_Write_Path.
- **Scope_Single_Source**: The resolution of OQ-3 — the per-field `scope` attribute on the
  `config#fields` overlay is the single AUTHORING source for Members scope dimensions, from which
  SAM `config#scope` is derived; SAM `config#scope` is the single authoritative source for scope
  dimensions. There is no silent fallback to a standalone param, so the per-field scope toggle has
  a real, visible effect. The standalone `members.scope_dimensions` param is NOT deleted and NOT
  retired as data; it is kept as the Scope_Dimension_Mirror (a frontend-written derived copy) and
  retired only as an authoring surface.
- **Scope_Dimension_Mirror**: The frontend-written Flask `members.scope_dimensions` derived copy of
  the SAM-authoritative `config#scope` dimensions. SAM `config#scope` is authoritative and written
  first; the frontend then mirrors the same dimension set into `members.scope_dimensions` so Flask's
  grant validators keep reading it unchanged. The mirror is best-effort (eventually-consistent, not
  transactional): SAM is authoritative, and a failed mirror-write leaves Flask's copy stale until a
  surfaced retry succeeds. The mirror is never an independent authoring surface — it is not editable
  in the Advanced_Parameter_Editor and is not authored by Projection_Sync; its only author is the
  frontend scope-save mirror.
- **Scope_Grant_Validation_Reader**: The Flask grant-validation reader
  (`backend/src/services/user_tenant_scope_service.py`) that, before writing a scope grant, checks
  every dimension key and value by canonical-equality against the valid dimensions. It continues to
  read the Scope_Dimension_Mirror (`members.scope_dimensions`) UNCHANGED; moving it to SAM
  (Option D) stays out of scope.
- **Scopegrant_Projection_Builder**: The Flask builder
  (`backend/src/services/_projection_scopegrant.py`) that builds the `scopegrant#` projection rows
  and reads the valid `scope_dimensions`. It continues to read the Scope_Dimension_Mirror
  (`members.scope_dimensions`) UNCHANGED; moving it to SAM (Option D) stays out of scope.
- **Scope_Grant_Reconciliation**: The two-tier obligation that a scope-dimension change on an
  existing tenant never silently orphans `user_tenant_scope` grants. ROUTINE tier (new tenant, add a
  dimension/value — no existing grant orphaned): the frontend mirrors the dimensions to Flask
  automatically and shows the Tenant_Admin a REMINDER that user scope grants may need to be
  created/updated to align with the change (a remark, not an automated grant rewrite). ORPHANING tier
  (rename/remove a dimension or drop a value that would orphan existing grants): the change is
  blocked and the block message instructs the Tenant_Admin to contact the System Administrator to
  align on the change (an interim, message-based escalation — not an automated mechanism — valid
  until the structural solution of moving user-tenant-role-scope to SAM, an Option D item, exists).
  The frontend SHALL NOT auto-rewrite user scope grants — grant creation/update is a human decision.
  Detection is cross-plane: it compares the SAM-authoritative proposed scope dimensions
  (`config#scope` / the per-field `scope` attributes) against the Flask MySQL `user_tenant_scope`
  grants.
- **Advanced_Parameter_Editor**: The raw MySQL parameter editor
  (`frontend/src/components/TenantAdmin/ParameterManagement.tsx`, writing
  `/api/tenant-admin/parameters`) which, after this feature, serves no `members.*` row and offers
  no `members.*` write path.
- **Mail_Certified_Gate**: The required boolean `mail_certified` attribute on the `config#mail`
  row — the fail-closed pre-send SES-certified gate; absent or not `True` blocks sending.
- **Mail_Sender_Composition**: The From address composition `<mail_local_part|noreply>@<mail_domain>`
  resolved from `config#mail` (by the MailSenderResolver). `mail_local_part` is tenant-authored,
  defaults to `noreply`, is tenant-branded, and need not be a real or deliverable inbox. From +
  interactive Reply-To are already implemented (MailSenderResolver plus the Members mail worker);
  this spec adds only the scheduled Reply-To default on `config#mail`.
- **Mail_Reply_To**: The Reply-To selection model for a Members mail send. FOR an INTERACTIVE
  (user-triggered) send, Reply-To is the invoking user's verified email, supplied at runtime by the
  caller — it is NOT a `config#mail` attribute (already implemented). FOR a SCHEDULED/unattended
  send (no triggering user, e.g. an EventBridge scheduler), Reply-To is the tenant-authored
  `config#mail` `mail_reply_to_default`; WHERE `mail_reply_to_default` is absent for a scheduled
  send, the scheduled send has no Reply-To and falls back to the Mail_Sender_Composition From
  address (the fail-safe), so an unattended send always has a defined Reply-To.
- **Member_Sender_Identities**: The Members SES sender-ADDRESS identities dataset
  (`MemberSenderIdentitiesTab` via `memberSenderIdentityService`, Flask
  `/api/members/sender-identities`, `members_sender_identity_routes.py`, `email_verifications`
  keyed by `administration`) — a separate dataset from the `config#mail` scalars that co-locates
  in the Typed_Mail_Function UI but is not part of the SAM `config#mail` write.
- **GOVERNANCE_PROJECTION_TABLE**: The environment variable that selects the projection table
  with no default — a missing/blank value fails fast at the first real DynamoDB call.

## Requirements

### Requirement 1: SAM-owned config write path

**User Story:** As a Tenant Admin, I want my `config#fields`, `config#scope`, and `config#mail`
edits written directly to the SAM plane, so that DynamoDB `governance_projection` is the
authoritative system-of-record for those rows without a projection step.

#### Acceptance Criteria

1. THE SAM_Write_Path SHALL expose a `PUT /members/config/{configId}` route routed through the
   existing Members Lambda edge.
2. WHEN the SAM_Write_Path receives a `PUT /members/config/{configId}` request with a valid body,
   THE Config_Write_Service SHALL persist the row to the Governance_Projection table via the
   Members_Config_Write_Repository.
3. WHEN a `config#*` write completes, THE SAM_Write_Path SHALL return an HTTP 200 response
   containing a success indicator, the written `configId`, and the authoritative Version_Stamp.
4. WHEN the Members_Config_Write_Repository persists a row, THE Members_Config_Write_Repository
   SHALL author the exact attribute shape that the Members_Projection_Reader reads for that
   `configId`, so that the Members_Projection_Reader remains unchanged.
5. FOR ALL `(tenant_id, configId, attributes)` with `configId` in {fields, scope, mail}, after the
   Members_Config_Write_Repository writes the row, the matching Members_Projection_Reader accessor
   SHALL return a value equivalent to the written attributes.
6. THE Members_Config_Write_Repository SHALL use the schema tokens from `services.projection_schema`
   (`CONFIG_ID_FIELDS`, `CONFIG_ID_SCOPE`, `CONFIG_ID_MAIL`, `build_sort_key`, `build_key`,
   `PARTITION_KEY_ATTR`, `SORT_KEY_ATTR`, `VERSION_ATTR`) so that writer and reader cannot drift.

### Requirement 2: Closed config-id write surface (split-ownership guardrail)

**User Story:** As a platform operator, I want the SAM write surface closed to exactly the three
SAM-owned config ids, so that the split-ownership partition between SAM and Projection_Sync stays
clean and no other row type is ever written by SAM.

#### Acceptance Criteria

1. THE Members_Config_Write_Repository SHALL write only sort keys with prefix `config#` whose id is
   in the closed set {fields, scope, mail}.
2. IF a write is requested for a `configId` outside {fields, scope, mail}, THEN THE SAM_Write_Path
   SHALL reject the request at the route with an HTTP 400 or 404 response and perform no write.
3. IF the Members_Config_Write_Repository is called with a `config_id` outside {fields, scope, mail},
   THEN THE Members_Config_Write_Repository SHALL raise a validation error before any `put_item`.
4. THE Members_Config_Write_Repository SHALL NOT author `tenant`, `module#`, `role#`, `scopegrant#`,
   or `config#views` rows.
5. THE SAM_Write_Path SHALL reject the `views` `configId`, so that Config_Views_Residue is never
   authored.

### Requirement 3: Authentication, entitlement, and tenant isolation

**User Story:** As a platform operator, I want every config write authenticated, entitled, and
tenant-scoped at the SAM edge, so that no cross-tenant or unauthorized write is addressable.

#### Acceptance Criteria

1. WHEN the SAM_Write_Path receives a config write request, THE Members Lambda edge SHALL verify
   the bearer Cognito JWT using the `sam/shared` toolkit before any write.
2. THE Members Lambda edge SHALL resolve `tenant_id` from the verified token rather than from the
   request body.
3. IF the caller lacks the Tenant_Admin entitlement for the resolved `tenant_id`, THEN THE Members
   Lambda edge SHALL reject the request with an HTTP 401 or 403 response and the
   Members_Config_Write_Repository SHALL NOT be reached.
4. IF the bearer token is unverified or the tenant does not match, THEN THE Members Lambda edge
   SHALL reject the request with an HTTP 401 or 403 response.
5. IF a write is requested with a blank `tenant_id`, THEN THE Members_Config_Write_Repository SHALL
   raise a validation error before any `put_item`.

### Requirement 4: Scoped IAM write grant

**User Story:** As a platform operator, I want a separate least-privilege IAM write grant for the
config rows, so that an audit can see exactly what the SAM write path may do while the existing
read grant stays intact.

#### Acceptance Criteria

1. THE `sam/members/template.yaml` SHALL add a distinct IAM statement (separate `Sid`) granting
   `dynamodb:PutItem` on the Governance_Projection table for the Members function role.
2. THE existing read-only IAM statement (`MembersReadGovernanceProjection`) SHALL remain unchanged.
3. THE write IAM statement SHALL pin the partition to the caller's tenant using
   `dynamodb:LeadingKeys`.
4. THE application layer (the route check plus the Members_Config_Write_Repository closed-set guard)
   SHALL be the primary enforcement that only `config#{fields,scope,mail}` sort keys are written,
   because no first-class IAM condition key constrains writes by a composite sort-key prefix.
5. THE write IAM statement SHALL request only the `dynamodb:PutItem` action, so that no write verb
   beyond the versioned put is granted.

### Requirement 5: Fail-fast table resolution across TEST and PROD

**User Story:** As a maintainer, I want the SAM write path to resolve its table loudly from a single
environment variable, so that a misconfiguration breaks visibly rather than silently targeting the
wrong environment.

#### Acceptance Criteria

1. THE Members_Config_Write_Repository SHALL resolve the Governance_Projection table via
   `services.projection_schema.get_projection_table_resource()` from the
   `GOVERNANCE_PROJECTION_TABLE` environment variable with no default.
2. IF `GOVERNANCE_PROJECTION_TABLE` is missing or blank, THEN THE Members_Config_Write_Repository
   SHALL raise an error at the first real DynamoDB call rather than using a default table.
3. WHERE the resolved table is `test_governance_projection`, THE SAM_Write_Path SHALL write the
   `config#*` rows against the TEST table.
4. WHERE the resolved table is `governance_projection`, THE SAM_Write_Path SHALL write the
   `config#*` rows against the PROD table.
5. THE Members_Config_Write_Repository SHALL require a non-empty `tenant_id` partition key on every
   write, so that the tenancy boundary is never crossed by a blank key.

### Requirement 6: Monotonic SAM version model

**User Story:** As a maintainer, I want the SAM-owned rows to carry their own monotonic write stamp,
so that writes are authoritative and ordered without porting the retired Flask max-of-params logic.

#### Acceptance Criteria

1. WHEN the SAM_Write_Path writes a `config#*` row, THE Config_Write_Service SHALL stamp the row
   with a monotonic ISO-8601 UTC Version_Stamp.
2. FOR ALL pairs of writes to the same row, a later write SHALL produce a lexicographically-greater
   Version_Stamp than an earlier write.
3. THE SAM_Write_Path SHALL NOT port the Flask max-of-params version logic (`_config_row_version`),
   because it becomes dead code once SAM writes the row atomically.
4. WHEN the SAM_Write_Path re-writes a row with identical attributes and Version_Stamp, THE
   Members_Config_Write_Repository SHALL produce no observable change (idempotent put).
5. THE SAM_Write_Path SHALL keep the row-level Version_Stamp separate from the `config#mail`
   Consent_Notice_Version.
6. THE Version_Stamp SHALL be purely an ordering/when-last-written marker, and THE SAM_Write_Path
   SHALL NOT use the Version_Stamp to gate what the Members_Projection_Reader can read.
7. THE Version_Stamp SHALL NOT encode a config schema or shape version, because the production
   system runs a single reader that interprets only the latest config shape (no schema/release
   version system).
8. WHEN two writes target the same `config#*` row, THE SAM_Write_Path SHALL adopt last-writer-wins
   for Phase 1 and SHALL NOT apply a conditional stale-write guard, so that the Version_Stamp
   remains an ordering marker only.

### Requirement 7: config#fields row authoring (Task 1)

**User Story:** As a Tenant Admin, I want to author the field overlay through the SAM write path,
so that `config#fields` is SAM-owned for its field, override, and functional-group attributes.

#### Acceptance Criteria

1. WHEN the SAM_Write_Path writes `config#fields`, THE Config_Write_Service SHALL author the
   `fields`, `overrides`, and `functional_groups` attributes in the shape the
   Members_Projection_Reader reads via `get_overlay`.
2. THE Config_Write_Service SHALL NOT author a `default_page_size` attribute on the `config#fields`
   row, because the tenant-level `default_page_size` config is retired in favor of the per-user
   runtime Rows_Per_Page_Selector defined in Requirement 25.
3. THE Config_Write_Service SHALL preserve each per-field `scope` attribute verbatim on the
   `config#fields` row, so that `config#scope` can be derived from it.
4. WHEN the SAM_Write_Path writes `config#fields`, THE Members_Projection_Reader SHALL return the
   written overlay unchanged on read-back.

### Requirement 8: config#scope row authoring (Task 2)

**User Story:** As a Tenant Admin, I want to author the scope dimensions through the SAM write path,
so that `config#scope` is SAM-owned and semantically equivalent to the legacy derivation.

#### Acceptance Criteria

1. WHEN the SAM_Write_Path writes `config#scope`, THE Config_Write_Service SHALL author the
   `dimensions` attribute in the `ScopeDimension` shape the Members_Projection_Reader reads via
   `get_scope_config`.
2. WHEN the SAM_Write_Path writes a `config#scope` row with empty `dimensions`, THE
   Members_Projection_Reader SHALL resolve it to a tenant-wide scope configuration.
3. THE per-field `scope` attribute on the `config#fields` overlay SHALL be the single authoring
   source for Members scope dimensions, and THE Config_Write_Service SHALL derive the `config#scope`
   row from those per-field `scope` attributes.
4. THE Config_Write_Service SHALL NOT author the `config#scope` row from a standalone
   `members.scope_dimensions` param, because that param is retired as an authoring surface by
   Requirement 22 and kept only as the frontend-written Scope_Dimension_Mirror.
5. WHEN a Tenant Admin toggles a field's `scope` attribute on the `config#fields` overlay, THE
   derived `config#scope` row SHALL change accordingly, so that the per-field scope toggle has a
   real, visible effect with no silent fallback masking it.
6. WHEN the SAM_Write_Path writes a `config#scope` row derived from an overlay that declares no
   scope dimensions, THE Members_Projection_Reader SHALL resolve it to a tenant-wide scope
   configuration, so that empty dimensions remain valid.
7. THE Config_Write_Service SHALL NOT author `all_wildcard` or `multi_valued` attributes on the
   `config#scope` row.

### Requirement 9: config#mail row authoring (Task 3)

**User Story:** As a Tenant Admin, I want to author the mail gate, sender fields, certification
gate, and consent notice through the SAM write path, so that `config#mail` is SAM-owned with
fail-closed mail behavior.

#### Acceptance Criteria

1. WHEN the SAM_Write_Path writes `config#mail`, THE Config_Write_Service SHALL author the
   `mail_enabled` gate, `mail_domain`, `mail_local_part`, `mail_certified`, `mail_reply_to_default`,
   and `application_consent_notice` in the shape the Members_Projection_Reader reads.
2. IF `mail_enabled` is absent or not explicitly `True`, THEN THE Members_Projection_Reader SHALL
   resolve the mail gate to `False` (fail-closed).
3. IF `mail_domain` is absent, THEN THE Members_Projection_Reader SHALL resolve it to a value that
   refuses sending, because `mail_domain` has no safe default.
4. WHEN the SAM_Write_Path writes `config#mail`, THE Config_Write_Service SHALL author
   `mail_certified` as a boolean on the written row, so that the projected row satisfies the
   projection validator requirement that `config#mail` carry `mail_certified` as a bool.
5. IF `mail_certified` is absent or not explicitly `True`, THEN THE Mail_Certified_Gate SHALL fail
   closed and the pre-send certification gate SHALL refuse sending.
6. THE Config_Write_Service SHALL author the `mail_certified` boolean on the written row even
   though the Members_Projection_Reader exposes no `mail_certified` accessor, so that the projected
   row shape stays valid for the pre-send certification gate.
7. THE Config_Write_Service SHALL author `application_consent_notice` only when it is well-formed
   (a non-blank version plus at least one non-blank locale).
8. THE Config_Write_Service SHALL preserve the domain-level Consent_Notice_Version within the
   `config#mail` row body independently of the row-level Version_Stamp.
9. THE Mail_Sender_Composition From address SHALL be composed as `<mail_local_part|noreply>@<mail_domain>`
   from `config#mail`, where `mail_local_part` is tenant-authored, defaults to `noreply`, is
   tenant-branded, and need not be a deliverable inbox.
10. FOR an INTERACTIVE user-triggered send, THE Mail_Reply_To SHALL be the invoking user's verified
    email supplied at runtime by the caller, and the invoking user's email SHALL NOT be a
    `config#mail` attribute.
11. FOR a SCHEDULED unattended send with no triggering user, THE Mail_Reply_To SHALL be the
    `config#mail` `mail_reply_to_default`.
12. WHEN the SAM_Write_Path writes `config#mail`, THE Config_Write_Service SHALL author
    `mail_reply_to_default` as an optional tenant-authored string in the shape the
    Members_Projection_Reader reads.
13. IF `mail_reply_to_default` is absent for a SCHEDULED unattended send, THEN THE Mail_Reply_To SHALL
    fall back to the Mail_Sender_Composition From address, so that an unattended send always has a
    defined Reply-To.
14. THE Mail_Sender_Composition From address and the interactive Mail_Reply_To SHALL remain as
    already implemented in the MailSenderResolver and the Members mail worker, and THE
    `mail_reply_to_default` scheduled default SHALL be the new `config#mail` attribute this feature
    authors.

### Requirement 10: Per-record migration with read-back verification and safety gate

**User Story:** As a platform operator, I want each record migrated and read-back verified in PROD
before its Flask builder is removed, so that no tenant ever has a config row with zero writers.

#### Acceptance Criteria

1. THE Per_Record_Cutover SHALL make the SAM write path live and read-back verified in PROD before
   the corresponding Projection_Sync builder is removed.
2. WHEN a record is migrated, THE migration SHALL copy every live tenant's MySQL value into the
   SAM-owned row and verify the row by reading it back.
3. THE Safety_Gate SHALL prevent the Projection_Sync builder removal for a record from merging to
   `main` until the SAM write path for that record is verified live in PROD.
4. FOR ALL points during a record's cutover, the migrated `config#*` row SHALL have exactly one
   authoritative writer and never zero.
5. THE per-record data migration SHALL remain reversible by retaining the MySQL params until the
   SAM write path is verified live in PROD.
6. THE records SHALL be migrated in the order `config#fields` then `config#scope` then `config#mail`.

### Requirement 11: ProjectionSync builder removal and param retirement (change-with-tests)

**User Story:** As a maintainer, I want each retired builder and MySQL param removed with its
allocated tests updated in the same change, so that Flask stops writing migrated rows without
leaving tests asserting stale behavior.

#### Acceptance Criteria

1. WHEN a record is cut over, THE Projection_Sync SHALL remove only that record's builder call
   (`build_config_fields_row`, `build_config_scope_row`, or `build_config_mail_row`) and leave the
   other two in place until their own step.
2. WHEN a record's builder call is removed, THE `ProjectionSync.sync_administration` result SHALL
   contain no row for that migrated `config#*` sort key.
3. WHEN a record's builder is removed, THE change SHALL update the allocated Flask and SAM tests and
   any committed fixtures in the same change, per the change-with-tests contract.
4. WHEN the `members.*` params for a migrated record are retired, THE change SHALL remove them
   together with the builder removal in the same cutover step.
5. THE `SyncResult`, `TenantSource`, `SourceProvider`, and `DatabaseSourceProvider` public surface
   SHALL remain unchanged.

### Requirement 12: Delete-sweep safety guardrail

**User Story:** As a maintainer, I want a verified, regression-locked guarantee that the existing
Flask delete sweeps touch only their own sort-key prefixes, so that a SAM-authored config row can
never be deleted by unrelated Flask cleanup even under split ownership.

#### Acceptance Criteria

1. FOR ALL tenant inputs, `ProjectionSync._reconcile_scopegrants` SHALL delete only rows under the
   `scopegrant#` prefix, because it deletes only the keys returned by `_list_scopegrant_sort_keys`,
   which queries with `begins_with(sort_key, "scopegrant#")` and re-checks the `scopegrant#` prefix
   before collecting a key.
2. FOR ALL tenant inputs, `delete_config_views_residue` SHALL delete only the single exact
   `config#views` key it builds via `build_key(administration, build_sort_key(RECORD_TYPE_CONFIG,
   CONFIG_ID_VIEWS))`, deleting it only when present, and SHALL never address `config#fields`,
   `config#scope`, or `config#mail`.
3. THE `_reconcile_scopegrants` and `delete_config_views_residue` sweeps SHALL NOT delete
   `config#fields`, `config#scope`, or `config#mail` for any tenant.
4. THE `config#views` cleanup SHALL remain delete-only residue removal and SHALL NOT author any row.
5. THE `config#*` rows SHALL be UPSERT-ONLY in the Governance_Projection table: no delete-sweep
   SHALL target the `config#` space, and the only deleter of a `config#` row SHALL be the
   `config#views`-only residue cleanup defined in Requirement 21 (`delete_config_views_residue`).
6. THE existing regression test `test_sync_reconcile_never_deletes_non_scopegrant_rows` SHALL remain
   green, and THE test SHALL be extended so that a SAM-authored `config#fields`, `config#scope`, or
   `config#mail` row SURVIVES a full `ProjectionSync.sync_administration` plus `_reconcile_scopegrants`
   cycle, so that the guardrail holds in the split-ownership case where no Flask builder re-creates a
   migrated `config#*` row.

### Requirement 13: Frontend repoint and simplified save-result UX

**User Story:** As a Tenant Admin, I want the config save to call the SAM route and reflect the
saved state immediately, so that there is no projection-lag reasoning in the UI.

#### Acceptance Criteria

1. WHEN a record is cut over, THE Members_Config_Service SHALL repoint that record's save from the
   Flask `parameter_admin_routes` to the SAM `PUT /members/config/{configId}` route.
2. WHEN a SAM config write succeeds, THE Members_Config_Service SHALL treat the write as
   authoritative and SHALL NOT present a pending-projection state.
3. THE Members_Config_Editor and `MembershipTypesManager` editors SHALL consume the
   Members_Config_Service unchanged in form shape, with only the save target repointed to the
   SAM_Write_Path.
4. WHEN a config save is repointed, THE change SHALL update the allocated frontend tests in the same
   change, per the change-with-tests contract.

### Requirement 14: Single authoring door / no second writer

**User Story:** As a maintainer, I want exactly one authoring door per `members.*` key, so that no
config row is ever writable from two surfaces (the two-writers-one-config trap).

#### Acceptance Criteria

1. WHEN a `members.*` key has migrated to SAM, THE Advanced_Parameter_Editor SHALL offer no write
   path for any `members.*` key, so that the blanket `members`-namespace exclusion is re-instated.
2. WHEN a `members.*` key has migrated to SAM, THE per-record data migration SHALL delete the
   migrated `members.*` MySQL rows, so that no raw or MySQL authoring door remains for that key.
3. FOR ALL `members.*` keys, after migration THE feature SHALL provide exactly one authoring door,
   and that door SHALL be the SAM-owned typed function.
4. WHERE both the Typed_Mail_Function and any other view touch `config#mail`, both SHALL write
   through the single SAM_Write_Path, so that no second store or second writer is introduced.

### Requirement 15: Mail-adjacent surfaces kept distinct

**User Story:** As a maintainer, I want the three mail-adjacent surfaces kept distinct, so that the
`config#mail` migration touches only the SAM-owned scalars and leaves the sender-identity and
invoice SES surfaces on their existing planes.

#### Acceptance Criteria

1. THE `config#mail` migration SHALL change only the SAM-owned `config#mail` scalars
   (`mail_enabled`, `mail_domain`, `mail_local_part`, `mail_certified`, `mail_reply_to_default`,
   `application_consent_notice`) on the SAM plane.
2. WHERE the Typed_Mail_Function co-locates Member_Sender_Identities, THE Member_Sender_Identities
   dataset SHALL remain a distinct dataset authored via its existing Flask route
   (`/api/members/sender-identities`) and SHALL NOT become part of the SAM `config#mail` write.
3. THE SAM Members Lambda SHALL implement no sender-identity route under this feature.
4. THE Flask/SES invoice verification path (`SenderSettingsTab`) SHALL remain unchanged by this
   feature.
5. THE feature SHALL NOT alter any code path that writes or reads invoice SES settings.

### Requirement 16: Cognito and deferred rows unchanged

**User Story:** As a platform operator, I want Cognito writes and the deferred projection rows left
exactly as today, so that Phase 1 stays locked to the three config rows.

#### Acceptance Criteria

1. THE Flask plane SHALL continue to write Cognito `custom:tenants` values and invites unchanged.
2. THE Projection_Sync SHALL continue to write `tenant`, `module#`, `role#`, and `scopegrant#` rows
   exactly as today.
3. THE feature SHALL NOT introduce any SAM identity-plane writes.
4. THE Flask and SAM planes SHALL NOT call each other at runtime, and the frontend SHALL talk to
   each plane separately.

### Requirement 17: Error handling

**User Story:** As a maintainer, I want errors handled without leaking internals, so that failures
are diagnosable server-side while clients receive safe messages.

#### Acceptance Criteria

1. IF a config write request has an unknown `configId` or a body that fails per-`configId` shape
   validation, THEN THE SAM_Write_Path SHALL return an HTTP 400 response with a generic,
   caller-safe message.
2. IF an unexpected exception occurs on the SAM edge, THEN THE SAM_Write_Path SHALL log the full
   exception server-side and return a generic client message without echoing the exception text.
3. WHERE a Flask route or ProjectionSync path is changed by this feature, THE Flask plane SHALL use
   the `error_response` convention (generic message plus `error_id`) on the caught-exception path
   per `30-backend-api-flask-mysql.md`.
4. IF the resolved table cannot be determined because `GOVERNANCE_PROJECTION_TABLE` is missing or
   blank, THEN THE SAM_Write_Path SHALL fail loudly at the first DynamoDB call.

### Requirement 18: TEST to PROD promotion

**User Story:** As a platform operator, I want a documented TEST → PROD promotion story, so that
config rows are promoted safely with a rehearsed rollback.

#### Acceptance Criteria

1. THE SAM_Write_Path SHALL operate against both the TEST table (`test_governance_projection`) and
   the PROD table (`governance_projection`) resolved via `GOVERNANCE_PROJECTION_TABLE`.
2. THE promotion SHALL verify TEST and PROD `config#*` read-back parity before the cutover merge.
3. THE promotion SHALL include a rehearsed rollback.
4. WHEN a config change is STRUCTURAL, THE promotion SHALL run a tenant-wide config migration
   test→prod per Requirement 24, ordered relative to merge-to-main like the other
   `backend/src/migrations` migrations.
5. WHEN a config change is ADDITIVE DATA, THE promotion SHALL require no separate promotion step,
   because the single reader consumes the new data directly.

### Requirement 19: CI/CD surface

**User Story:** As a platform operator, I want the change delivered through the documented CI/CD
surface, so that SAM infra, frontend, and builder removal ship through the correct gated pipelines.

#### Acceptance Criteria

1. THE SAM write infra and the scoped IAM write grant SHALL ship via `deploy-sam-members.yml` using
   OIDC `NonprofitDeployRole` with no stored AWS secrets.
2. THE frontend repoint and the Projection_Sync builder removal SHALL ride the full-test-suite /
   Flask path.
3. THE CodeQL and GitGuardian gates SHALL be green before any merge to `test` or `main`.
4. WHEN a promotion merges `test` into `main`, THE merge SHALL be treated as a production deploy
   through a reviewed pull request and SHALL NOT be pushed straight to `main`.
5. THE `workflow_dispatch` trigger SHALL default to the TEST environment, so that a mis-click never
   deploys production.

### Requirement 20: Typed authoring UI for Members config

**User Story:** As a Tenant Admin, I want each Members config concern authored through a dedicated
typed function, so that I never edit raw JSON and each concern has exactly one typed door.

#### Acceptance Criteria

1. THE Typed_Mail_Function SHALL be a dedicated single-screen function under Members Tenant Admin
   that is the single authoring door for all Members mail config (`mail_enabled`, `mail_domain`,
   `mail_local_part`, `mail_certified`, `mail_reply_to_default`, `application_consent_notice`).
2. THE Typed_Mail_Function SHALL present typed Chakra form fields with Formik and Yup validation and
   bilingual labels per `32-frontend-ui.md`, rather than a raw JSON grid.
3. THE Members_Config_Editor SHALL own `field_overlay` (`config#fields`) and `scope_dimensions`
   (`config#scope`) as typed form fields repointed to the SAM_Write_Path, and SHALL NOT author a
   tenant-level rows-per-page default, because rows-per-page is the per-user runtime
   Rows_Per_Page_Selector of Requirement 25.
4. THE feature SHALL NOT introduce a raw JSON grid for any Members config concern.

### Requirement 21: Retire view_contexts residue (no editor, physical cleanup)

**User Story:** As a maintainer, I want the retired View_Contexts_Residue physically removed, so
that the zero-`members.*`-rows guarantee holds end-to-end and no dead config lingers.

#### Acceptance Criteria

1. THE View_Contexts_Residue SHALL have no authoring editor and SHALL be authored nowhere — neither
   the Advanced_Parameter_Editor nor any typed function — so that it requires no migration, which
   distinguishes it from the migrated keys in Requirement 14.2.
2. THE stored `members.view_contexts` MySQL parameter rows SHALL be removed for every tenant via
   `backend/src/migrations/retire_members_view_contexts.py`, which SHALL default to a dry run and
   remain reversible and auditable.
3. WHEN the View_Contexts_Residue cleanup runs, THE `retire_members_view_contexts.py` migration
   SHALL be confirmed applied in TEST and then in PROD.
4. WHERE stale `config#views` DynamoDB projection residue exists, THE
   `ProjectionSync.delete_config_views_residue` sweep SHALL remove it as delete-only residue removal
   and SHALL author no row.
5. AFTER the View_Contexts_Residue cleanup completes, THE Advanced_Parameter_Editor and MySQL SHALL
   contain no `members.view_contexts` row, so that the Single_Authoring_Door guarantee of
   Requirement 14 holds end-to-end including retired keys.
6. THE Session_Columns per-user column chooser (`ColumnChooser` with `getColumnPreferences` /
   `saveColumnPreferences`) SHALL remain unchanged, because it is a separate per-user preference and
   is neither View_Contexts_Residue nor tenant config.
7. THE tenant-level `default_page_size` scalar SHALL be retired rather than re-homed: it is NOT
   authored on `config#fields`, NOT migrated to SAM, and the Members_Projection_Reader SHALL no
   longer surface it as a tenant default, because rows-per-page is the per-user runtime
   Rows_Per_Page_Selector of Requirement 25.

### Requirement 22: Scope single-source authoring with a frontend-written Flask mirror

**User Story:** As a Tenant Admin, I want the per-field scope toggle to be the single, effective way
to define scope, with SAM `config#scope` authoritative and Flask's validator copy kept as a derived
mirror, so that scope (access control) is authored in one place with real effect and no dead control
while Flask grant validation keeps working without being moved to SAM.

#### Acceptance Criteria

1. THE per-field `scope` attribute on the `config#fields` overlay SHALL be the single AUTHORING
   source for Members scope dimensions, and SAM `config#scope` (derived from it) SHALL be the single
   authoritative source for scope dimensions.
2. THE standalone `members.scope_dimensions` param SHALL be KEPT as the Scope_Dimension_Mirror (a
   frontend-written derived copy of SAM `config#scope`) and SHALL NOT be deleted and SHALL NOT be
   retired as data.
3. THE Scope_Grant_Validation_Reader (`user_tenant_scope_service`), the Scopegrant_Projection_Builder
   (`_projection_scopegrant`), and the scope picker and validation API SHALL continue to read the
   Scope_Dimension_Mirror (`members.scope_dimensions`) UNCHANGED, so that moving those validators to
   SAM (Option D) stays out of scope.
4. THE `members.scope_dimensions` param SHALL be retired ONLY as an authoring surface: it SHALL NOT
   be editable in the Advanced_Parameter_Editor and SHALL NOT be authored by Projection_Sync; its
   only author SHALL be the frontend scope-save mirror.
5. WHEN a Tenant Admin saves a scope change, THE frontend SHALL write SAM `config#scope` first as
   the authoritative source and THEN mirror the same dimension set into Flask `members.scope_dimensions`
   via a Flask write.
6. THE Scope_Dimension_Mirror write SHALL be best-effort with SAM authoritative, and IF the Flask
   mirror-write fails, THEN THE UI SHALL surface the failure and offer retry, so that the mirror is
   eventually-consistent rather than transactional and a failed mirror leaves Flask's copy stale
   until a surfaced retry succeeds.
7. WHEN a new tenant defines scope dimensions, THE frontend mirror SHALL populate
   `members.scope_dimensions` automatically with no manual step, so that routine scope definition
   requires no SysAdmin escalation.
8. WHEN scope authoring and grant validation both operate, IF a scope grant requests a dimension or
   value the tenant has not declared on any field, THEN THE Scope_Grant_Validation_Reader SHALL
   reject the grant by canonical-equality against the Scope_Dimension_Mirror, so that the
   access-control invariant is preserved.
9. WHEN the per-field overlay `scope` attributes change or the mirror-write logic changes, THE
   change SHALL update the allocated scope-equivalence, round-trip, and grant-validation tests in the
   same change, per the change-with-tests contract.
10. THE single-source authoring and mirror behavior defined here SHALL be performed as part of the
    `config#scope` cutover described in Requirement 8 and the Per_Record_Cutover of Requirement 10,
    not as a separate pre-spec workstream.

### Requirement 23: Scope-change grant reconciliation for existing tenants (no silent stale grants)

**User Story:** As a Tenant Admin, I want changing scope dimensions on a live tenant to never
silently orphan existing user scope grants, so that routine changes mirror automatically with a
reminder to review grants and orphaning changes are blocked with guidance to align with the System
Administrator.

#### Acceptance Criteria

1. WHEN a scope-dimension change is authored for a tenant that has no existing `user_tenant_scope`
   grants, THE Scope_Grant_Reconciliation SHALL apply the change without a reconciliation gate.
2. WHEN a scope-dimension change is ROUTINE (a new tenant, or adding a dimension or value such that
   no existing `user_tenant_scope` grant is orphaned), THE Scope_Grant_Reconciliation SHALL mirror
   the dimensions to Flask automatically AND SHALL show the Tenant_Admin a reminder that user scope
   grants (`user_tenant_scope`) may need to be created or updated to align with the change.
3. THE frontend SHALL NOT auto-rewrite user scope grants, because grant creation or update is a
   human decision reserved to the Tenant_Admin.
4. WHEN a scope-dimension change renames a dimension, removes a dimension, or removes a value such
   that it would orphan one or more existing `user_tenant_scope` grants, THE Scope_Grant_Reconciliation
   SHALL detect the affected grants by comparing the proposed scope dimensions against the stored
   grants before applying the change.
5. IF a scope-dimension change would orphan one or more existing `user_tenant_scope` grants, THEN
   THE Scope_Grant_Reconciliation SHALL block the change and SHALL notify the Tenant_Admin which
   users and grants are affected.
6. IF a scope-dimension change is blocked for orphaning grants, THEN THE block message SHALL include
   guidance to contact the System Administrator to align on the change, as an interim, message-based
   escalation valid until the structural solution (moving user-tenant-role-scope to SAM, an Option D
   item) exists.
7. WHERE the affected grants are resolvable by the Tenant_Admin updating or clearing them, THE
   Scope_Grant_Reconciliation SHALL make the change applicable once those grants no longer reference
   a removed or renamed dimension key or value.
8. FOR ALL applied scope-dimension changes, THE Scope_Grant_Reconciliation SHALL guarantee that no
   surviving `user_tenant_scope` grant references a dimension key or value that no longer exists.
9. THE Scope_Grant_Reconciliation detection SHALL be cross-plane, comparing the SAM-authoritative
   proposed scope dimensions (`config#scope` derived from the per-field `scope` attributes per
   Requirements 8 and 22) against the Flask MySQL `user_tenant_scope` grants.
10. WHEN the Scope_Grant_Reconciliation detection or reconciliation logic changes, THE change SHALL
    update the allocated tests in the same change, per the change-with-tests contract.
11. THE Scope_Grant_Reconciliation SHALL operate within the `config#scope` cutover discipline of
    Requirement 10, so that scope definition (SAM-authoritative per Requirements 8 and 22) and grant
    reconciliation stay consistent across the cutover.

### Requirement 24: Structural config change migration (single-codebase, latest-reader)

**User Story:** As a maintainer, I want structural config changes to migrate every tenant's config
to the new shape on deploy, so that the single production reader only ever sees the latest shape
without a per-row version system.

#### Acceptance Criteria

1. THE production system SHALL run a single codebase whose reader interprets only the latest config
   shape, config rows SHALL NOT carry a schema or release version, and THE reader SHALL NOT branch
   on a per-row shape version.
2. WHEN a config change is ADDITIVE DATA (a new field value, a new enum value, a scope-toggle
   change, or an edited scalar) within an existing config-row shape, THE reader SHALL consume it
   with no migration and no version.
3. WHEN a config change is STRUCTURAL (introducing a new `config#` row type, retiring a `config#`
   row type, or adding, removing, or repurposing an attribute in a config row's shape), THE change
   SHALL ship a tenant-wide config migration that updates every tenant's config rows to the new
   shape as part of the deploy that introduces the change.
4. THE structural config migration SHALL run test→prod following the same migration discipline as
   `backend/src/migrations` and the Per_Record_Cutover of Requirement 10, remaining dry-run and
   reversible where applicable and verified in TEST before PROD.
5. AFTER a structural config migration completes, every affected tenant config row SHALL be the new
   shape, so that the single reader interprets it with no per-row version.
6. WHERE a structural change is additive, THE change MAY rely on the reader's existing graceful
   defaulting (unknown attributes ignored, missing attributes defaulted).
7. IF a structural change removes, renames, or repurposes an attribute or row type, THEN THE change
   SHALL ship the tenant-wide config migration, because graceful defaulting is not sufficient for a
   non-additive shape change.

### Requirement 25: Members table rows-per-page runtime selector (DynamoDB cursor paging)

**User Story:** As a Members user, I want to choose how many rows the table shows
(50/100/250/500/Max) with prev/next paging, so that I control page size at runtime without a
tenant-authored default.

This requirement is IN SCOPE for this spec: it touches both the SAM Members edge/query path (which
accepts a page-size/limit parameter and returns the `LastEvaluatedKey` cursor) and the Members
table frontend (the Rows_Per_Page_Selector and the Cursor_Paging prev/next controls).

#### Acceptance Criteria

1. THE Members table SHALL present a Rows_Per_Page_Selector with options 50, 100, 250, 500, and Max.
2. WHEN the user selects a fixed option (50, 100, 250, or 500), THE SAM Members query SHALL apply
   that value as the DynamoDB Query `Limit`.
3. WHEN the user selects Max, THE SAM Members query SHALL omit the DynamoDB Query `Limit` so that
   DynamoDB returns one page up to its natural ~1 MB response boundary, so that Max is one Query
   page rather than all rows.
4. THE Members table SHALL page with cursor-based prev/next using the DynamoDB `LastEvaluatedKey`
   for every Rows_Per_Page_Selector option including Max, and SHALL NOT use a SQL-style offset or
   jump-to-page control.
5. THE Next control SHALL be enabled only when the last query returned a `LastEvaluatedKey`, and
   THE Prev control SHALL be enabled only when a previous-page cursor exists; otherwise each control
   SHALL be disabled.
6. WHERE a tenant's members fit within one page for the selected size, THE Members table SHALL
   return them in a single page with no `LastEvaluatedKey`, so that the Next control is disabled and
   the result appears as one page.
7. THE SAM Members edge/query path SHALL accept the selected page-size/limit parameter and SHALL
   return the `LastEvaluatedKey` cursor to the frontend for both the fixed options and Max.
8. THE Rows_Per_Page_Selector SHALL mirror the FIN Transactions rows-per-page pattern adapted for
   DynamoDB, bounded by the ~1 MB page via the Max option rather than an unbounded all-rows option.
9. THE rows-per-page value SHALL be a per-user runtime choice and SHALL NOT be a tenant-authored
   config value; the tenant-level `default_page_size` config is RETIRED — it is NOT authored on
   `config#fields`, NOT carried on the `config#fields` row, and NOT migrated to SAM, and the
   Members_Projection_Reader SHALL no longer surface it as a tenant default.
10. WHERE a per-user rows-per-page default is persisted, THE Rows_Per_Page_Selector MAY use it as
    the selector's initial value; otherwise THE Members table SHALL use a platform fallback for the
    initial pre-selected option, because no tenant-authored default exists.

### Requirement 26: Scope dimension mirror to Flask (frontend cross-plane bridge)

**User Story:** As a maintainer, I want the frontend to mirror the SAM-authoritative scope
dimensions into Flask's validator copy, so that Flask grant validation keeps working without moving
it to SAM (Option D stays out of scope).

#### Acceptance Criteria

1. THE frontend SHALL read the authoritative scope dimensions from SAM `config#scope`, which is
   derived from the per-field `scope` attributes per Requirements 8 and 22.
2. WHEN a Tenant Admin saves a scope change, THE frontend SHALL write SAM `config#scope` first as
   the authoritative source and THEN mirror the same dimension set into Flask `members.scope_dimensions`.
3. THE Scope_Grant_Validation_Reader, the Scopegrant_Projection_Builder, and the scope picker and
   validation API SHALL read the Scope_Dimension_Mirror (`members.scope_dimensions`) UNCHANGED.
4. THE Flask and SAM planes SHALL NOT call each other at runtime, and THE frontend SHALL be the
   cross-plane bridge that writes each plane separately.
5. THE Scope_Dimension_Mirror write SHALL be best-effort with SAM authoritative, and IF the Flask
   mirror-write fails, THEN THE UI SHALL surface the failure and offer retry.
6. THE Scope_Dimension_Mirror SHALL be a derived copy of the SAM-authoritative `config#scope`
   dimensions and SHALL NOT be an independent authoring surface — it SHALL NOT be editable in the
   Advanced_Parameter_Editor and SHALL NOT be authored by Projection_Sync.
7. WHEN the frontend mirror-write logic changes, THE change SHALL update the allocated frontend and
   Flask tests in the same change, per the change-with-tests contract.

## Open Questions

No open questions remain; all resolved — see Resolved below.

### Resolved (kept for traceability)

- **OQ-7 (SysAdmin-escalation mechanism for complex scope changes) — RESOLVED:** The SysAdmin
  alignment is a surfaced MESSAGE, not an automated mechanism. Routine scope definition or edit
  (including new tenants, adding a dimension or value with no orphaned grant) auto-mirrors the
  dimensions to Flask (`members.scope_dimensions`) and shows the Tenant_Admin a reminder that user
  scope grants may need to be created or updated to align with the change. The ORPHANING case
  (renaming or removing a dimension, or dropping a value that would orphan existing `user_tenant_scope`
  grants — Requirement 23) is blocked with a stronger message that includes guidance to contact the
  System Administrator to align on the change. This message-based escalation is an interim; the
  structural solution (bringing user-tenant-role-scope to SAM, an Option D item) is future work and
  is out of scope. So there is no automated SysAdmin-escalation mechanism to design. Settled by
  Requirements 22, 23, and 26.

- **OQ-6 (`default_page_size` authoring home) — RESOLVED:** Rows-per-page is not a tenant-authored
  config value at all — it is a per-user runtime Rows_Per_Page_Selector on the Members table
  (options 50/100/250/500/Max, mirroring the FIN Transactions dropdown adapted for DynamoDB). Max is
  one DynamoDB Query page up to the natural ~1 MB response boundary (not all rows); the fixed
  options apply a Query `Limit` and Max omits it, and every option including Max uses cursor-based
  prev/next on the `LastEvaluatedKey` (no SQL-style offset/jump-to-page). Consequently the
  tenant-level `default_page_size` config is RETIRED: it is not authored on `config#fields`, not
  carried on the `config#fields` row, and not migrated to SAM, and the Members_Projection_Reader no
  longer surfaces it as a tenant default (a persisted per-user default MAY seed the selector's
  initial value but is not required). Settled by Requirement 25 and by Requirement 7 no longer
  carrying `default_page_size`.
- **OQ-5 (Version model / stale-write guard) — RESOLVED:** The production system is a single
  codebase with one latest reader, so config rows carry no schema/release version; the Version_Stamp
  is an ordering/when-written marker only and does not gate reads. Phase 1 is last-writer-wins with
  no conditional stale-write 409 guard. The `get_config_status()` / delivered-vs-source staleness
  reasoning collapses because a SAM write is authoritative (no projection lag). Settled by
  Requirement 6 and the new structural-migration Requirement 24.
- **OQ-4 (TEST → PROD promotion mechanism) — RESOLVED:** A STRUCTURAL config change is promoted as a
  tenant-wide config migration run test→prod like the other `backend/src/migrations`, ordered
  relative to merge-to-main; ADDITIVE data changes need no promotion step because the single reader
  consumes them. Settled by Requirement 18 and the new structural-migration Requirement 24.
- **OQ-3 (`config#scope` authoring surface) — RESOLVED:** The per-field `scope` attribute on the
  `config#fields` overlay is the single AUTHORING source for scope; SAM `config#scope` is derived
  from those per-field scope attributes and is authoritative, done as part of the `config#scope`
  cutover (not a separate pre-spec workstream). This also fixes a code-verified defect:
  `build_config_scope_row` today falls back to the standalone `members.scope_dimensions` param when
  the overlay yields no dimensions, so for tenants that authored dimensions in the standalone param
  the per-field scope toggle writes a `scope` attribute the live projection never uses — the toggle
  silently does nothing; the per-field toggle now has real effect. Rather than deleting the standalone
  param and moving its readers to SAM (Option D, out of scope), `members.scope_dimensions` is KEPT as
  the frontend-written Scope_Dimension_Mirror: on scope save the frontend writes SAM `config#scope`
  first (authoritative) and then mirrors the dimension set into `members.scope_dimensions`, so the
  Flask access-control readers (`user_tenant_scope_service` grant validation and
  `_projection_scopegrant`) keep reading the mirror UNCHANGED. The param is retired only as an
  authoring surface. Settled by Requirements 8, 22, and 26.
- **OQ-2 (Sender-identity surface relationship) — RESOLVED, non-issue:** Code verification confirms
  the Members "Sender Addresses" surface (`MemberSenderIdentitiesTab` → Flask
  `/api/members/sender-identities`, `members_sender_identity_routes.py`) persists SES
  identity-verification state in the MySQL `email_verifications` table (keyed by `administration`)
  via `EmailVerificationService`; it carries no `config#` sort key and is not in DynamoDB, so it was
  never part of the `config#fields/scope/mail` projection this spec migrates. Leaving it on its
  existing Flask route this phase does not fragment the config migration. Moving the whole Members
  email feature (including any duplicate SES verification rule) to SAM is a possible FUTURE phase and
  is explicitly not required here. Settled by Requirement 15.
- **OQ-1 (Delete-sweep scoping) — RESOLVED:** This was not an open decision but a verifiable
  guarantee, now covered by Requirement 12 (the delete-sweep safety guardrail). `_reconcile_scopegrants`
  is confined to the `scopegrant#` prefix, `delete_config_views_residue` touches only the single
  `config#views` key, `config#*` rows are UPSERT-ONLY, and the regression test
  `test_sync_reconcile_never_deletes_non_scopegrant_rows` locks it in, extended for the split-ownership
  survival case. Settled by Requirement 12.

## Out of Scope (deferred to a later spec)

- `tenant` row ownership — stays MySQL-owned and Projection_Sync-written.
- `module#<name>` rows — stay MySQL-owned and Projection_Sync-written.
- `role#<email>#<role>` rows — deferred (Phase 2, conditional); the Flask plane reads
  `user_tenant_roles` from MySQL at request time, so role ownership cannot move yet.
- `scopegrant#<email>#<dimension>` rows — deferred (Phase 2, clean).
- Moving the Flask user-tenant-role-scope grant data and its validators (`user_tenant_scope_service`,
  `_projection_scopegrant`, the scope picker/validation API) to SAM (the structural solution,
  "Option D") — a FUTURE phase, out of scope. This spec instead keeps Flask `members.scope_dimensions`
  as a frontend-written derived mirror (Scope_Dimension_Mirror) as the interim, so those validators
  keep reading it unchanged.
- Invoice SES verification (`SenderSettingsTab`) — stays on the Flask/SES plane and must not be
  touched.
- Member_Sender_Identities (`MemberSenderIdentitiesTab`) — stays on its existing Flask route
  (`/api/members/sender-identities`); it co-locates in the Typed_Mail_Function UI but is a separate
  dataset and is not part of the SAM `config#mail` write.
- Cognito writes (`custom:tenants`, invites) — stay on Flask; no SAM identity-plane writes.
- `config#views` — retired residue; never authored, cleanup is delete-only.
- Raw JSON authoring of any Members config concern — removed; every concern has a typed door.
- `members.view_contexts` (View_Contexts_Residue) — retired with no editor; it is authored nowhere
  and is cleanup-only (MySQL rows removed via `retire_members_view_contexts.py`, stale `config#views`
  residue via the delete-only sweep), not migrated.
- Session_Columns (the per-user column chooser `ColumnChooser` /
  `getColumnPreferences` / `saveColumnPreferences`) — a separate live per-user preference left
  untouched by this feature.

## Success Metrics

- DynamoDB `governance_projection` is the system-of-record for `config#fields`, `config#scope`, and
  `config#mail` (including `mail_certified` carried on the `config#mail` row); the three
  corresponding `members.*` MySQL params and the three `ProjectionSync` builders are retired.
- `config#mail` carries `mail_reply_to_default`, and the mail Reply-To model is defined for both
  send modes: an interactive (user-triggered) send sets Reply-To to the invoking user's verified
  email at runtime (not a config attribute), while a scheduled/unattended send uses the `config#mail`
  `mail_reply_to_default` (falling back to the `<mail_local_part|noreply>@<mail_domain>` From address
  when absent), so an unattended send always has a defined Reply-To. The From composition and the
  interactive Reply-To are already implemented; this spec adds only the scheduled default.
- There is no schema-version system on config rows: the single production codebase reads only the
  latest shape, structural config changes migrate every tenant to the new shape on deploy
  (test→prod like other `backend/src/migrations`), additive data changes are transparent (no
  migration, no version), and the Phase 1 write path is last-writer-wins with the Version_Stamp as
  an ordering marker only.
- The Members_Projection_Reader is unchanged and returns equivalent values on read-back for all
  three migrated rows (round-trip equivalence holds).
- Scope has a single authoring source (the per-field `scope` attribute on the `config#fields`
  overlay) with SAM `config#scope` authoritative; the per-field scope toggle has a real, visible
  effect with no silent fallback. Flask `members.scope_dimensions` is NOT deleted — it is kept as a
  frontend-written derived mirror (Scope_Dimension_Mirror): on scope save the frontend writes SAM
  first then mirrors the dimension set into Flask. The access-control validators
  (Scope_Grant_Validation_Reader and Scopegrant_Projection_Builder) read the mirror UNCHANGED (moving
  them to SAM is Option D, out of scope), so scope-grant validation still rejects undeclared
  dimensions/values. New tenants auto-mirror with no manual step, and the mirror-write is best-effort
  with surfaced retry on failure (eventually-consistent, not transactional).
- Changing scope dimensions on an existing tenant never silently orphans user grants: a routine
  change (new tenant, adding a dimension/value with no orphaned grant) auto-mirrors to Flask and
  shows the Tenant Admin a reminder to review/update user scope grants; an orphaning change
  (renaming/removing a dimension or dropping a value) is blocked with a message to contact the System
  Administrator to align (interim, message-based) and the Tenant Admin is notified of the affected
  users/grants; the frontend never auto-rewrites user grants (a human decision); no applied change
  leaves a `user_tenant_scope` grant referencing removed or renamed vocabulary (detection is
  cross-plane: SAM-authoritative dimensions vs Flask grants).
- Every live tenant (minimum `h-dcn`) has each migrated row authored and read-back verified in PROD
  before the corresponding builder removal merges to `main`.
- The split-ownership partition holds: SAM writes only `config#fields/scope/mail`; Projection_Sync
  writes only `tenant`/`module#`/`role#`/`scopegrant#`; no row ever has zero writers during cutover.
- Every `members.*` key has exactly one authoring door: the SAM-owned typed function (the
  Typed_Mail_Function for `config#mail`; the Members_Config_Editor for `config#fields` /
  `config#scope`) after migration.
- The Advanced_Parameter_Editor serves zero `members.*` rows and the migrated `members.*` MySQL
  rows are deleted, so no raw or MySQL door remains for any Members config key.
- Rows-per-page for the Members table is a per-user runtime selector (options 50/100/250/500/Max,
  where Max is one DynamoDB Query page up to the natural ~1 MB boundary) with DynamoDB cursor-based
  prev/next paging on the `LastEvaluatedKey` for every option including Max, and there is no
  tenant-level `default_page_size` config: it is not authored on `config#fields`, not carried on the
  row, and not migrated to SAM.
- The retired View_Contexts_Residue (`members.view_contexts`) has no editor and is cleanup-only:
  its MySQL rows are removed via `retire_members_view_contexts.py` and any stale `config#views`
  residue via the delete-only sweep, so no `members.view_contexts` row remains and the
  zero-`members.*`-rows guarantee holds including retired keys; Session_Columns stays untouched and
  out of scope.
- The invoice SES verification path, the Member_Sender_Identities Flask route, and Cognito writes
  are observably unchanged.
- SAM infra + IAM ship via `deploy-sam-members.yml`; CodeQL and GitGuardian are green on every
  merge; the `test → main` promotion goes through a reviewed PR.
