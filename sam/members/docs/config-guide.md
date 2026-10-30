# Members configuration — tenant-admin guide

Plain-language guide to what a tenant administrator configures for the Members module, and where
each piece lives. For the technical shapes (tables, keys, item formats) see
[`data-model.md`](./data-model.md).

> Where config is authored (post-03b / spec-02):
> - **Member field config** (the member form: fields, labels, dropdowns), **scope**, and **mail**
>   are authored by the **Members module itself** and saved directly to its config
>   (`config#fields` / `config#scope` / `config#mail`) — NOT copied from MySQL any more.
> - **Membership types** are just a regular dropdown (enum) field now — edited inline on the
>   `membership_type` field like any other dropdown. The old separate "membership-type catalog"
>   (Lidmaatschap Beheer) and its lack of a UI are **gone** (03b).
> - Only **user access** — logins, roles, and per-user scope grants — still comes from the
>   identity system (MySQL `user_tenant_roles`), projected to the module read-only.

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

## 1. Fields and their dropdowns (Members Tenant Admin)

The member form is a set of fields — some platform fixed fields (e.g. `status`), some you add
yourself ("club detail" fields). Per field you set label, order, required/visible, and — for a
dropdown (enum) field — its allowed values.

- Dropdown values are stored **inline on the field** (each value = a code + nl/en label). One
  canonical list per field — there is a single way to store a field's vocabulary now.
- Each value also carries an **"allowed"** flag. Turning a value OFF ("retire") removes it from
  the dropdown for new/edited members, but members who already have that value keep it
  (grandfathered). This is how you retire a type without breaking existing records.
- `status` is a fixed field whose values (Aanmelding / Actief / … / Overleden) you edit here —
  and a newly added fixed-field value now shows correctly in the app (the earlier "Overleden"/
  `died`-not-appearing bug is fixed).
- Your edit saves directly to the module's own config and takes effect on the next read — there
  is no MySQL copy / projection delay for field config any more.

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

## 3. Membership types — a regular dropdown field (03b)

Membership types are now just the values of the `membership_type` dropdown field — edited inline
in the field config exactly like any other enum (section 1), each value a code + nl/en label with
an "allowed" flag. There is no separate "catalog" and no missing UI any more: you add, relabel,
reorder, and retire types right on the field.

- A member's `membership_type` stores the value's code (e.g. `erelid`), as before.
- **Retiring** a type = turn its "allowed" flag OFF: it leaves the dropdown for new/edited
  members, existing members keep it (grandfathered). (This replaced the old `active=false`
  soft-delete on the separate catalog.)
- Ordered by `order`, then code.

h-dcn's membership_type values (now inline options on the field):

| order | code | Nederlands | English | allowed |
| --- | --- | --- | --- | --- |
| 10 | `gewoon_lid` | Gewoon lid | Regular member | yes |
| 15 | `gezins_lid` | Gezinslid | Family member | yes |
| 20 | `erelid` | Erelid | Honorary member | **no (retired)** |
| 30 | `donateur` | Donateur | Donor | yes |
| 35 | `gezins_donateur` | Gezinsdonateur | Family donor | yes |
| 40 | `sponsor` | Sponsor | Sponsor | yes |
| 50 | `overig` | Overig | Other | yes |

> History: these were previously standalone `membershiptype#` catalog records with no management
> UI. 03b folded them into the field's own options and retired the catalog, so they are now
> managed like every other dropdown.

## 4. The public application form (per-field)

For a public member-application form, each field has four extra toggles: put it **on the form**,
make it **required on the form**, offer only a **subset** of its dropdown values publicly, and
attach a **format check** (e.g. email). These are set per field in the application-form builder;
an unauthored field simply isn't on the public form.

## 5. Mail (Members Tenant Admin)

The per-tenant mail-enabled gate and sender identity, authored in the module's typed Mail config.
The module reads it to decide whether to offer mail actions.

---

## Why `region` behaves differently from the other dropdowns

In the member form, `status`, `membership_type`, and `region` all look like dropdowns. Post-03b
`status` and `membership_type` are the SAME kind — plain inline values on the field, edited the
same way (section 1 / section 3). Only `region` is special:

- **`status` / `membership_type`** — inline values on the field (code + nl/en label + allowed).
- **`region`** — has NO values of its own; it reuses the **scope** config's values (section 2),
  so you maintain that list once (as access control) and the field borrows it.

So there are only two models now: a field's own inline values, or (for `region`) the scope list it
borrows. Expected, not a bug.
