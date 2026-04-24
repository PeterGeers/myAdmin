# Requirements Document: Dynamic Pivot Views

## Introduction

Dynamic Pivot Views enables users to create ad-hoc aggregated views of tabular data by selecting grouping columns, aggregation functions, and optional filters — then save those configurations as reusable "pivot models" for later recall. This feature extends the existing table infrastructure (`useFilterableTable`, `FilterableHeader`, `ReportingService`) with a user-driven GROUP BY query builder and a persistence layer for saved view definitions.

The scope covers the two primary data sources (`vw_mutaties` for financial transactions and `vw_bnb_total` for STR revenue) and integrates with the existing parameter system for default view configuration.

## Data Source Column Definitions

### vw_mutaties (Financial Transactions)

| Column                 | Type    | Groupable | Aggregatable | Description                                                 |
| ---------------------- | ------- | --------- | ------------ | ----------------------------------------------------------- |
| Aangifte               | varchar | Yes       | No           | Tax declaration category                                    |
| TransactionNumber      | varchar | No        | No           | Unique transaction identifier                               |
| TransactionDate        | date    | Yes       | No           | Date of the transaction                                     |
| TransactionDescription | varchar | No        | No           | Free-text description                                       |
| Amount                 | decimal | No        | Yes          | Signed transaction amount (debet=negative, credit=positive) |
| Reknum                 | varchar | Yes       | No           | Ledger account number                                       |
| AccountName            | varchar | Yes       | No           | Ledger account name                                         |
| Parent                 | varchar | Yes       | No           | Parent account category                                     |
| VW                     | varchar | Yes       | No           | Profit (V) or Loss (W) indicator                            |
| jaar                   | int     | Yes       | No           | Transaction year                                            |
| kwartaal               | int     | Yes       | No           | Transaction quarter (1-4)                                   |
| maand                  | int     | Yes       | No           | Transaction month (1-12)                                    |
| week                   | int     | Yes       | No           | Transaction week number                                     |
| ReferenceNumber        | varchar | Yes       | No           | Bank reference number                                       |
| administration         | varchar | Yes       | No           | Administration (tenant entity)                              |

### vw_bnb_total (STR Revenue)

| Column                | Type    | Groupable | Aggregatable | Description                            |
| --------------------- | ------- | --------- | ------------ | -------------------------------------- |
| channel               | varchar | Yes       | No           | Booking platform (Airbnb, Booking.com) |
| listing               | varchar | Yes       | No           | Property listing name                  |
| checkinDate           | date    | Yes       | No           | Guest check-in date                    |
| checkoutDate          | date    | No        | No           | Guest check-out date                   |
| nights                | int     | No        | Yes          | Number of nights stayed                |
| guests                | int     | No        | Yes          | Number of guests                       |
| amountGross           | decimal | No        | Yes          | Gross booking revenue                  |
| amountNett            | decimal | No        | Yes          | Net revenue after fees                 |
| amountChannelFee      | decimal | No        | Yes          | Platform commission fee                |
| amountTouristTax      | decimal | No        | Yes          | Tourist tax amount                     |
| amountVat             | decimal | No        | Yes          | VAT amount                             |
| pricePerNight         | decimal | No        | Yes          | Average price per night                |
| daysBeforeReservation | int     | No        | Yes          | Lead time in days                      |
| year                  | int     | Yes       | No           | Booking year                           |
| q                     | int     | Yes       | No           | Booking quarter (1-4)                  |
| m                     | int     | Yes       | No           | Booking month (1-12)                   |
| country               | varchar | Yes       | No           | Guest country code                     |
| countryName           | varchar | Yes       | No           | Guest country name (English)           |
| countryRegion         | varchar | Yes       | No           | Geographic region                      |
| source_type           | varchar | Yes       | No           | Booking type: "actual" or "planned"    |
| status                | varchar | Yes       | No           | Booking status                         |

### How Pivot Output Is Structured

A pivot view produces a flat result table where:

- **Rows** are defined by the unique combinations of the selected Group_Columns. Each distinct combination of group values produces one row.
- **Columns** consist of the Group_Columns (as row identifiers) followed by the Aggregate_Measures (as computed values). For example, selecting Group_Columns `[channel, year]` with Aggregate_Measures `[SUM(amountGross), COUNT(*)]` produces a table with four columns: `channel`, `year`, `SUM(amountGross)`, `COUNT(*)`.

