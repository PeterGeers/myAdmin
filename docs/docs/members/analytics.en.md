# Analytics

> Build, view, and export summaries and pivot tables over your members.

## Overview

**Analytics** is a separate page within Member Administration, next to the Members Overview. You reach it through its own menu item **📊 Analytics** under the Members section. The page is **read-only**: here you calculate and report on your members; you do not change any member data.

On the page:

- a **filter bar** at the top (member number, name, email, status, membership type, and region) to narrow the dataset;
- a live **counter** of how many members remain after filtering;
- a panel of analyses, including the **pivot views** (pivot tables and lists) described below.

As in the Members Overview, your **region scope** applies: you only work with the members within your scope. The page fetches that set itself and can only narrow it further with the filter bar, never widen it.

!!! info
For a very large member set, the page shows a warning (results may be incomplete) or, when the limit is exceeded, a notice that the set is too large to analyze. In that case, narrow it down first with the filter bar.

## The three areas

The analytics panel has three areas, which you switch between with the buttons at the top of the panel. One is visible at a time; **Overview** is the default.

| Area        | For                                                            |
| ----------- | -------------------------------------------------------------- |
| Overview    | Key figures at a glance (count, averages, breakdown per type)  |
| Distributions | Charts (violin plots) of age and years of membership         |
| Pivot views | Pivot tables and lists you run, build, and export              |

All three work on the same dataset: your members within your region scope, further narrowed by the filter bar. If you change a filter, the figures and charts move with it immediately.

## Overview

The **Overview** area shows key figures about the filtered members:

| Figure              | Meaning                                                 |
| ------------------- | ------------------------------------------------------- |
| Count               | The number of members in the current (filtered) set     |
| Average age         | The average age                                         |
| Average years member | The average number of years of membership              |

Below the figures is a **breakdown per membership type**: the number of members per type, sorted descending.

!!! info
The averages are computed over the members with a valid value. Members without a (valid) age or years-member are not counted as zero but skipped. If there are such members, a line like "N of M excluded" is shown, so you interpret the figure correctly.

!!! info
Age and years-member are **calculated fields**. If your tenant does not have one of those fields, that single figure is omitted gracefully (the rest stays) — you never see a nonsense value.

## Distributions

The **Distributions** area shows **violin plots**: a chart that shows how a value is distributed across your members. There are two: one for **age** and one for **years of membership**.

### Grouping

By default you see one distribution per chart over all filtered members. With the **Group by** dropdown you split each chart into several "violins", one per value of the chosen dimension:

- Region
- Membership type
- Gender

!!! info
The dropdown only shows the dimensions your tenant actually has as a field. If your tenant has no gender field, for example, that option does not appear. If no dimension is available, there is no dropdown and you see one distribution per metric.

!!! info
A chart needs a minimum number of data points to be meaningful. If too few members have a valid value, that chart shows a "not enough data" notice instead of a plot. This is judged on the total; grouping therefore never hides a metric that had enough data when ungrouped.

## Pivot views

A **pivot view** (set) is a predefined count or list over your members. There are two kinds:

- **Count** — groups members and counts (or sum/average/min/max) per group. For example "number of members per membership type".
- **List** — shows one row per member with a fixed set of columns. For example "members by birth month" with name, birthday, and address.

### Running a view

**Nothing is calculated automatically.** You decide when a view runs:

1. Go to **Member Administration** → **📊 Analytics**
2. Choose a set from the dropdown
3. Click **Execute**
4. The result appears as a table below the button

!!! info
The dropdown shows only the sets in **your preferred list** (see below). To run a different set, open **All sets** and run it there or add it to your preferred list.

Two presets show an extra dropdown next to **Execute**:

- **Jubilees** — choose a jubilee year; the result is limited to members reaching that jubilee.
- **New members** — choose a year; the result shows members who joined in or after that year.

## Built-in views (presets)

There are standard views that are always available, plus a few that only appear once your tenant has mapped the matching field.

### Always available

| View                   | Kind    | Shows                                                        |
| ---------------------- | ------- | ----------------------------------------------------------- |
| Membership types       | Count   | Number of members per membership type                       |
| Birthday / birth month | List    | Members by birth month, with name, birthday, region, and address |
| Jubilees               | List    | Jubilee members based on years of membership                |
| New members            | List    | New members based on their join date                        |

### Only visible after mapping (role-backed)

These views only appear once your tenant has mapped the matching field in the analytics configuration:

| View                        | Kind    | Requires mapped field       |
| --------------------------- | ------- | --------------------------- |
| Cancellations               | List    | Cancellation/end date       |
| Paper newsletter (per country) | Count | Paper-newsletter flag       |
| Digital newsletter          | List    | Digital-newsletter flag     |
| Referral source             | Count   | Referral source             |

