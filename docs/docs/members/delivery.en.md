# Sending & delivery

> Mail an analytics result, use templates, store a delivery on a set, run it on a schedule, and make address labels.

## Overview

Once you have run a pivot view on the [Analytics](analytics.md) page, you can do more with the result than just export it to CSV and mail it:

- **mail a result to an external address** that is not in the member list;
- pick a stored **template** so you don't retype the message each time;
- store a fixed **delivery** on a **saved set**, so running or scheduling it repeats the send without re-entering everything;
- **run a delivery now** (the send happens in the background);
- run a delivery on a **schedule** (for example monthly);
- make **address labels** straight from a result.

!!! info
Mailing is only available once your tenant is cleared to send. Your Tenant Admin sets this up once by verifying a sender address — see [Sender verification](../tenant-admin/sender-verification.md). Until that clearance is in place, you do not see the mail actions.

!!! info
You always work within your own **region scope**. A delivery can only send what you could already export within your scope; no new permission is added.

## Mailing to an external address

Sometimes you want to mail a result to someone who is **not** in the member list — for example a print shop, a mailing service, or a board member who just gets the overview for information.

The mail dialog (the **Mail** button below a result) has an **External recipients** field for exactly that:

1. Run the result on the [Analytics](analytics.md) page and click **Mail**.
2. In the **External recipients** field, type one or more email addresses that are not in the dataset.
3. Set the subject and message (or pick a template — see below).
4. Optionally choose an attachment: the **CSV file** and — if your tenant has mapped address fields — **PDF address labels**.
5. Send.

!!! info
Attachments work exactly as you are used to: CSV for both counts and lists, and PDF address labels if your tenant has mapped the address fields.

!!! tip
You can combine external recipients with the regular send; the external address gets the same email with the same attachments.

## Using templates

A **template** is a stored, named message (NL/EN) that pre-fills the subject and body, so you don't have to retype it every time.

### Picking a template in the mail dialog

1. Open the mail dialog via **Mail**.
2. Pick a template in the **Template** dropdown.
3. The subject and body are filled in. You can still **edit** them before you send.

!!! info
A template may contain **merge fields** (for example the first name). On send, those are filled per recipient from that member's row.

### Managing templates

You manage your templates in template management:

- **Create** — make a new template with a name, subject, and body (NL and/or EN).
- **Edit** — change an existing template.
- **Delete** — remove a template you no longer use.
- **Upload** — upload a ready-made template.

A template may also include a **logo** from your tenant's branding.

### Improve with AI

While editing a template you can use **Improve with AI**: you give a short instruction (for example "make the tone friendlier" or "shorter"), and the text is rewritten for you. You stay in control — you see the result and can adjust or discard it.

!!! info
The AI **never sees member data**. Only the template text (and the branding) go to the AI, never your members' names, addresses, or other data. Merge fields are filled only *after* the AI step, at send time.

!!! info
Only **free** AI models are used. If the AI cannot help, you simply keep your original text — nothing bad happens.

## Storing a delivery on a saved set

On a [saved set](analytics.md) you can configure a **delivery**: the set then remembers what to do with its result. That way you repeat the send (manually or on a schedule) without re-entering everything.

A delivery has two **modes**:

| Mode          | What it does                                                                                      |
| ------------- | ------------------------------------------------------------------------------------------------- |
| Per recipient | Mail each member in the result individually, with **real mail-merge**: the template's merge fields are filled per member, so everyone gets a personalized email. Addresses come from the data and are not stored separately. |
| To fixed      | Send the result as an **attachment** to a fixed list of addresses (often one).                    |

You configure a delivery on the set:

1. Choose the mode (**Per recipient** or **To fixed**).
2. **Per recipient:** choose the template each member is mailed with.
3. **To fixed:** fill in the fixed recipient list and choose the attachment.