### Nested / Hierarchical Rows

When multiple Group_Columns are selected, the Pivot_Result_Table supports a hierarchical display mode. The first Group_Column defines the top-level rows, and subsequent Group_Columns create nested sub-rows that can be expanded or collapsed. For example, with Group_Columns `[channel, listing, year]`:

```
▼ Airbnb                    SUM(amountGross): €45,000   COUNT: 120
    ▼ Amsterdam Apartment   SUM(amountGross): €30,000   COUNT:  80
        2025                SUM(amountGross): €18,000   COUNT:  50
        2024                SUM(amountGross): €12,000   COUNT:  30
    ▼ Rotterdam Studio      SUM(amountGross): €15,000   COUNT:  40
        2025                SUM(amountGross): €10,000   COUNT:  28
        2024                SUM(amountGross):  €5,000   COUNT:  12
▼ Booking.com               SUM(amountGross): €22,000   COUNT:  65
    ...
```

Each parent row shows the aggregate values rolled up across its children. Users can toggle between flat and hierarchical display modes.

### Nested / Pivoted Columns

In addition to row grouping, users can designate one Group_Column as a **Column_Pivot** — its distinct values become column headers, spreading the Aggregate_Measures across the horizontal axis. The system supports hierarchical column nesting by allowing additional Group_Columns as **Column_Nest_Levels** beneath the Column_Pivot, mirroring how nested rows work on the vertical axis.

Any groupable column can serve as a Column_Pivot or Column_Nest_Level. Time-based nesting (year → quarter → month) is one common pattern, but the mechanism is general-purpose.

**Example 1 — Time-based nesting:** Row Group `[channel]`, Column Pivot `jaar` with nest level `kwartaal`, Aggregate `SUM(Amount)`:

```
                    |        2024         |        2025         |
                    |  Q1  |  Q2  | ...  |  Q1  |  Q2  | ...  |
-----------------------------------------------------------------
Airbnb              | 5000 | 7200 | ...  | 6100 | 8400 | ...  |
Booking.com         | 3200 | 4100 | ...  | 3800 | 5000 | ...  |
```

**Example 2 — Non-time nesting:** Row Group `[year]`, Column Pivot `channel` with nest level `listing`, Aggregate `SUM(amountGross)`:

```
                    |        Airbnb                    |        Booking.com              |
                    |  Amsterdam  |  Rotterdam  | ...  |  Amsterdam  |  Rotterdam  | ... |
------------------------------------------------------------------------------------------
2024                |    12000    |    5000     | ...  |    3200     |    4100     | ... |
2025                |    18000    |   10000     | ...  |    3800     |    5000     | ... |
```

Column pivoting is optional — when no Column_Pivot is selected, all Group_Columns appear on the row axis as described in the hierarchical rows section above.

## Glossary

- **Pivot_View**: A user-defined aggregation configuration consisting of a data source, one or more group-by columns, one or more aggregate measures, optional filters, and display preferences.
- **Pivot_Model**: A persisted Pivot_View definition stored in the database, identified by a unique name, owned by a user within a tenant.
- **Pivot_Model_Store**: The persistence layer responsible for saving, loading, updating, and deleting Pivot_Model definitions. Backed by the `pivot_models` database table and exposed through the Pivot_API.
- **Group_Column**: A column selected by the user to partition data into groups (used in the SQL GROUP BY clause).
- **Column_Pivot**: An optional Group_Column whose distinct values are transposed into column headers, spreading Aggregate_Measures horizontally across the result table. Supports hierarchical nesting through additional Column_Nest_Levels for any groupable columns (e.g., year → quarter → month, or channel → listing).
- **Column_Nest_Level**: An additional Group_Column placed beneath the Column_Pivot to create hierarchical column headers. Multiple nest levels can be stacked, mirroring how nested rows work on the vertical axis.
- **Aggregate_Measure**: A combination of an aggregation function (SUM, COUNT, AVG, MIN, MAX) and a target column, producing a single computed value per group.
- **Data_Source**: One of the available database views or tables that a Pivot_View can query — initially `vw_mutaties` and `vw_bnb_total`.
- **Pivot_Builder**: The frontend UI component that allows users to configure a Pivot_View by selecting group columns, aggregate measures, and filters.
- **Pivot_Result_Table**: The frontend component that renders the aggregated output of a Pivot_View execution.
- **Pivot_Service**: The backend service responsible for constructing and executing dynamic GROUP BY queries. Delegates model persistence to the Pivot_Model_Store.
- **Pivot_API**: The set of backend REST endpoints for executing pivot queries and managing Pivot_Models (CRUD operations on the Pivot_Model_Store).
- **Allowed_Columns_Registry**: A backend configuration that defines which columns from each Data_Source are available for grouping and aggregation, preventing arbitrary column access.

