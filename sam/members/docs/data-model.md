# Members module — data model (DynamoDB)

Technical reference for what the Members module stores in DynamoDB: tables, keys, record types,
and item shapes. For the plain-language admin view see [`config-guide.md`](./config-guide.md).

> Scope: the SAM/module plane only. Ownership is SPLIT (spec-02): the Flask/MySQL plane is the
> system of record for the access/identity GRANTS projected here (`role#`/`scopegrant#` from
> `user_tenant_roles`), while the tenant CONFIG rows (`config#fields`/`config#scope`/`config#mail`)
> are **SAM-authored** directly in DynamoDB (no MySQL source). This document describes how both —
> the projected grants and the SAM-authored config — plus the module's own data live in DynamoDB.
> Tenancy here is `tenant_id` (the partition key) — never `administration` (that is the MySQL plane).
>
> Single source of truth for the shapes below: `backend/src/services/projection_schema.py`
> (projection) and `sam/members/repository/table_design.py` (module table). This doc mirrors them.

---

## How DynamoDB stores this (read first)

- A row (DynamoDB "item") is identified by a **two-part key**: the **partition key** `tenant_id`
  (which tenant's drawer) + the **sort key** `sk` (identity within that drawer). A row is the
  pair `(tenant_id, sk)`.
- **Many different KINDS of row share one table.** The KIND is the leading segment of `sk` (e.g.
  `config`, `role`, `member`). The `#` just separates sort-key segments (`config#fields`).
- Treat each row's value as a **JSON record**. Nested things (like a field's dropdown values)
  live INSIDE a row's JSON — they are NOT separate rows and NOT sort keys.
- Isolation is structural: the partition key is pinned to `tenant_id`, so a query can never cross
  tenants.

The tables below are each a list of **the kinds of row you find in one tenant's partition**.

---

## Two identities this model keeps SEPARATE

The single most load-bearing distinction. **User ≠ member. There is no link between them.**

| | **User** (access principal) | versus | **Member** (data subject) |
| --- | --- | :---: | --- |
| What it is | a person with a Cognito login + admin/access rights |  | a person recorded as a club member |
| Identified by | Cognito login (`email` / `sub`) |  | `member_id` |
| Defined in | MySQL `user_tenant_roles` → projected as `role#…` rows |  | `member#…` rows in `sam-members` |
| Has access rights? | **Yes** — that is its whole purpose |  | **No** — being a member grants nothing |
| Link to the other | **none** (the same human MAY be both, but nothing stores that) |  | **none** |

User-keyed rows use the Cognito `sub`; member-keyed rows use `member_id`. They never reference
each other.

---

## Two tables, two roles

The module touches **two** DynamoDB tables (each with a `test_`-prefixed TEST sibling). There is
**no** separate `sam-config` table.

| Table | Role | Written by | Read by | System of record |
| --- | --- | --- | --- | --- |
| `governance_projection` | tenant/module rows + access & scope GRANTS (`role#`/`scopegrant#`) **projected from MySQL**, PLUS the tenant CONFIG rows (`config#fields`/`config#scope`/`config#mail`) **authored by SAM** | mixed — see below | SAM module | **split** (see below) |
| `sam-members` | The module's OWN data: member records + tenant-shared library + per-user preferences | SAM module (read/write) | SAM module | **this table** |

**Split ownership of `governance_projection` (spec-02, "SAM-owned config write path").** This
table no longer has a single writer. Two distinct sets of rows with two different authors:

- **Projected-from-MySQL (Flask writes, SAM reads):** `tenant`, `module#…`, `role#…`,
  `scopegrant#…`. `ProjectionSync` (one-directional) copies these from MySQL
  (`tenants` / `tenant_modules` / `user_tenant_roles`). System of record = MySQL.
- **SAM-authored config (SAM writes AND reads):** `config#fields`, `config#scope`, `config#mail`.
  Authored directly by the module via `PUT /members/config/fields` (a Change-Op list) and
  `PUT /members/config/{scope|mail}` (whole-object), Tenant_Admin-gated, `tenant_id` from the
  verified token. **`ProjectionSync` emits ZERO `config#*` rows** — the earlier
  Flask-writes-config#*/SAM-reads projection path is RETIRED for authoring and must not be
  revived. System of record = this table.

TEST siblings: `test_governance_projection`, `test_sam-members`. Both tables are managed OUTSIDE
the CloudFormation stack (Retain) — a deploy references them by name, never creates/replaces them.
Account: `nonprofit-deploy` (506221081911), region `eu-west-1`.

