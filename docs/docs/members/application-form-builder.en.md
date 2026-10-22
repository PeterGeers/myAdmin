# Configure your application form

> As Tenant Admin, decide which fields appear on the public application form and how the form is shared.

## Overview

With the **form builder** you set up how your organization's public [application form](application-form.md) looks: which fields an applicant fills in, which are required, how the form is shared (address and embedding) and which consent notice applies. Here you build the side the applicant sees; for the staff side that handles applications, see [Reviewing applications](reviewing-applications.md).

The builder is a single worksheet with four panels. You work in a **working copy** and commit your changes with **Save** — individual fields are not sent separately.

!!! info
You find the builder in **Tenant Admin** → **Member Administration** → the **Application form** sub-tab. The sub-tab appears only if the Member Administration module is enabled for your tenant.

## Where the builder lives

1. Go to **Tenant Admin** → **Member Administration**.
2. Open the **Application form** sub-tab (next to *Field configuration*, *Membership types* and *Mail*).
3. The builder loads your current field configuration and your mail settings into one working copy.

!!! info
The builder and the other sub-tabs write to the same underlying configuration. You switch a field on in one place; the builder only shows the *application* side of it.

## Choosing fields (the field-list panel)

The first panel shows all available fields of your tenant, **grouped** by functional section (for example *Personal details*, *Address*, *Financial*) and in a fixed order.

- Each field has an **On the form** toggle. Turn it on to add the field to the public application form.
- **Administration fields** (meant for member administration, not for an applicant) default to **off**, but you can turn them on if you want.
- **Calculated or non-editable fields** cannot be placed on the form — they do not appear as an option.

!!! tip
Keep the form short. Only turn on the fields you truly need at application time; fill in the rest later from member administration.

## Per-field attributes (for each chosen field)

Once a field is **on the form**, you can set per-field attributes for it. These apply to the public form only:

| Attribute                 | What it does                                                                                        |
| ------------------------- | --------------------------------------------------------------------------------------------------- |
| **Required on form**      | Makes the field required for the applicant. A field the platform already marks required is locked on — you cannot relax it. |
| **Choice subset**         | On a choice-list field, pick which options the applicant sees — a **subset** of the field's own options. Leave it empty to show all options. |
| **Format (validation)**   | Attaches a validity check to the field (for example email or IBAN). You pick from the formats the platform knows, so the list always matches what the check actually supports. |

!!! info
If you put the **membership type** on the form, you offer it as required with a non-empty choice subset from your own [membership-types catalog](membership-types.md). An empty choice on a visible-and-required membership type is blocked.

!!! tip
The attributes appear only once the field is on the form. If a field is off, its attributes do not apply.

## Sharing the form (the form-shell panel)

The form-shell panel controls how the public form is reachable:

- **Public address (URL)** — the form's address is derived from your landing page's **slug**. If you have no slug yet, you see "no address yet" with a link to the [Landing Page editor](../landing-page/index.md), where you set the slug. You manage the slug there, not in the builder.
- **Embedding** — the form can appear on another page in two ways:
    - **On your own landing page** — add the form as a **block** in the [Landing Page editor](../landing-page/index.md). The form is then rendered directly as part of your own page (same styling, no iframe).
    - **On an external site** (for example a Google Site or your event portal) — use the ready-to-copy **iframe snippet** the builder generates for you. The embedded form resizes its height automatically so it is not clipped.
- **Allowed origins** — for an external embed, you list which websites may show the form in an iframe (for example `https://sites.google.com` and your event portal). If you list no origins, no external site may embed the form.
- **Consent notice** — the bilingual (NL/EN) text an applicant must agree to. Every change **bumps the version number**, so each application records exactly which text the applicant agreed to.

!!! info
You manage the slug in the [Landing Page editor](../landing-page/index.md). The **sender**, **Reply-To** and the **copy setting (scope-copy)** are configured on the **Mail** sub-tab — they are not authored in the builder; the builder only references them.

## Readiness (the readiness panel)

The readiness panel summarizes whether the form is ready to receive applications. It shows three conditions:

| Condition              | Meaning                                                                 |
| ---------------------- | ----------------------------------------------------------------------- |
| **Verified sender**    | Your tenant has a verified/certified sender for mail                    |
| **Slug (address)**     | A slug is set, so the form has a reachable address                      |
| **At least one field** | At least one field is on the form                                       |

If a condition is not met, the panel gives neutral guidance (without revealing mail settings) and a link to [Sender verification](../tenant-admin/sender-verification.md). As long as there is no verified sender, the public form shows the applicant a tidy "applications not available" message instead of a half form.

!!! info
Readiness uses the same "ready to send" signal as the public form itself. Only when all three conditions hold does the form open for applicants.

## Live preview (the preview panel)

The preview panel shows the public form **in the app**, exactly as an applicant sees it — with the same rendering as the real form. The preview follows your **working copy live**: turn a field on, make it required, or restrict its choices, and it appears in the preview immediately, before you even save.

- So you do **not** need to save to see a change in the preview — the preview reflects your unsaved edits.
- The preview is **read-only**: you cannot submit anything in it; it is for checking, not for making an application.
- Because the preview uses the same filtering and the same rendering code as the real form, you get exactly what an applicant sees — there is no separate view that can drift.

!!! info
The preview shows your **working copy** (not yet saved). The **real** public form — reachable via the **Open live form** button in the form-shell panel — reflects the **last saved** state; a saved change appears there the next time it is loaded.

!!! tip
Work in small steps: turn a field on, check it right away in the preview, and save once it looks right.

## Permissions

| Permission     | What the user can do                                              |
| -------------- | ----------------------------------------------------------------- |
| `Tenant_Admin` | Configure the application form (fields, attributes, sharing, consent) |

!!! info
Configuring the application form is reserved for the **Tenant Admin**. The configuration applies to the whole tenant, not to an individual member.

## Troubleshooting

| Problem                                        | Cause                                                        | Solution                                                                  |
| ---------------------------------------------- | ------------------------------------------------------------ | ------------------------------------------------------------------------- |
| "No address yet" for the public address        | No slug has been set yet                                     | Set a slug via the [Landing Page editor](../landing-page/index.md)        |
| The form does not open for applicants          | No verified sender (readiness not met)                       | Verify a sender via [Sender verification](../tenant-admin/sender-verification.md) |
| The required toggle is locked on               | The platform already marks this field required              | This is intentional — a platform-required field cannot be relaxed         |
| Choice subset not available on a field         | The field is not a choice-list field                         | A choice subset applies only to fields with options                       |
| Live form shows an old state                   | The *live* form reflects the last saved state (the preview shows the working copy) | Click **Save**; the change appears on the live form the next time it is loaded |
| Application form sub-tab is missing            | The Member Administration module is not enabled              | Ask your SysAdmin to enable the module for your tenant                    |
