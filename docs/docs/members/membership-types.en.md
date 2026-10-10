# Membership types

> The membership types (the "catalog") your tenant uses for members.

## Overview

Every member is assigned a **membership type** (for example *Ordinary member*, *Honorary member*, or *Youth member*). Together, the available types form your tenant's **membership-type catalog**, also referred to as **Lidmaatschap Beheer**. This catalog is tenant-specific: the types are not a fixed, built-in list but are managed per organization.

Where you encounter the catalog:

- In the **New member** / **Edit** form, the **Membership type** dropdown is filled with the types from this catalog. See [Managing members](managing-members.md).
- In the Members Overview you can filter and sort on **Membership type**.

## Active and archived types

Each type is either **active** or **archived** (retired):

| Status    | Meaning                                                                   |
| --------- | ------------------------------------------------------------------------- |
| Active    | The type is assignable: it appears in the dropdown when adding/editing     |
| Archived  | The type is retired: it no longer appears in the dropdown, but is kept for existing members and history |

!!! info
A type is never "hard" deleted. Retiring it is an **archive** (setting it inactive): members already on that type and the history stay correct. This prevents discarding a type that still has members attached to it.

!!! tip
Want to stop using a type for new members but keep it for existing ones? Archive it instead of changing it. New applications no longer offer the type, while existing members remain unchanged.

## Managing the catalog

Creating, editing, and archiving membership types is a **management task**: it falls under the `Members_CRUD` permission (the administrative/management rights within Member Administration) and is reserved for administrators. It changes the type vocabulary for the whole tenant, not a single member.

Each type records, among other things, a reference code (the value stored on a member) and a display name (NL/EN).

!!! info
Managing the catalog is an administrative function. If you do not have the management rights (`Members_CRUD`), you can still see the types in the dropdowns and filters, but you cannot create, edit, or archive them. In that case, ask your Tenant Admin.

## Troubleshooting

| Problem                                   | Cause                                             | Solution                                                       |
| ----------------------------------------- | ------------------------------------------------- | -------------------------------------------------------------- |
| A type is missing from the dropdown       | The type is archived (inactive)                   | Set the type active again (requires `Members_CRUD`)            |
| An archived type cannot be removed        | Types are archived, never hard deleted            | This is intentional — existing members and history stay correct |
| You cannot manage types                   | You do not have the `Members_CRUD` permission     | Ask your Tenant Admin for the management rights                |