---

## `governance_projection` — projected config + grants

- Partition key `tenant_id`, sort key `sk` (segments joined by `#`).
- Version attr `version` (per-item; drives the idempotent conditional write + read staleness).

| Sort key (`sk`) | The JSON record holds | Keyed to | MySQL source | Who manages it |
| --- | --- | --- | --- | --- |
| `tenant` | the tenant row | tenant | `tenants` | **SysAdmin** (creates the tenant, invites the Tenant_Admin) |
| `module#<name>` | a module-enabled flag for the tenant | tenant | `tenant_modules` | **SysAdmin** (enables modules at tenant start) |
| `role#<email>#<role>` | a **user's** role grant (login + what they may do) | user | `user_tenant_roles` | **Tenant_Admin** (grants users their roles) |
| `scopegrant#<email>#<dimension>` | a **user's** granted scope values (which slice they may see) | user | `user_tenant_roles` | **Tenant_Admin** (grants users their scope values) |
| `config#scope` | the tenant's scope dimensions (access axes) | tenant | **SAM-authored** (`PUT /members/config/scope`) | **Tenant_Admin** |
| `config#fields` | field overlay: `fields` (added variable fields) + `overrides` (fixed-field overrides) + `functional_groups` + `default_page_size` | tenant | **SAM-authored** (`PUT /members/config/fields`, Change-Op) | **Tenant_Admin** |
| `config#mail` | the mail-enabled gate + sender fields | tenant | **SAM-authored** (`PUT /members/config/mail`) | **Tenant_Admin** |
| `config#views` | **RETIRED** — dead residue; no builder emits it, no code reads it (a cleanup routine only DELETES leftovers) | — | — | nobody (retired) |

**Who manages what (lifecycle):** **SysAdmin bootstraps** a tenant — creates the `tenant` row,
enables its `module#<name>` rows, and invites the **Tenant_Admin**. The **Tenant_Admin** then runs
everything else for that tenant: user role grants (`role#`), per-user scope grants
(`scopegrant#`), and all member config (`config#scope` / `config#fields` / `config#mail`). Nobody
manages `config#views` (retired).

Two authoring paths reach this table (split ownership, spec-02):
- `role#` / `scopegrant#` (and `tenant` / `module#`) are authored in **Flask** (UI → MySQL) and
  **projected** here read-only by `ProjectionSync` — no one edits them in DynamoDB directly.
- `config#fields` / `config#scope` / `config#mail` are authored **directly by the SAM module**
  via the `PUT /members/config/*` write surface (Change-Op for `fields`), which writes to this
  table. They are NOT projected from MySQL — `ProjectionSync` emits no `config#*` row.

`role#` / `scopegrant#` rows come from MySQL `user_tenant_roles` — the IDENTITY model, not member
data. They are access principals; a `role#` email may or may not also be a member, with no stored
link.

### `config#scope` — access control, not a member dropdown

Defines how member rows are sliced so a user who may not see everything is limited to granted
values. Each dimension: `key`, the member `field` it binds to, `label{nl,en}`, `enabled`,
`values` (the allowed set), and `required_for` (capabilities that REQUIRE a grant in this
dimension — deny-by-default without one).

Live h-dcn record (from production `governance_projection`), one `region` dimension:

```json
{
  "tenant_id": "h-dcn",
  "sk": "config#scope",
  "version": "2026-10-10T17:49:33",
  "dimensions": [
    {
      "key": "region",
      "field": "region",
      "label": { "nl": "Regio", "en": "Region" },
      "enabled": true,
      "required_for": ["Members_CRUD"],
      "values": ["Brabant/Zeeland", "Duitsland", "Friesland", "Geen",
                 "Groningen/Drenthe", "Limburg", "Noord Holland", "Oost",
                 "Utrecht", "Zuid Holland"]
    }
  ]
}
```

Config defines the axis + allowed values; the per-user `scopegrant#<email>#region` rows say which
of those values each user is granted. Here, holding `Members_CRUD` without a region grant is a
deny.

### `config#fields` — one canonical enum vocabulary (`options`), SAM-authored

