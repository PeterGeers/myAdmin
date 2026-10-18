# Members configuration — tenant-admin guide

Plain-language guide to what a tenant administrator configures for the Members module, and where
each piece lives. For the technical shapes (tables, keys, item formats) see
[`data-model.md`](./data-model.md).

> Two places author config, and that split causes most of the confusion:
> - **Flask Tenant Admin** authors FIELD config (the member form: fields, labels, dropdowns),
>   plus scope and mail. Saved in MySQL, then COPIED ("projected") to the module to read.
> - **The Members module** owns the **membership-type catalog** (Lidmaatschap Beheer) directly.

---

## First: users are not members

Two different kinds of person, with **no link** between them:

- A **user** has a login (Cognito) and **access rights** — they can sign in and work with the
  data (e.g. do member CRUD, finance CRUD). Users and their roles are managed in the identity
  system (`user_tenant_roles`), not here.
- A **member** is a person recorded in the club's data, with a member id and many attributes.
  Being a member grants **no** access to the dataset — a member is data, not a login.

The same human can be both (an admin who is also a member), but the system never ties the two
together. Keep this in mind: "field config," "scope," and "roles" below are about USERS and the
data they may see — not about members themselves.

---

## 1. Fields and their dropdowns (Flask Tenant Admin)

The member form is a set of fields — some platform fixed fields (e.g. `status`), some you add
yourself ("club detail" fields). Per field you set label, order, required/visible, and — for a
dropdown (enum) field — its allowed values.

- Dropdown values are stored **inline on the field** (each value = a code + nl/en label).
- Your edit is saved in MySQL, then **projected** to the module. The member app reads the
  projected copy — so if a new value doesn't appear, the projection is behind your edit, not the
  reverse.
- `status` is a fixed field whose values (Aanmelding / Actief / … / Overleden) you edit here.

> Known bug: a newly added value on a FIXED field's dropdown (e.g. adding "Overleden"/`died` to
> `status`) may not appear in the app — the module currently drops fixed-field override values on
> read. Tracked in `.kiro/specs/Members/application-app/issues_found.md`.

## 2. Scope — who may see which members (access control)

Scope restricts users who should NOT see the whole dataset to only the slice they're granted. It
is an ACCESS feature, not a member attribute.

- You define one or more **scope dimensions** (h-dcn uses one: `region`).
- A dimension lists its allowed values, and which capabilities **require** a grant (without one,
  access is denied).
- Each user is then granted specific values (e.g. "Jan may see Limburg and Oost").

h-dcn's live `region` scope (10 values): **Brabant/Zeeland, Duitsland, Friesland, Geen,
Groningen/Drenthe, Limburg, Noord Holland, Oost, Utrecht, Zuid Holland** — and holding the
`Members_CRUD` capability **requires** a region grant.

Single-list rule: the `region` member FIELD intentionally has no values of its own — it reuses
the scope dimension's values. You maintain the list in ONE place (the scope config), and the
field's dropdown borrows it. No duplicate list to keep in sync.

## 3. Membership types — the Lidmaatschap Beheer catalog (owned by the module)

Membership types are **not** an inline dropdown. Each type is its own managed record; a member's
`membership_type` references one by its code.

- Tenant-owned, empty by default; h-dcn's types were seeded as data.
- Retiring a type is a **soft-delete** (`active=false`): it leaves the dropdown for new/edited
  members but existing members keep their type.
- Ordered by `order`, then code.

h-dcn's live catalog (7 active types):

| order | code | Nederlands | English |
| --- | --- | --- | --- |
| 10 | `gewoon_lid` | Gewoon lid | Regular member |
| 15 | `gezins_lid` | Gezinslid | Family member |
| 20 | `erelid` | Erelid | Honorary member |
| 30 | `donateur` | Donateur | Donor |
| 35 | `gezins_donateur` | Gezinsdonateur | Family donor |
| 40 | `sponsor` | Sponsor | Sponsor |
| 50 | `overig` | Overig | Other |

> Authoring gap (known): there is currently **no UI** to manage this catalog. The 7 entries were
> seeded as data; adding/retiring a type today means editing the catalog record directly.

## 4. Mail (Flask Tenant Admin)

The per-tenant mail-enabled gate and sender identity. Projected; the module reads it to decide
whether to offer mail actions.

---

## Why "it looks like one dropdown but behaves differently"

In the member form, `status`, `region`, and `membership_type` all look like dropdowns, but each
is stored a different way:

- **`status`** — inline values on the field (authored in Flask, projected).
- **`region`** — values come from the scope config (access control), reused by the field.
- **`membership_type`** — a reference to a separate catalog record the module owns.

Three storage models behind one familiar control. That is why they aren't managed the same way —
expected, not a bug.
