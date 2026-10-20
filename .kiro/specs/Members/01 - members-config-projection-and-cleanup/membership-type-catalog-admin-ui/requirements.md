# Requirements Document

> **Origin.** Split out from `.kiro/specs/Members/application-app/issues_found.md` (the "membership_type
> reference catalog has no TenantAdmin management UI" gap) and the `members-config-projection-and-cleanup`
> spec, which deliberately scoped this UI OUT. This is its own spec so the work is not lost.

## Introduction

`membership.membership_type` is a `reference` FIELD: a member record stores a `type_code` that points
at an entry in the tenant's **Lidmaatschap Beheer** membership-type catalog. The field and the catalog
are ALIVE and used — the member add/edit dropdown is fed from the catalog's active entries.

The gap: there is NO TenantAdmin UI to MANAGE that catalog. The SAM backend already exposes the full
CRUD (list/get/create/update/soft-delete). The frontend only ever READS it (`GET /membership-types`)
for the dropdown. So a tenant admin cannot add, rename, reorder, or retire a membership type — and the
Members field editor shows `membership_type` as `reference` with no values editor and no path onward,
which is a dead end.

This spec adds the missing authoring door: a TenantAdmin "Lidmaatschapstypes" (membership-types)
management surface wired to the EXISTING SAM routes, plus a pointer from the field editor to it. No new
backend capability is required — the routes, repository, domain entity, and validation already exist.

> **NOT the same as `view_contexts`.** `view_contexts` is a RETIRED, unused parameter (handled in the
> `members-config-projection-and-cleanup` spec). `reference` / `membership_type` is a LIVE field. This
> spec is about the live one.

## Glossary

- **`reference` field** — a field type whose value is a foreign key into a separately-managed catalog
  of records (vs `enum`, whose values are an inline list on the field). `membership_type` is the one
  such field today.
- **Membership-type catalog (Lidmaatschap Beheer)** — the tenant-scoped set of membership types, stored
  on the SAM plane in DynamoDB `sam-members` under sort key `membershiptype#<type_code>` in the tenant
  partition. Entry shape: `{ tenant_id, type_code, label{nl,en}, active, order }`.
- **Soft-delete / retire** — deactivating a catalog entry (`active=false`) so existing member records
  keep a valid reference while the type drops out of the assignment dropdown. Never a hard delete.
- **`members:admin`** — the capability gating catalog mutation (create/update/retire). Reads use
  `members:read`. Never self-service.

## Requirements

### R1 — A TenantAdmin surface lists the tenant's membership-type catalog

**User story:** As a tenant admin, I want to see all my membership types (including retired ones), so I
can understand and manage the vocabulary members are assigned.

#### Acceptance criteria

1. THE SPA SHALL provide a TenantAdmin management surface (a "Lidmaatschapstypes" / membership-types
   tab or section under the Members admin area) that lists the tenant's catalog entries.
2. THE list SHALL call `GET /membership-types` (ALL entries incl. retired — NOT `?active_only=true`),
   showing each entry's `type_code`, bilingual `label`, `active` state, and `order`, sorted by
   `(order, type_code)`.
3. THE surface SHALL be reachable only by a caller with the Members admin capability for the tenant
   (`members:admin`); a non-admin SHALL NOT see the management actions. (The SAM routes enforce this
   authoritatively; the UI gates for UX.)
4. Empty-by-default: a tenant with no catalog SHALL render an empty state with a create action, never a
   crash.

### R2 — A tenant admin can create, edit, and retire a membership type

**User story:** As a tenant admin, I want to add a new type, relabel/reorder an existing one, and retire
one that is no longer offered, so the catalog reflects the club's real membership types.

#### Acceptance criteria

1. CREATE — THE surface SHALL let an admin create an entry (`type_code`, bilingual `label`, `order`;
   `active` defaults true) via `POST /membership-types`; a duplicate `type_code` SHALL surface the
   server's 409 as a readable error.
2. EDIT — THE surface SHALL let an admin update an existing entry's `label`/`order`/`active` via
   `PUT /membership-types/{type_code}`; a 404 (absent) SHALL surface readably. `type_code` is the
   stable id and SHALL NOT be editable in place (create a new entry instead).
3. RETIRE — THE surface SHALL let an admin soft-delete (retire) an entry via
   `DELETE /membership-types/{type_code}`, which sets `active=false` — NEVER a hard delete; existing
   members keep their reference, and the retired type drops out of the assignment dropdown.
4. VALIDATION — THE surface SHALL enforce the same shape the domain requires (non-blank `type_code`
   with no `#` separator; a non-blank `nl` label; integer `order`) BEFORE submit for fast feedback,
   with the SAM domain remaining the authoritative validator (its 4xx surfaced on failure).
5. THE surface SHALL add a frontend service wrapper for the write routes
   (`createMembershipType` / `updateMembershipType` / `deactivateMembershipType`) alongside the
   existing `listMembershipTypes`, mirroring the Members API client pattern.
6. AFTER a successful mutation THE list SHALL refresh so the change is visible without a manual reload.

### R3 — The field editor points to the catalog manager (no more dead end)

**User story:** As a tenant admin opening `membership_type` in the field editor, I want to understand it
is a managed-catalog reference and get to where I manage its values, instead of a blank values editor.

#### Acceptance criteria

1. WHEN a `reference` field is opened in the Members field editor (`MembersFieldModal`) THEN the editor
   SHALL NOT show an empty enum-values editor; it SHALL instead show a read-only note that the field's
   values are managed in the membership-type catalog, with a link/button to that manager.
2. THE field editor SHALL continue to allow editing the field's presentation attributes
   (label / visibility / order / functional_group) — only the VALUES are managed elsewhere.
3. THE change SHALL be scoped to `reference`-type fields; `enum` fields keep their inline
   `EnumOptionsEditor` unchanged.

### R4 — No backend change; reads stay consistent

**User story:** As a maintainer, I want this to be a pure UI/authoring addition over existing routes, so
it carries no backend risk.

#### Acceptance criteria

1. THIS spec SHALL add NO new SAM route, repository method, domain entity, or validation — it consumes
   the existing `list/get/create/update/deactivate` membership-type routes as-is.
2. THE member add/edit dropdown (which reads `GET /membership-types?active_only=true`) SHALL continue
   to work unchanged; a type retired via the new UI SHALL disappear from that dropdown on next load.
3. ALL new/changed frontend code SHALL ship with paired tests (service wrapper, the management
   surface, the field-editor pointer), per the change-with-tests contract.

## Out of scope

- Any change to the `membership_type` field's STORAGE or the member record shape.
- Migrating `membership_type` to a different field type.
- A generic "reference catalog" framework for future reference fields — this spec targets the one live
  reference field (`membership_type`); generalization is a later concern if more reference fields appear.
- The projection fix and `view_contexts` retirement — the OTHER spec
  (`members-config-projection-and-cleanup`).
