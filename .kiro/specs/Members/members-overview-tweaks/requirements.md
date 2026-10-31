# Requirements Document

## Introduction

A set of small, focused UI/UX and export-naming changes in the Members area. The work covers four independent improvements: relocating the action-button and pagination controls above the members table, trimming calculated fields from the edit modal while preserving them in the view modal (with a responsive two-column layout), naming analytics pivot exports and email subjects with a tenant-name prefix combined with the pivot name, and re-wiring the applications inbox out of Members Overview and into the tenant administrator members mail area.

These are primarily frontend presentation changes plus export-naming logic in the mail-send path and navigation/routing changes for the applications inbox.

## Glossary

- **Members_Overview_Page**: The frontend Members Overview page (`frontend/src/pages/MembersPage.tsx`) that renders the members table with shared filters, sort, action buttons, pagination, and row modals.
- **Members_Table**: The table element rendered on the Members_Overview_Page listing member rows.
- **Action_Buttons_Row**: The row of action buttons (e.g. add, export, view toggles) associated with the Members_Overview_Page.
- **Pagination_Controls**: The next/previous page controls associated with the Members_Table.
- **Edit_Modal**: The modal used to create or edit a member, containing editable form fields.
- **View_Modal**: The read-only modal shown on row-click that displays a member's details.
- **Calculated_Field**: A read-only field whose value is derived/computed and cannot be edited by the user.
- **Editable_Field**: A field in the Edit_Modal that the user can change.
- **Pivot_Export**: The analytics pivot output delivered as a downloaded CSV file or as an email attachment.
- **Pivot_Name**: The display name of the selected analytics pivot.
- **Tenant_Name**: The name of the active tenant, used as the fixed prefix for export naming.
- **Mail_Send_Worker**: The SAM mail-send worker service (`sam/members/worker/mail_send_worker.py`) that builds the CSV attachment and email subject for pivot output sends.
- **Applications_Inbox**: The view that filters members to `status = application`, currently presented as a preset on the Members_Overview_Page.
- **Members_Mail_Area**: The navigation location under tenant administrator > members > mail where the Applications_Inbox is to be presented.
- **Wide_Viewport**: A viewport whose width meets or exceeds the application's defined breakpoint for a two-column modal layout.
- **Narrow_Viewport**: A viewport whose width is below the two-column breakpoint.

## Requirements

### Requirement 1: Controls above the table

**User Story:** As a member administrator, I want the action buttons and pagination controls positioned directly above the members table, so that I can reach them without scrolling to the bottom of the page.

#### Acceptance Criteria

1. THE Members_Overview_Page SHALL render the Action_Buttons_Row directly above the Members_Table.
2. THE Members_Overview_Page SHALL render the Pagination_Controls directly above the Members_Table.
3. THE Members_Overview_Page SHALL render the Action_Buttons_Row and the Pagination_Controls in the same positions above the Members_Table regardless of the number of rows displayed.
4. WHEN a user activates a Pagination_Control above the Members_Table, THE Members_Table SHALL display the corresponding page of member rows.

### Requirement 2: Edit modal shows only editable fields

**User Story:** As a member administrator, I want the edit modal to show only editable fields, so that the modal is smaller and focused on what I can change.

#### Acceptance Criteria

1. THE Edit_Modal SHALL display every Editable_Field for the member.
2. THE Edit_Modal SHALL exclude every Calculated_Field from display.
3. WHEN a user saves the Edit_Modal, THE Members_Overview_Page SHALL persist the values of the Editable_Fields.

### Requirement 3: View modal keeps all calculated fields

**User Story:** As a member administrator, I want the view modal to keep all calculated fields, so that I can see a member's complete derived details when viewing.

#### Acceptance Criteria

1. THE View_Modal SHALL display every Calculated_Field for the member.
2. THE View_Modal SHALL display the member's non-calculated fields.

### Requirement 4: Responsive two-column modal layout

**User Story:** As a member administrator, I want the member modals laid out in two columns on wider screens, so that the content fits on one page without vertical scrolling.

#### Acceptance Criteria

1. WHILE the viewport is a Wide_Viewport, THE Edit_Modal SHALL arrange its fields in two columns.
2. WHILE the viewport is a Wide_Viewport, THE View_Modal SHALL arrange its fields in two columns.
3. WHILE the viewport is a Narrow_Viewport, THE Edit_Modal SHALL arrange its fields in a single column.
4. WHILE the viewport is a Narrow_Viewport, THE View_Modal SHALL arrange its fields in a single column.

### Requirement 5: Tenant-prefixed pivot export naming

**User Story:** As a member administrator, I want analytics pivot exports named with the tenant name and pivot name, so that I can identify which tenant and pivot a downloaded or emailed file belongs to.

#### Acceptance Criteria

1. WHEN a Pivot_Export is produced as a downloaded CSV file, THE Members_Overview_Page SHALL name the file `{Tenant_Name}-{Pivot_Name}.csv`.
2. WHEN a Pivot_Export is produced as an email attachment, THE Mail_Send_Worker SHALL name the attachment `{Tenant_Name}-{Pivot_Name}.csv`.
3. WHEN a Pivot_Export is sent by email, THE Mail_Send_Worker SHALL compose the email subject to include the Tenant_Name as a prefix combined with the Pivot_Name.
4. THE Members_Overview_Page SHALL replace the fixed `members.csv` download filename with the `{Tenant_Name}-{Pivot_Name}.csv` name.
5. THE Mail_Send_Worker SHALL replace the fixed `members.csv` attachment filename with the `{Tenant_Name}-{Pivot_Name}.csv` name.

### Requirement 6: Relocate the applications inbox

**User Story:** As a tenant administrator, I want the applications inbox located under tenant administrator > members > mail, so that it lives in a logical place rather than on the Members Overview page.

#### Acceptance Criteria

1. THE Members_Overview_Page SHALL exclude the Applications_Inbox.
2. THE Members_Mail_Area SHALL present the Applications_Inbox under tenant administrator > members > mail.
3. WHEN a user opens the Applications_Inbox from the Members_Mail_Area, THE Applications_Inbox SHALL display members filtered to `status = application`.
4. WHERE the Applications_Inbox provides duplicate and auto-notify keyword filters, THE Members_Mail_Area SHALL retain those keyword filters in the relocated Applications_Inbox.