**One vocabulary verb: `options` (03a).** Every selectable field — inline enum, reference, or
scope-bound — resolves to ONE canonical `options` list of rich objects
`{value, label{nl,en}, allowed, order?, roles?}`. The legacy bare `choices` key is **FORBIDDEN**
on a config field and has been removed from the write surface, the read seam, and (by the C7 +
03b migrations) stored data. `value` is the language-neutral stored key; `label` is per-language;
`allowed` is the retire/grandfather flag (see below); `order` is presentation rank.

**Three option SOURCES, one shape (design C4).** A field's `options` are assembled at ONE read
seam from one of three sources, but every consumer reads the same `{value, label, allowed, …}`
shape — no per-kind read branch:
- **inline enum** (e.g. `status`) — the field's own `options`, stored on the field.
- **reference** (e.g. `membership_type`) — ALSO the field's own inline `options` now (see the
  membership_type note below); the separate `membershiptype#` catalog is RETIRED (03b).
- **scope-bound** (e.g. `region`) — NO inline values; the resolver injects the matching
  `config#scope` dimension's values at read time (single source of truth, stored once on the
  scope dimension). `region`'s stored `options` are `null` **on purpose**.

**The retire/grandfather flag `allowed` (03b Req 3.2).** An enum option carries `allowed`
(defaults `true`). `allowed:false` = RETIRED: it is dropped from the picker for new/changed
records but an existing member that already holds the value stays valid (grandfathered). This
replaces the old reference-catalog `active=false` soft-delete — "retired" is now a feature of the
option itself, uniform across every enum.

### The `status` enum, as actually stored

Inside the `config#fields` row's `overrides` map — the rich vocabulary under the canonical
`options` key (03a; the old `choices` key + the fixed-override "`died` dropped on read" bug are
resolved — fixed and variable fields serialize the same single `options`):

```json
"membership.status": {
  "type": "enum",
  "label": { "en": "Status", "nl": "Status" },
  "order": 20,
  "required": true,
  "functional_group": "membership",
  "options": [
    { "value": "application", "label": { "en": "Application", "nl": "Aanmelding" }, "allowed": true },
    { "value": "active",      "label": { "en": "Active",      "nl": "Actief" },     "allowed": true },
    { "value": "died",        "label": { "en": "Passed away", "nl": "Overleden" },  "allowed": true }
  ]
}
```

### `membership_type` — a normal enum field, not a catalog (03b)

Under the unified enum model (03b), `membership_type` is a REFERENCE-kind field that owns its
vocabulary as its OWN inline `options` on the `config#fields` `overrides` map (dotted key
`membership.membership_type`), exactly like `status`. Each option is
`{value=type_code, label{nl,en}, allowed, order}`; a retired type is `allowed:false` (not a
separate soft-deleted record). The old `membershiptype#<code>` catalog in `sam-members`, its five
`/membership-types` CRUD routes, and its management apparatus are all **RETIRED** — the EXPAND
migration folded each tenant's catalog into the field's `options`, and the reference check +
default now read the field's options only (no catalog read on the runtime path). Member records
still store a `membership.membership_type` code reference verbatim (grandfathered).

### The four public-application attributes (`application_*`, application-app D20)