## Requirements

### Requirement 1: Define a Pivot View Configuration

**User Story:** As a financial administrator, I want to select a data source, choose columns to group by, and pick aggregation functions for numeric columns, so that I can create custom aggregated views of my data.

#### Acceptance Criteria

1. WHEN the user opens the Pivot_Builder, THE Pivot_Builder SHALL display the list of available Data_Sources.
2. WHEN the user selects a Data_Source, THE Pivot_Builder SHALL display the columns available for grouping and the numeric columns available for aggregation, as defined by the Allowed_Columns_Registry.
3. WHEN the user selects one or more Group_Columns, THE Pivot_Builder SHALL include those columns in the pivot configuration.
4. WHEN the user selects one or more Aggregate_Measures (function + column), THE Pivot_Builder SHALL include those measures in the pivot configuration.
5. THE Pivot_Builder SHALL support the aggregation functions SUM, COUNT, AVG, MIN, and MAX.
6. IF the user attempts to execute a Pivot_View without at least one Group_Column and one Aggregate_Measure, THEN THE Pivot_Builder SHALL display a validation error indicating the missing selections.
7. THE Pivot_Builder SHALL allow the user to select up to five Group_Columns per Pivot_View.
8. THE Pivot_Builder SHALL allow the user to select up to ten Aggregate_Measures per Pivot_View.

### Requirement 2: Apply Filters to a Pivot View

**User Story:** As a financial administrator, I want to apply filters to my pivot view using the same filter controls I already know from the existing tables, so that I can focus the aggregation on a relevant subset of data without learning a new UI.

#### Acceptance Criteria

1. WHEN the user configures a Pivot_View, THE Pivot_Builder SHALL display above-table filter controls appropriate to the selected Data_Source, reusing the existing `FilterPanel`, `YearFilter`, and `GenericFilter` components already used on the respective source tables.
2. WHEN the Data_Source is `vw_mutaties`, THE Pivot_Builder SHALL offer the same above-table filter controls as the MutatiesReport: date range (via `YearFilter`), administration, profit/loss category (VW), and ledger account (Reknum).
3. WHEN the Data_Source is `vw_bnb_total`, THE Pivot_Builder SHALL offer the same above-table filter controls as the BNB revenue table: date range, channel, and listing.
4. WHEN the user sets filter values, THE Pivot_Service SHALL apply those filters as WHERE clause conditions before the GROUP BY aggregation.
5. THE Pivot_Builder SHALL reuse the existing `FilterPanel` and `GenericFilter` components for filter rendering and state management, ensuring consistent filter behavior with the source tables.

### Requirement 3: Execute a Pivot View and Display Results

**User Story:** As a financial administrator, I want to execute my configured pivot view and see the aggregated results in a sortable table, so that I can analyze my data from different angles.

#### Acceptance Criteria

1. WHEN the user executes a Pivot_View, THE Pivot_API SHALL construct a parameterized SQL query using the selected Group_Columns, Aggregate_Measures, and filters.
2. THE Pivot_Service SHALL use parameterized queries with placeholder values for all user-provided filter inputs.
3. THE Pivot_Service SHALL enforce tenant isolation by including the tenant identifier in every query WHERE clause.
4. WHEN the Pivot_API returns results, THE Pivot_Result_Table SHALL display the grouped data with one column per Group_Column and one column per Aggregate_Measure.
5. THE Pivot_Result_Table SHALL support sorting on any displayed column.
6. THE Pivot_Result_Table SHALL format numeric Aggregate_Measure values with appropriate decimal precision (two decimal places for currency amounts, zero decimal places for counts).
7. THE Pivot_Result_Table SHALL offer a number format toggle allowing the user to switch between three display modes: decimal (e.g., €12,345.67), whole numbers (e.g., €12,346), and abbreviated/k-notation (e.g., €12.3k).
8. IF the pivot query returns zero rows, THEN THE Pivot_Result_Table SHALL display a message indicating no data matches the current configuration.
9. IF the pivot query execution fails, THEN THE Pivot_API SHALL return a descriptive error message without exposing internal SQL details.

