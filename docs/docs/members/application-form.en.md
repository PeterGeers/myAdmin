# Application form (public)

> The public form a prospective member uses to apply on their own, without signing in.

## Overview

The **application form** is a public web page where a prospective member can apply to your organization themselves — no account, no sign-in. After submitting, the application lands as a member with status *Applied* ("Application"), and the reviewers within the tenant receive an email.

This page describes what the **applicant** sees and does. For the staff side that reviews applications, see [Reviewing applications](reviewing-applications.md).

!!! info
The form is per tenant: each organization has its own address (a slug, e.g. `yourorg`). The application always lands with the correct organization — the applicant cannot choose or forge this.

## What the applicant sees

### The fields

The form is **not fixed**: it shows exactly the fields the Tenant Admin marked as visible on the application form. Fields are grouped into sections (for example *Personal details*, *Address*, *Financial*). Common fields are:

- **Email address** — always required and validated
- **Name** and **date of birth** — always required
- Optionally a **membership type**, if the organization put it on the form (the applicant then picks from a limited, public-safe list)
- Address, region, or other fields, depending on the configuration

Some fields appear only after you make a certain choice (conditional fields). Required fields are marked; you can only submit once they are complete and valid. Errors are shown per field, next to the field in question.

!!! info
If you choose a **direct-debit / payment option**, an IBAN field appears that is validated (mod-97).

### Language

At the top you choose the **language** of the form (Dutch or English). The default is Dutch. The chosen language also drives the language of the confirmation email.

### Consent

Before you can submit, you must tick the organization's **consent statement** (privacy/processing). This is required — without agreement the application is not submitted. The text is per organization and is recorded with a version number on your application, so it is exactly known what you agreed to.

### Submitting and the confirmation email

After **Submit**, a neutral confirmation appears on screen. You also receive a **confirmation email** at the address you provided, with a copy of what you filled in, in the language you chose.

!!! tip
If you adjust your application and resubmit within the same session, your existing application is **updated** — no duplicate application is created. A double-click on *Submit* also results in a single application.

## "Applications not available"

Sometimes the form does not open and you see a message that the organization is **not accepting applications** right now. That means the organization has not yet set up a verified email sender — without that sender an applicant could not be reliably confirmed, so the form is deliberately closed.

This is a setting on the organization's side. The administrator resolves it by verifying a sender — see [Sender verification](../tenant-admin/sender-verification.md). After that the form opens automatically.

## Troubleshooting

| Problem                              | Cause                                                      | Solution                                                            |
| ------------------------------------ | ---------------------------------------------------------- | ------------------------------------------------------------------- |
| Form does not open / "not available" | The organization has no verified sender yet                | The administrator verifies a sender ([Sender verification](../tenant-admin/sender-verification.md)) |
| Page not found (404)                 | The link/slug is wrong or the organization does not exist  | Check the link you received from the organization                   |
| **Submit** does not work             | A required field is empty or invalid, or consent is not ticked | Fill in the marked fields and tick the consent box              |
| No confirmation email received       | Wrong email address, or the mail is in spam                | Check your spam folder; otherwise contact the organization          |
