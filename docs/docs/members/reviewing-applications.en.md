# Reviewing applications

> View new applications, recognize the markers, and approve them into membership.

## Overview

When someone fills in the public [application form](application-form.md), the application lands as a member with status *Applied* ("Application"). There is **no separate screen** for applications: the "applications inbox" is simply the familiar **Member Overview**, filtered to status *Applied*. Everything stays in one trusted table.

Reviewers with an all-regions (`Regio_All`) `Members_CRUD` permission receive an email for each new application, with a deep-link to the record. That email is **best-effort**: even if the mail does not arrive, the application is still in the overview. The overview is the source of truth, not the email.

## What you need

- `Members_Read` to view applications
- `Members_CRUD` to approve an application (status transition) or delete it

## Opening the applications inbox

1. Go to **Member Administration** → **Overview**
2. Filter the **Status** column to *Applied* ("Application")
3. The table now shows only the open applications

!!! tip
Save this filter as a view so you can reach it in one click. See [Filters & views](filters-and-views.md).

## Markers: `DUP` and `NO_NOTIFY`

Some applications carry a **marker** in the *Additional information* field (`overlay.additional_info`). These are keywords you can filter on:

- **`DUP`** — possible duplicate application. The system found an existing member with the same **name + date of birth**. The application was still created (the marker never blocks); check whether it is the same person before approving.
- **`NO_NOTIFY`** — no one could be notified by email about this application (no all-regions `Members_CRUD` and no `TenantAdmin` fallback). The application is present; handle it manually.

!!! info
These markers are visible only on the staff side. The applicant never sees them, and the applicant confirmation does not change because of them — so the `DUP` marker is not a leak that reveals whether someone is already a member.

!!! tip
Filter on the keyword `DUP` to review all possible duplicates at once, or on `NO_NOTIFY` to find applications no one has seen by email.

## Reviewing an application

1. Click the application's row to view the submitted details (read-only)
2. Check the details and any `DUP` marker
3. If the application is in order, **approve it via a status transition**: move the member from *Applied* to, for example, *Active*

Approving is therefore not a separate button but a **status change** — the same transition used elsewhere in member administration. Which target statuses are available is determined by your tenant's lifecycle. See [Status & transitions](transitions.md).

!!! tip
Approve several applications at once: filter on status *Applied*, select the rows, and use the bulk status transition to *Active*. See [Status & transitions](transitions.md).

## Rejecting or cleaning up an application

If you do not want to approve an application, delete the record via **Delete** (see [Managing members](managing-members.md)). Deleting open applications is a manual action and is reserved for an all-regions `Members_CRUD` user.

!!! warning
Deleting cannot be undone. There is deliberately no automatic deletion of open applications, so an approved member never disappears by accident.

## Troubleshooting

| Problem                               | Cause                                                   | Solution                                                         |
| ------------------------------------- | ------------------------------------------------------- | ---------------------------------------------------------------- |
| No applications visible               | The status filter is not set to *Applied*               | Filter the **Status** column to *Applied*                        |
| No email for an application           | You lack all-regions `Members_CRUD`, or the application carried `NO_NOTIFY` | Check the overview itself; the overview is the source of truth |
| Cannot approve                        | You only have `Members_Read`                            | Ask your Tenant Admin for `Members_CRUD`                         |
| Duplicate applications (`DUP`)        | Name + date of birth match an existing member           | Check whether it is the same person; approve one, delete the rest |