### Requirement 4: Save a Pivot View as a Reusable Model

**User Story:** As a financial administrator, I want to save my pivot view configuration with a descriptive name, so that I can reuse it later without reconfiguring from scratch.

#### Acceptance Criteria

1. WHEN the user clicks save on a valid Pivot_View configuration, THE Pivot_Builder SHALL prompt the user for a model name.
2. THE Pivot_Service SHALL persist the Pivot_Model with the model name, Data_Source, Group_Columns, Column_Pivot configuration, Aggregate_Measures, filters, display mode preference, and the creating user's identifier.
3. THE Pivot_Service SHALL associate each Pivot_Model with the current tenant.
4. IF the user provides a model name that already exists for the same user and tenant, THEN THE Pivot_Service SHALL return an error indicating the name is already in use.
5. THE Pivot_Service SHALL store the Pivot_Model definition as a JSON document in the database.
6. WHEN a Pivot_Model is saved, THE Pivot_Service SHALL record the creation timestamp and the creating user's email.

### Requirement 5: Load and Manage Saved Pivot Models

**User Story:** As a financial administrator, I want to browse, load, and delete my saved pivot models, so that I can quickly switch between different analytical views.

#### Acceptance Criteria

1. WHEN the user opens the Pivot_Builder, THE Pivot_Builder SHALL display a list of saved Pivot_Models available to the current user within the current tenant.
2. WHEN the user selects a saved Pivot_Model, THE Pivot_Builder SHALL populate the configuration (Data_Source, Group_Columns, Aggregate_Measures, filters) from the saved definition.
3. WHEN the user deletes a Pivot_Model, THE Pivot_Service SHALL remove the model from the database.
4. THE Pivot_API SHALL return only Pivot_Models belonging to the requesting user's tenant.
5. WHEN the user modifies a loaded Pivot_Model and saves it with the same name, THE Pivot_Service SHALL update the existing model definition.
6. WHEN a Pivot_Model is updated, THE Pivot_Service SHALL record the update timestamp.

### Requirement 6: Column Access Control via Allowed Columns Registry

**User Story:** As a system administrator, I want to control which columns are available for grouping and aggregation per data source, so that sensitive or irrelevant columns are not exposed in pivot views.

#### Acceptance Criteria

1. THE Pivot_Service SHALL maintain an Allowed_Columns_Registry that defines, per Data_Source, the system-level maximum set of columns available for grouping and aggregation.
2. THE system SHALL allow a tenant administrator to reduce the allowed columns for their tenant via the parameter system, restricting which columns are available to their users.
3. WHEN resolving available columns for a user, THE Pivot_Service SHALL apply scope inheritance: start with the system-level maximum list, then apply any tenant-level restrictions.
4. WHEN the Pivot_Builder requests available columns for a Data_Source, THE Pivot_API SHALL return only columns permitted by the resolved Allowed_Columns_Registry for the current tenant.
5. IF a pivot execution request includes a column not in the resolved Allowed_Columns_Registry, THEN THE Pivot_Service SHALL reject the request with a validation error.
6. THE system-level Allowed_Columns_Registry SHALL be defined in backend configuration and not modifiable through the Pivot_API.
7. THE tenant-level column restrictions SHALL be stored in the `parameters` table (namespace: `ui.pivot`, key per Data_Source) and editable by tenant administrators through the existing ParameterManagement UI.

### Requirement 7: Export Pivot Results

**User Story:** As a financial administrator, I want to export either the pivot view results or the underlying dataset to CSV, so that I can share or further analyze the data in Excel or other tools.

#### Acceptance Criteria

