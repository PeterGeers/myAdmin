# Members module — data model (DynamoDB)

Technical reference for what the Members module stores in DynamoDB: tables, keys, record types,
and item shapes. For the plain-language admin view see [`config-guide.md`](./config-guide.md).

> Scope: the SAM/module plane only. The Flask/MySQL plane (`parameters` table, the authored
> `members.*` config) is the SYSTEM OF RECORD for projected config; this document describes how
> that config, once projected, and the module's own data, live in DynamoDB. Tenancy here is
> `tenant_id` (the partition key) — never `administration` (that is the MySQL plane).
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
| `governance_projection` | Projected tenant CONFIG (scope, fields, mail) + access/scope grants | Flask projection writer (one-directional) | SAM module (read-only) | **MySQL** (`parameters` / `user_tenant_roles`) — this is a copy |
| `sam-members` | The module's OWN data: member records + tenant-shared library + per-user preferences | SAM module (read/write) | SAM module | **this table** |

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
| `config#scope` | the tenant's scope dimensions (access axes) | tenant | `parameters` (`members.scope_dimensions`) | **Tenant_Admin** |
| `config#fields` | field overlay: `fields` (added variable fields) + `overrides` (fixed-field overrides) + `functional_groups` + `default_page_size` | tenant | `parameters` (`members.field_overlay`, `default_page_size`) | **Tenant_Admin** |
| `config#mail` | the mail-enabled gate + sender fields | tenant | `parameters` (`members.mail_enabled` + sender) | **Tenant_Admin** |
| `config#views` | **RETIRED** — dead residue; no builder emits it, no code reads it (a cleanup routine only DELETES leftovers) | — | — | nobody (retired) |

**Who manages what (lifecycle):** **SysAdmin bootstraps** a tenant — creates the `tenant` row,
enables its `module#<name>` rows, and invites the **Tenant_Admin**. The **Tenant_Admin** then runs
everything else for that tenant: user role grants (`role#`), per-user scope grants
(`scopegrant#`), and all member config (`config#scope` / `config#fields` / `config#mail`). Nobody
manages `config#views` (retired). All of it is authored in **Flask** (UI → MySQL) and projected
here read-only; no one edits `governance_projection` directly.

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

### `config#fields` — and the single-vocabulary rule for scope-bound enums

`region` is ALSO a member field (an added variable enum in `config#fields.fields`), but its stored
`choices`/`options` are **`null` on purpose**. By design (D1a / "scope_vocab"), a scope-bound enum
field declares NO inline values; the resolver injects the values from the matching `config#scope`
dimension at read time. So the region vocabulary is stored **once** (on the scope dimension) and
reused by the field — a single source of truth, not a duplicate. (Caveat: this only renders if the
caller passes `scope_vocab` to the resolver on that read path.)

### The `status` enum, as actually stored

Inside the `config#fields` row's `overrides` map (verified from the live TEST `parameters` row for
`h-dcn`). The vocabulary sits under the key **`choices`** as rich objects:

```json
"membership.status": {
  "type": "enum",
  "label": { "en": "Status", "nl": "Status" },
  "order": 20,
  "required": true,
  "functional_group": "membership",
  "choices": [
    { "value": "application", "label": { "en": "Application", "nl": "Aanmelding" } },
    { "value": "active",      "label": { "en": "Active",      "nl": "Actief" } },
    { "value": "died",        "label": { "en": "Passed away", "nl": "Overleden" } }
  ]
}
```

> Naming caveat: the domain model (`sam/members/domain`) calls the RICH representation `options`
> and the BARE string list `choices`, but the stored data puts rich objects under `choices`. For
> a FIXED-field override this vocabulary is currently dropped on read (the `died`-not-showing
> bug) — an open issue, see `.kiro/specs/Members/application-app/issues_found.md`. Recorded here
> so the doc matches reality, not the ideal.

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
| **Tenant-shared library** | `membershiptype#<type_code>` | Lidmaatschap Beheer catalog entry (membership type) | tenant |
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

### Membership-type catalog entry

`membershiptype#<type_code>` item (domain attrs from `MembershipTypeEntry.to_item`; PK/SK stamped
by the repository). Example — a LIVE `sam-members` row for `h-dcn`:

```json
{
  "tenant_id": "h-dcn",
  "sk": "membershiptype#erelid",
  "type_code": "erelid",
  "label": { "nl": "Erelid", "en": "Honorary member" },
  "active": true,
  "order": 20
}
```

Rules: `type_code` is non-blank and contains no `#` (it is a sort-key segment and the reference
key member records store in `membership.membership_type`); `label` must carry at least a non-blank
`nl`; `active=false` is the soft-delete; `order` is an integer (presentation order).

**h-dcn's live catalog (production `sam-members`, verified):** 7 active entries —
`gewoon_lid` (10), `gezins_lid` (15), `erelid` (20), `donateur` (30), `gezins_donateur` (35),
`sponsor` (40), `overig` (50).

---

## Three ways "a dropdown of values" is modelled (why it looks confusing)

| Field | Values live in | Resolves correctly? |
| --- | --- | --- |
| `status` (fixed-field override) | rich objects under `choices` in `config#fields` | **No** — dropped on read for fixed overrides (the `died` bug) |
| `region` (scope-bound variable enum) | once, on the `config#scope` dimension; the field is deliberately empty | **Yes, by design** — injected via `scope_vocab`, if the caller passes it |
| `membership_type` (reference) | catalog entities in `sam-members` (`membershiptype#…`) | separate model — the member stores a `type_code` reference |

Same-looking dropdowns, three different storage models. This is a comprehension cost, not a
correctness defect (except the `status` item above). None of it is tenant-specific code.

---

## Verification status (honesty note)

- Table/key/record-type shapes: transcribed from `projection_schema.py`, `table_design.py`, and
  the SAM `template.yaml` — current as of writing.
- `config#scope` (region, 10 values, `required_for: ["Members_CRUD"]`): the **production**
  `governance_projection` row for `h-dcn`.
- `config#fields` `region` field (`choices`/`options` = null): the production `config#fields` row.
- `status` / `membership.status` (7 `choices` incl. `died`): the live **TEST** `parameters` row
  for `h-dcn` (local Docker).
- Membership-type catalog (7 active entries): the **production** `sam-members` table
  (nonprofit-deploy, caller identity confirmed account 506221081911).
- `role#` rows (user-tenant-role grants, keyed by login email): the production
  `governance_projection` table.