!!! info
For **To fixed**, the attachment is the **CSV file**. (PDF address labels as a per-recipient attachment are not yet available for a server-side delivery; for labels, use the [Generate address labels action](#making-address-labels) or the PDF attachment in the mail dialog for now.)

!!! info
Old sets without a delivery keep working. The delivery is separate from the pivot definition — you change nothing about how the set calculates.

## Running a delivery now

If a set has a delivery, you can run it straight away with **Run now**:

- The send is **queued** and sent in the background. Your window does not hang on a long send, and a large run cannot time out.
- The send **respects the send limits**: it goes out at the right pace, so the mail service's limits are not exceeded.

!!! info
Every send is recorded in the audit log (metadata only, no message content) — including the runs that happen automatically on a schedule.

## Running on a schedule

You can run a saved set with a delivery on a **schedule**, so a recurring send happens on its own.

1. Make sure the set has a **delivery** (see above).
2. Attach a schedule to the set, for example **monthly** or **weekly**.
3. Turn the schedule **on** (and later **off** again).

!!! warning
Scheduling is reserved for users with **tenant-wide** member access: a **Tenant Admin**, or a user with edit rights (`Members_CRUD`) **and** full (tenant-wide) access. A user restricted to a single region **cannot** schedule — an unattended run must never accidentally send only part of the tenant.

!!! info
A scheduled run always operates **tenant-wide**. The tenant is pinned in the schedule and the send uses the same background processing as **Run now**.

## Making address labels

Besides the PDF attachment in the mail dialog, you can also make address labels **straight from a result**, with the **Generate address labels** action (next to CSV and Mail below a result).

1. Run the result on the [Analytics](analytics.md) page.
2. Click **Generate address labels**.
3. Choose the **Avery format** and the options (such as sort, font size, alignment, border, country, and the start position on the sheet).
4. Download the PDF with the labels.

!!! tip
The action is only available if your tenant has **mapped the address fields** (name, street, postal code, city, country) and you have the export permission. If that mapping is missing, CSV export still works.

## Permissions

| Permission                               | What the user can do                                                             |
| ---------------------------------------- | -------------------------------------------------------------------------------- |
| `Members_Export` (or `Members_CRUD`)      | Mail results (incl. external recipients), attach CSV, generate address labels, configure a delivery on a set, and **Run now** |
| `Members_Export` or `Members_CRUD`       | Create, edit, delete, upload templates, and improve with AI                      |
| `Members_Admin`, or `Members_CRUD` with full access | Attach a schedule to a set and turn it on/off                         |

!!! info
A delivery uses no new permission: what you can send is bounded by your export permission and your region scope — exactly what you could already export yourself.

## Configuration dependencies

- **Sender verification (clearance to mail)** — the mail actions only appear once your Tenant Admin has verified a sender address and your tenant is cleared. See [Sender verification](../tenant-admin/sender-verification.md).
- **Address mapping** — enables the address labels (both the action and the PDF attachment).

## Troubleshooting

| Problem                                   | Cause                                              | Solution                                                       |
| ----------------------------------------- | -------------------------------------------------- | -------------------------------------------------------------- |
| No mail actions visible                   | Your tenant is not yet cleared to mail             | Have your Tenant Admin verify a sender address                 |
| No **External recipients** field          | You do not have the export permission              | Ask your Tenant Admin for `Members_Export`                     |
| No **PDF address labels** attachment       | Your tenant has not mapped address fields          | Have the address mapping added; CSV works in the meantime      |
| No **Generate address labels** action      | No address mapping, or no export permission        | Have the address mapping added and ask for `Members_Export`    |
| I cannot set up a schedule                | Scheduling requires tenant-wide access             | Ask a Tenant Admin, or full access with edit rights            |
| An improve-with-AI did not happen         | The AI step did not succeed                        | Your original text stays; try again later                      |
| A scheduled send did not run              | The schedule is off, or the set has no delivery    | Turn the schedule on and check that the set has a delivery     |