!!! info
If a role-backed view is missing, the matching field is not mapped in **Member configuration → Analytics**. An administrator can add that mapping; the view then appears automatically.

## Your preferred list and "All sets"

There are two listings of sets:

- **Your preferred list** — a personal, ordered shortlist. This is exactly what the dropdown at the top shows. The list is per user: your choice applies only to you.
- **All sets** — the full library with all presets and all of your tenant's saved sets, alphabetically. You open it with the **All sets** button next to the dropdown.

In the **All sets** dialog you can, per set:

- **run** it directly;
- **add** it to or **remove** it from your preferred list, and reorder it;
- **delete** a saved (custom) set (presets cannot be deleted).

## Building your own set

Besides the presets, you create your own counts and lists with the **set builder**. The actions sit above the result:

- **New set** — build and save a new set.
- **Save as** — save the chosen set (or preset) as a new variant.
- **Update** — edit a saved set.

In the builder you specify:

| Element       | Behavior                                                                                  |
| ------------- | ----------------------------------------------------------------------------------------- |
| Name          | Required; the name the set appears under                                                  |
| Group by      | Zero or more fields to group on. No grouping = a list set (one row per member)            |
| List columns  | (For a list set) the columns the list shows                                               |
| Measures      | Zero or more calculations: `COUNT`, `SUM`, `AVG`, `MIN`, `MAX` over a field (or "count all") |
| Filters       | Optional fixed filters (field = value) that belong to the set and apply when run          |

Saved sets are **shared within your tenant**: everyone with access sees them in the library. The result always follows your own region scope and the filter bar.

!!! info
The sets are tenant-specific and are stored by the Member Administration module itself. The Analytics page's live filter is never saved into a set — a set contains only its own definition and any fixed filters.

## Exporting and mailing

If you have the export permission, extra buttons appear below a result:

- **Export to CSV** — downloads the result as a CSV file (`member-analytics.csv`). Works for both counts and lists.
- **Mail** — opens an email dialog (through the built-in mail service) to send the result. You can attach the CSV file, and — if your tenant has mapped address fields — add **PDF address labels** as an attachment.

!!! info
Export and mail operate on the rows you currently **see** in the result table. If you filter or sort the result, you export/mail exactly that subset.

!!! tip
The PDF address labels are only available if your tenant has mapped the address fields (name, street, postal code, city, country). If that mapping is missing, CSV export still works.

## Permissions

| Permission                           | What the user can do                                               |
| ------------------------------------ | ------------------------------------------------------------------ |
| `Members_Read` (or `Members_CRUD`)   | Open the Analytics page, filter, and run views                     |
| `Members_Export` (or `Members_CRUD`) | Export results to CSV, mail them, and generate PDF labels          |
| `Members_Export` or `Members_CRUD`   | Create, save as, update sets, and manage your preferred list       |

!!! info
**Deleting** a saved set from the shared library is further restricted: only a **Tenant Admin**, or a user with full (tenant-wide) access and management rights, may do so. A region-scoped administrator can create and update sets but not delete them.

## Configuration dependencies

What you see on the Analytics page also depends on your tenant's analytics configuration:

- **Jubilee rule** — determines which years count as a jubilee (default every multiple of 5 years). This drives the jubilee-year dropdown and the Jubilees view.
- **Field mappings (roles)** — determine which role-backed views are available (see above) and which real field they group/list on.
- **Address mapping** — enables the PDF address labels.

These mappings are managed in your tenant's member configuration.

## Troubleshooting

| Problem                                 | Cause                                            | Solution                                                     |
| --------------------------------------- | ------------------------------------------------ | ------------------------------------------------------------ |
| An average (age/years) is missing in Overview | Your tenant does not have that calculated field, or no member has a valid value | This is correct — no nonsense value is shown                 |
| A distribution shows "not enough data"  | Too few members with a valid value               | Widen the filter bar; below the minimum no plot is shown     |
| No **Group by** dropdown                | Your tenant has none of the dimension fields (region/type/gender) | This is normal; without dimension fields there is one distribution per metric |
| Dropdown shows few sets                 | The dropdown shows only your preferred list      | Open **All sets** to see the full library                    |
| A role-backed view is missing           | The matching field is not mapped                 | Have the mapping added in Member configuration → Analytics   |
| No export/mail buttons                  | You do not have the export permission            | Ask your Tenant Admin for `Members_Export`                   |
| No PDF labels in the mail dialog        | Your tenant has not mapped address fields        | Have the address mapping added; CSV works in the meantime    |
| "Dataset too large"                     | The member set exceeds the analytics limit       | Narrow it down with the filter bar first, then run           |
| You cannot delete a saved set           | Deleting is reserved for administrators          | Ask a Tenant Admin to delete the set                         |
