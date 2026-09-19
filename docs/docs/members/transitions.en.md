# Status & transitions

> Move one member or several members at once to another membership status.

## Overview

Every member has a membership status (for example *Applied*, *Active*, or *Terminated*). A status change is called a **transition**. You can run a transition for a single member or for several members at once (bulk).

Which statuses you can choose as a target is determined by your tenant's configured **lifecycle**. You only see the transitions that are allowed from the current status.

## What you need

- `Members_CRUD` permission

## Single member: change status

1. Go to **Member Administration** → **Overview**
2. Open the member and choose **Change status**
3. Choose a target status from the list of allowed transitions
4. Confirm the change

The new status is immediately visible in the **Status** column.

!!! info
The list of target statuses is not fixed: it comes from the lifecycle configured for your tenant. From a given status, only certain follow-up statuses are possible.

## Multiple members: bulk transition

1. Go to **Member Administration** → **Overview**
2. Select the rows of the members you want to change (checkboxes per row)
3. Choose the bulk action **Change status**
4. Choose the target status
5. Confirm the change

The status change is applied to all selected members.

!!! tip
Combine bulk transitions with filters: filter on status *Applied*, for example, select the members you want to approve, and set them to *Active* in one go. See [Filters & views](filters-and-views.md).

!!! warning
A bulk transition affects all selected rows. Check your selection before you confirm.

## Troubleshooting

| Problem                          | Cause                                            | Solution                                                       |
| -------------------------------- | ------------------------------------------------ | -------------------------------------------------------------- |
| Desired target status is missing | The transition is not allowed from the current status | Check the allowed transitions; the lifecycle determines this |
| **Change status** is unavailable | You do not have the `Members_CRUD` permission    | Ask your Tenant Admin for the right permission                 |
| Bulk action is missing           | No rows are selected                             | Select one or more rows first                                  |
