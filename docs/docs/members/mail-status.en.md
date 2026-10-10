# Mail status

> See what happened to a send — queued, sent, or failed — with per-run detail and the failed addresses.

## Overview

A send from [Member Administration](delivery.md) happens in the **background**: your window does not hang on a long run. The **Mail status** screen then shows you what happened to each send. That way the background processing is not a black box — you can look back and, if something went wrong, see which address failed and why.

!!! info
Mail status is a **pull screen**: you open it yourself when you want to check. So you do not get a "your send failed" email — the outcome is waiting on this screen.

## Opening the screen

You open **Mail status** on the [Analytics](analytics.md) page, next to the entry point for your saved sets (**All sets**). The screen shows a **list of runs**: every send you started (or, if you are a Tenant Admin, that anyone in your tenant started).

!!! info
The mail actions, and therefore the runs, only appear once your tenant is cleared to mail. See [Sender verification](../tenant-admin/sender-verification.md).

## The list of runs

Per run you see a summary with the key tallies:

| Column       | Meaning                                                                 |
| ------------ | ----------------------------------------------------------------------- |
| Description  | What the run belongs to (for example the set or template name)          |
| When         | The time the run started                                                |
| Mode         | **Per recipient** or **To fixed** (see [Sending & delivery](delivery.md)) |
| Count        | The number of recipients in the run                                     |
| Sent         | How many messages the mail service **accepted**                         |
| Failed       | How many could not be sent                                              |
| Status       | **Queued** → **Sending** → **Completed**                                |

A completed run reads, for example, as: *Newsletter — 198 sent, 2 failed*.

!!! warning
**"Sent" means: accepted by the mail service — not "delivered to the inbox".** The mail service accepting a message is not proof that it reached the recipient's inbox. A message can still **bounce** afterwards or be marked as a **complaint**. Such late outcomes appear only after the run, among the failed addresses (see below), and adjust the tallies.

## Drilling into a run

Click a run to open its detail. The summary only counts the successful recipients; the **failed addresses** are shown individually:

| Field    | What you see                                                            |
| -------- | ----------------------------------------------------------------------- |
| Address  | The email address that was not (properly) delivered                     |
| Status   | **Failed**, **Bounced**, or **Complaint**                               |
| Reason   | Why it went wrong (for example an unknown address, a rejected message, or a full mailbox) |

!!! info
Only **failed** addresses are stored individually; the successful recipients are only counted. That keeps the screen tidy and free of unnecessary member data.

!!! info
An address with no usable email (in **Per recipient** mode) is **skipped** and reported as failed — a single missing row like that lets the rest of the run continue.

## Deleting a run

You can **delete** a run from the list with the delete action. A **confirmation** follows first, so you don't throw something away by accident.

!!! info
Runs are also **cleaned up automatically** over time (90 days by default). That covers a few monthly newsletter cycles to look back on; after that the small metadata disappears on its own. The manual delete action is there for when you want it gone sooner.

## Who sees which runs

The runs are scoped **per tenant**, and within that depend on your role:

| Role           | What you see in Mail status                                 |
| -------------- | ----------------------------------------------------------- |
| Regular user   | **Your own** sends                                          |
| `Tenant_Admin` | **All** of the tenant's sends (oversight)                   |

!!! info
It is the same data, only scoped differently: a regular user sees their own runs, a Tenant Admin sees the whole tenant's for oversight. Nobody ever sees another tenant's runs.

## Configuration dependencies

- **Sender verification (clearance to mail)** — without clearance there are no mail actions and therefore no runs. See [Sender verification](../tenant-admin/sender-verification.md).

## Troubleshooting

| Problem                                   | Cause                                              | Solution                                                       |
| ----------------------------------------- | -------------------------------------------------- | -------------------------------------------------------------- |
| I don't see the Mail status screen        | Your tenant is not yet cleared to mail             | Have your Tenant Admin verify a sender                         |
| A run stays on **Queued**                 | The background processing is still working         | Wait a moment and refresh; large runs are sent at a safe pace  |
| An address shows **Failed**               | Unknown/invalid address, or the message was rejected | Check the address against the reason; correct it and resend  |
| An address later **bounced** anyway       | The mail service accepted it, but it bounced afterwards | This is normal: "sent" = accepted, not delivered           |
| I only see my own runs                    | You are not a Tenant Admin                         | Only a Tenant Admin sees all of the tenant's runs              |