A field may carry four optional per-field attributes that drive the PUBLIC application form
(authored via the `set_field_application` Change-Op, served on the public field-config read):
- `application_visible` (bool) — the field appears on the public application form.
- `application_required` (bool) — required on the public form (the form may TIGHTEN requiredness).
- `application_choices` (list) — the public-safe SUBSET of the field's `options.value`s offered on
  the form (a strict subset of the field's own vocabulary; a dangling entry fails loud).
- `format` (`{checker, params?}`) — a declarative validator token (platform-known, e.g. `EMAIL`).

These are additive and default to "not on the form"; an unauthored field is simply absent from the
public form. They are stored alongside the field's definition attributes on the same `config#fields`
override/field entry.

---

## `sam-members` — member data, tenant library, and user preferences

The table name is a slight misnomer: it holds the whole Members MODULE's data, in **three
categories**, not just members.

- Partition key `tenant_id`, sort key `sk` (segments joined by `#`).
- One GSI: `name_dob_index` (HASH `tenant_id`, RANGE `name_dob_key`) — backs the public-intake
  possible-duplicate flag.

| Category | `sk` prefix | The JSON record holds | Keyed to |
| --- | --- | --- | --- |
| **Member data** | `member#<member_id>` | a member record | member |
| | `member#<member_id>#membership#<membership_id>` | a membership of a member | member |
| | `member#<member_id>#delegates` | a member's delegate set | member |
| | `member#<member_id>#payment#<payment_id>` | a member-scoped payment | member |
| **Tenant-shared library** | ~~`membershiptype#<type_code>`~~ | **RETIRED (03b)** — membership types are now inline `options` on the `membership_type` field (`config#fields`), not standalone rows | — |
| | `analyticsset#<set_id>` | a saved analytics-set (pivot/list definition); `set_id` is a server uuid4 | tenant |
| | `template#<template_id>` | a stored mail template (metadata; body/logo in S3) | tenant |
| | `schedule#<schedule_id>` | a recurring-run schedule (references a `set_id`) | tenant |
| **Per-user preferences** | `preflist#<sub>` | a user's ordered references into the shared set library (`preset:<key>` / `set:<id>`) | **user** (`sub`) |
| | `colprefs#<sub>` | a user's chosen overview columns (field-key list) | **user** (`sub`) |
| **Operational / transient** | `mailrun#<run_id>` | a send-run status tally | tenant |
| | `mailrecipient#<run_id>#<seq>` | a failure-only per-recipient sub-record | tenant |
| | `mailsent#<job_id>` | a mail-sent idempotency marker | tenant |
| | `appsession#<session_key>` | a public-application session de-dup marker | tenant |

Note the identity split in one table: `member#…` is keyed by `member_id` (a data subject);
`preflist#<sub>` / `colprefs#<sub>` are keyed by the Cognito `sub` (a USER). Same table, two
identity universes, no link.

### Membership-type catalog entry — RETIRED (03b)

The `membershiptype#<type_code>` catalog row no longer exists. Under the unified enum model (03b),
`membership_type` owns its vocabulary as inline `options` on the `config#fields` `membership.
membership_type` field (see "`membership_type` — a normal enum field" above). The EXPAND migration
(`sam/members/migration/membership_type_catalog_to_field_options.py`) folded each tenant's catalog
into those field options (`active` → `allowed`); the catalog rows were then retired (deleted on
TEST, 03b Task 10.1; PROD at Task 12). A member's stored `membership.membership_type` code is
untouched (grandfathered).

**h-dcn's membership types (now the field's inline `options`, verified on TEST):** 7 options —
`gewoon_lid` (10), `gezins_lid` (15), `erelid` (20, `allowed:false` — retired), `donateur` (30),
`gezins_donateur` (35), `sponsor` (40), `overig` (50).

---

## Two ways "a dropdown of values" is modelled (one source each)

| Field | Values live in | How it resolves |
| --- | --- | --- |
| `status` / `membership_type` (inline enum / reference) | the field's own `options` in `config#fields` (rich `{value,label,allowed,order}`) | served verbatim as the field's canonical `options` — same shape for fixed and variable fields |
| `region` (scope-bound variable enum) | once, on the `config#scope` dimension; the field's own `options` are deliberately `null` | injected from the scope dimension at read time (single source of truth) |

Post-03b there are only two models (the old separate `membershiptype#` catalog model is gone): a
field either carries its own inline `options`, or — for a scope-bound field — borrows the scope
dimension's values. Both resolve to the same `{value, label, …}` shape. None of it is
tenant-specific code.

---

## Verification status (honesty note)

- Table/key/record-type shapes: transcribed from `projection_schema.py`, `table_design.py`, and
  the SAM `template.yaml` — current as of writing (post-03b: `options` canonical, no `choices`;
  membership_type is an inline-options field, not a catalog).
- Split ownership of `governance_projection` (`config#*` SAM-authored via `PUT /members/config/*`;
  `tenant`/`module#`/`role#`/`scopegrant#` projected from MySQL): spec-02 `ProjectionSync` emits
  zero `config#*` rows — verified in `backend/src/services/projection_sync.py`.
- `config#scope` (region, 10 values, `required_for: ["Members_CRUD"]`): the `governance_projection`
  row for `h-dcn`.
- `config#fields` `region` field (`options` = null, injected from scope): the `config#fields` row.
- `membership_type` inline options (7, incl. `erelid` `allowed:false`): verified on **TEST**
  `test_governance_projection` `config#fields` for `h-dcn` (03b Task 10.1 gate check), after the
  7 `membershiptype#` catalog rows were deleted from `test_sam-members` (caller identity confirmed
  account 506221081911, NonprofitDeployRole). PROD retirement is Task 12.
- `role#` rows (user-tenant-role grants, keyed by login email): the `governance_projection` table.
