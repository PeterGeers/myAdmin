# Design — Membership-type catalog admin UI

## Overview

Add the missing TenantAdmin authoring door for the `membership_type` reference catalog. Pure
frontend work over EXISTING SAM routes: a service wrapper for the write routes, a management
surface (list + create/edit/retire), and a pointer from the Members field editor so a
`reference` field is no longer a dead end. No SAM/backend change.

## Architecture

Frontend-only, consuming the Members SAM API already in place:
- **SAM routes (exist, unchanged)** — `routes.py` group `CATALOG`:
  `GET /membership-types` (`members:read`), `GET /membership-types/{type_code}` (`members:read`),
  `POST /membership-types` (`members:admin`), `PUT /membership-types/{type_code}` (`members:admin`),
  `DELETE /membership-types/{type_code}` = soft-delete (`members:admin`).
- **Storage (exists, unchanged)** — DynamoDB `sam-members`, SK `membershiptype#<type_code>` in the
  tenant partition; entry `{ tenant_id, type_code, label{nl,en}, active, order }`.
- **New frontend pieces** — a service wrapper (mutations), a management component, and a small
  change to `MembersFieldModal` for the `reference` pointer.

The data flow for management: component → service wrapper → Members API (SAM) → DynamoDB. The
existing member add/edit dropdown continues to read `GET /membership-types?active_only=true`
independently; a retire via the new UI simply drops the type from that active-only feed.

## Components and Interfaces

- `frontend/src/services/members/membersConfigApi.ts` (or a sibling) — ADD
  `createMembershipType(body)` → `POST /membership-types`;
  `updateMembershipType(typeCode, body)` → `PUT /membership-types/{type_code}`;
  `deactivateMembershipType(typeCode)` → `DELETE /membership-types/{type_code}`. Mirror the
  existing `listMembershipTypes` client style (envelope unwrap, error surfacing). Re-export from
  `membersApiService.ts` alongside `listMembershipTypes`.
- `frontend/src/components/TenantAdmin/MembersConfig/` — NEW management surface
  (e.g. `MembershipTypesTab.tsx` + a row/edit modal): lists ALL entries (`listMembershipTypes()`
  with no active filter), with create/edit/retire actions gated on the admin capability. Reuses
  the existing TenantAdmin Members tab shell + table/modal patterns.
- `frontend/src/components/TenantAdmin/MembersConfig/MembersFieldModal.tsx` — CHANGE: for a
  `reference`-type field, render a read-only note + a link/button to the membership-types manager
  instead of the empty `EnumOptionsEditor`. Keep presentation-attribute editing. `enum` path
  unchanged.
- `frontend/src/types/members.ts` — EXTEND `MembershipType` (and/or add a write-body type) to
  carry `label{nl,en}`, `order`, `active` for the authoring round-trip (read type already exists).

## Data Models

- **Catalog entry (read + write)** — `{ type_code: string, label: {nl: string, en?: string},
  active: boolean, order: number }`. `type_code` is the stable id (create-time only; immutable on
  edit). `tenant_id` is server-derived from the verified token — never sent by the client.
- **Create body** — `{ type_code, label, order?, active? }` (active defaults true server-side).
- **Update body** — `{ label?, order?, active? }` for `{type_code}`.
- **Retire** — `DELETE /membership-types/{type_code}` (no body); server sets `active=false`.

## Correctness Properties

Property 1: Round-trip. Creating a type then listing the catalog returns an entry whose
`type_code`/`label`/`order` equal what was submitted, and `active` is true by default.
**Validates: Requirements 2.1, 2.6**

Property 2: Retire is non-destructive. Retiring a type sets `active=false` and the entry still
appears in the management list (incl. retired), but is absent from the active-only dropdown feed.
**Validates: Requirements 2.3, 4.2**

Property 3: Immutable id. The edit path never changes an entry's `type_code`; editing updates
only `label`/`order`/`active`.
**Validates: Requirements 2.2**

Property 4: Reference pointer, not a values editor. For a `reference`-type field the field editor
renders the catalog pointer and NOT an enum-values editor; for an `enum` field it still renders
the inline values editor.
**Validates: Requirements 3.1, 3.3**

## Error Handling

- A duplicate `type_code` on create → server 409 → surfaced as a readable "type code already
  exists" message (R2.1).
- An absent `type_code` on edit/retire → server 404 → surfaced readably (R2.2).
- A malformed entry (blank `type_code` / contains `#` / blank `nl` label / non-int `order`) →
  client-side pre-submit validation blocks it with inline feedback; the SAM domain remains the
  authoritative validator and its 4xx is surfaced if the client check is bypassed (R2.4).
- A non-admin caller → the SAM route returns 403; the UI additionally hides the mutation actions
  for a non-admin (R1.3).

## Testing strategy

- **Service wrapper** — unit tests asserting each new function hits the right method + path
  (mirror `membersApiService.test.ts` style: `createMembershipType → POST /membership-types`,
  etc.) and unwraps/propagates errors.
- **Management surface** — component tests (MSW over the SAM routes): list renders entries incl.
  retired; create/edit/retire call the right route and refresh the list; empty state; admin-gating
  hides actions for a non-admin.
- **Field-editor pointer** — a test that opening a `reference` field shows the pointer (no enum
  editor) and an `enum` field still shows `EnumOptionsEditor` (change-with-tests on
  `MembersFieldModal`).
- Properties 1–4 are exercised through the component/service tests over the fake SAM routes.

## Rollout

1. Land the service wrapper + management surface + field-editor pointer together.
2. Frontend vitest + the build typecheck green; manual smoke on `test` (create/edit/retire a type,
   confirm the dropdown reflects a retire).
3. Promote with the normal `test` → `main` gate.

No SAM deploy is required (no backend change).