1. WHEN the user clicks export on a Pivot_Result_Table with data, THE Pivot_Result_Table SHALL offer the choice to export the pivot view result (aggregated data as displayed) or the underlying filtered dataset (raw rows before aggregation).
2. THE Pivot_Result_Table SHALL export to CSV format, which can be imported into Excel/XLSX by the user.
3. WHEN exporting the pivot view result, THE exported CSV SHALL include column headers matching the displayed table headers and the same aggregated rows.
4. WHEN exporting the underlying dataset, THE exported CSV SHALL include all columns from the Data_Source that match the current filter criteria, with one row per source record.
5. THE pivot view export SHALL use the same numeric formatting as the currently selected display mode (decimal, whole numbers, or k-notation). The underlying dataset export SHALL use full-precision numbers.
6. IF the Pivot_Result_Table has no data, THEN the export actions SHALL be disabled.

### Requirement 8: Hierarchical Display Mode

**User Story:** As a financial administrator, I want to view pivot results in a hierarchical tree layout when multiple group columns are selected, so that I can drill down from high-level summaries into detailed breakdowns.

#### Acceptance Criteria

1. WHEN a Pivot_View has two or more Group_Columns, THE Pivot_Result_Table SHALL offer a hierarchical display mode in addition to the flat table mode.
2. WHILE in hierarchical mode, THE Pivot_Result_Table SHALL render the first Group_Column as top-level rows, with subsequent Group_Columns as nested expandable sub-rows.
3. WHILE in hierarchical mode, THE Pivot_Result_Table SHALL display rolled-up Aggregate_Measure values on each parent row, computed as the aggregation across all child rows.
4. WHEN the user clicks a parent row, THE Pivot_Result_Table SHALL expand or collapse the child rows beneath it.
5. THE Pivot_Result_Table SHALL default to hierarchical mode when two or more Group_Columns are selected.
6. WHEN the user toggles between flat and hierarchical mode, THE Pivot_Result_Table SHALL re-render the same data in the selected layout without re-executing the query.
7. WHEN a Pivot_View has exactly one Group_Column, THE Pivot_Result_Table SHALL display in flat mode only (hierarchical toggle is hidden).

### Requirement 9: Column Pivot with Nested Column Headers

**User Story:** As a financial administrator, I want to pivot any groupable column into column headers with optional nested sub-columns, so that I can compare values across categories side by side — the same way nested rows allow drill-down on the vertical axis.

#### Acceptance Criteria

1. WHEN the user configures a Pivot_View, THE Pivot_Builder SHALL allow the user to optionally designate one Group_Column as a Column_Pivot.
2. WHEN a Column_Pivot is selected, THE Pivot_Result_Table SHALL render the distinct values of that column as column headers, with Aggregate_Measure values spread across those columns.
3. WHEN a Column_Pivot is selected, THE Pivot_Builder SHALL allow the user to add one or more additional Group_Columns as Column_Nest_Levels beneath the Column_Pivot.
4. WHEN Column_Nest_Levels are selected, THE Pivot_Result_Table SHALL render hierarchical column headers with the Column_Pivot as the top level and each Column_Nest_Level as a subsequent sub-level.
5. THE Pivot_Builder SHALL allow any groupable column from the Allowed_Columns_Registry to serve as a Column_Pivot or Column_Nest_Level.
6. WHEN no Column_Pivot is selected, THE Pivot_Result_Table SHALL display all Group_Columns on the row axis only.
7. THE Pivot_Service SHALL construct the appropriate query to produce the pivoted result set, using conditional aggregation for column pivoting.
8. THE Pivot_Builder SHALL allow at most one Column_Pivot per Pivot_View.
9. WHEN a Column_Pivot is active, THE Pivot_Result_Table SHALL display a grand total column at the end of each pivot group.
10. THE Pivot_Builder SHALL prevent the same Group_Column from being used simultaneously as a row Group_Column, Column_Pivot, and Column_Nest_Level.
11. THE Pivot_Builder SHALL allow the user to select up to five Column_Nest_Levels per Pivot_View.

### Requirement 10: Pivot Model Definition Serialization

**User Story:** As a developer, I want pivot model definitions to be reliably serialized and deserialized, so that saved models are faithfully restored when loaded.

#### Acceptance Criteria

1. THE Pivot_Service SHALL serialize Pivot_Model definitions to JSON for database storage.
2. THE Pivot_Service SHALL deserialize stored JSON back into Pivot_Model definitions when loading.
3. FOR ALL valid Pivot_Model definitions, serializing then deserializing SHALL produce an equivalent Pivot_Model definition (round-trip property).
4. IF a stored JSON document is malformed or missing required fields, THEN THE Pivot_Service SHALL return a descriptive error and not load a partial model.
