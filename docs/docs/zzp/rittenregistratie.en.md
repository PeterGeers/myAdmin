# Trip Registration

> Track business and private kilometers in compliance with Dutch Tax Authority requirements.

## Overview

The trip registration helps you maintain a complete odometer administration for your vehicle(s). This is mandatory if you:

- Have a **private car for business use** — you claim €0.23/km deduction for business trips
- Have a **business car** — you must prove you drive less than 500 private km/year to avoid fringe benefit tax

The Dutch Tax Authority requires per trip: date, start and end address, start and end odometer, distance driven, trip purpose and category (business/private/commute). myAdmin records all this data and offers export in the required format.

## What you need

- Access to the ZZP module (`zzp_crud` permissions)
- At least one registered vehicle (see [Vehicles](voertuigen.md))

## Register trips

### Add a new trip

1. Go to **ZZP** → **Trip Registration**
2. Click **New trip**
3. Fill in the fields:

| Field          | Required  | Description                                          |
| -------------- | --------- | ---------------------------------------------------- |
| Date           | Yes       | Date of the trip                                     |
| Start time     | No        | Departure time                                       |
| End time       | No        | Arrival time                                         |
| Start address  | Yes       | Departure location                                   |
| End address    | Yes       | Destination                                          |
| Start odometer | Yes       | Odometer reading at departure (filled automatically) |
| End odometer   | Yes       | Odometer reading at arrival                          |
| Distance       | Automatic | Calculated as end odometer minus start odometer      |
| Trip purpose   | Yes       | Reason for the trip (e.g., Client visit, Meeting)    |
| Category       | Yes       | Business, Private or Commute                         |
| Vehicle        | Yes       | The vehicle you are driving                          |
| Client/project | No        | Link to a contact or project                         |
| Notes          | No        | Free text for clarification                          |

4. Click **Save**

### Use route presets

If you regularly drive the same route, the system offers your frequently used routes as quick selections:

1. Click **New trip**
2. Under **Favorite routes** your most used routes appear
3. Click on a route — start address, end address, category and trip purpose are filled automatically
4. Enter the odometer reading and click **Save**

## Edit trips

The Tax Authority requires that changes to your trip administration are traceable. Therefore you cannot simply overwrite a trip.

1. Go to **ZZP** → **Trip Registration**
2. Click on the trip you want to correct
3. Click **Edit**
4. Modify the fields
5. Fill in a mandatory **Correction reason** (e.g., "Odometer misread")
6. Click **Save**

The system preserves the old values and the reason for change in an immutable audit trail.

## Cancel trips

Trips cannot be deleted — only cancelled (soft-delete). This is intentional, so your administration remains complete and auditable.

1. Open the trip you want to cancel
2. Click **Cancel**
3. Fill in a mandatory **Cancellation reason** (e.g., "Entered twice")
4. Click **Confirm**

The trip is shown crossed out in the overview and no longer counts towards your totals.

## Categories

Each trip gets a category that determines how the kilometers are processed for tax:

| Category     | Meaning                                       | Tax effect                                            |
| ------------ | --------------------------------------------- | ----------------------------------------------------- |
| **Business** | Trip for your company (client visit, meeting) | Deductible for private car; no fringe benefit for biz |
| **Private**  | Personal trip                                 | Counts toward the 500 km limit for business cars      |
| **Commute**  | Trip from home to your fixed workplace        | Counts toward the 500 km limit for business cars      |

## Fringe benefit tax (500 km limit)

If you have a business car, you must demonstrate that you drive less than 500 private km/year to avoid fringe benefit tax. The system tracks this automatically.

### Dashboard widget

In the trip overview you see a widget showing:

- **Total km this year** — all kilometers driven
- **Business** — kilometers for your company
- **Private + Commute** — kilometers counting toward the 500 km limit
- **Remaining budget** — how many private kilometers you can still drive

## Gap-fill (odometer gaps)

An odometer gap occurs when the start odometer of a new trip does not connect to the end odometer of your previous trip.

### How it works

1. You enter a new trip with start odometer 45,200
2. Your previous trip ended at 45,050
3. There is a gap of 150 km — the system warns you

### What you can do

- **Accept gap-fill** — the system automatically creates an intermediate trip (category: Private, purpose: "Not registered")
- **Fill in manually** — create the missing trip(s) yourself
- **Resolve later** — the trip is saved, the gap remains visible as an attention point

## Filtering and sorting

The trip overview offers extensive filter and sort options:

| Filter     | Description                            |
| ---------- | -------------------------------------- |
| Date range | View trips within a specific period    |
| Category   | Only business, private or commute      |
| Vehicle    | Filter by a specific vehicle           |
| Client     | Only trips linked to a specific client |
| Status     | Active, cancelled, or gap-fill         |

## Invoicing

Business trips linked to a client can be invoiced directly:

1. Go to **ZZP** → **Trip Registration**
2. Filter by the desired client and period
3. Select the trips you want to invoice (only non-invoiced business trips)
4. Click **Create invoice**
5. The selected trips are converted to invoice lines (km × rate)
6. Review the invoice and click **Save**

## Exporting

You can export your trip administration in various formats:

| Format    | Use                                               |
| --------- | ------------------------------------------------- |
| **PDF**   | Official overview for Tax Authority or accountant |
| **CSV**   | Processing in Excel or other software             |
| **Excel** | Ready-made spreadsheet with formatting            |

## Troubleshooting

| Problem                       | Cause                                      | Solution                                               |
| ----------------------------- | ------------------------------------------ | ------------------------------------------------------ |
| Trip registration not visible | ZZP module not enabled                     | Ask your Tenant Admin to activate the module           |
| No vehicle available          | No vehicle registered yet                  | Register a vehicle first via [Vehicles](voertuigen.md) |
| Odometer not filled in        | No previous trip for this vehicle          | Fill in the start odometer manually                    |
| Error when saving             | End odometer is lower than start odometer  | Check your odometer readings                           |
| Gap-fill warning              | Start odometer doesn't match previous trip | Create an intermediate trip or accept the gap-fill     |
| Trip cannot be deleted        | Deletion is not allowed                    | Use **Cancel** instead of delete                       |
