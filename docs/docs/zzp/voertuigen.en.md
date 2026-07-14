# Vehicles

> Register and manage vehicles for your trip administration.

## Overview

Before you can register trips, you need to add at least one vehicle. The system tracks the odometer per vehicle and calculates the correct tax totals.

!!! info
You can register multiple vehicles. The system maintains a separate odometer administration per vehicle.

## What you need

- Access to the ZZP module (`zzp_crud` permissions)
- Your vehicle registration document (for license plate, make, model, and year)

## Add a vehicle

1. Go to **ZZP** → **Trip Registration** → **Vehicles**
2. Click **Add vehicle**
3. Fill in the fields:

| Field                 | Required | Description                                      |
| --------------------- | -------- | ------------------------------------------------ |
| License plate         | Yes      | Dutch license plate (e.g., AB-123-CD)            |
| Make                  | Yes      | Vehicle make (e.g., Volkswagen)                  |
| Type/Model            | Yes      | Vehicle model (e.g., Golf)                       |
| Year                  | Yes      | Year of manufacture                              |
| Chassis number (VIN)  | No       | Vehicle Identification Number (17 characters)    |
| Vehicle type          | Yes      | Private for business use **or** Business vehicle |
| Unit                  | Yes      | Kilometers (default) or Miles                    |
| Start odometer        | Yes      | Current odometer reading at registration         |
| Owner/Leasing company | No       | Name of owner or leasing company                 |

4. Click **Save**

## Vehicle types

The vehicle type determines how the system processes your kilometers for tax purposes:

### Private for business use

You drive your own (private) car and also use it for business trips.

| Aspect             | Explanation                        |
| ------------------ | ---------------------------------- |
| Ownership          | Private property or private lease  |
| Tax deduction      | €0.23/km for business trips        |
| What is tracked    | Total business kilometers per year |
| Fringe benefit tax | Not applicable                     |

### Business vehicle

The car is in your company's name or leased commercially.

| Aspect             | Explanation                                  |
| ------------------ | -------------------------------------------- |
| Ownership          | Business property or business lease          |
| Tax deduction      | All costs are already business               |
| What is tracked    | Private + commute km (max 500 km/year)       |
| Fringe benefit tax | Exempt if you stay under 500 private km/year |

## Edit a vehicle

1. Go to **ZZP** → **Trip Registration** → **Vehicles**
2. Click on the vehicle you want to edit
3. Click **Edit**
4. Modify the fields
5. Click **Save**

### What can be changed

| Field                 | Changeable | Notes                                     |
| --------------------- | ---------- | ----------------------------------------- |
| License plate         | Yes        | E.g., for personalization                 |
| Make / Type / Year    | Yes        | Correction of entry errors                |
| Chassis number        | Yes        | Can be added later                        |
| Vehicle type          | Limited    | Only if no trips have been registered yet |
| Unit (km/miles)       | No         | Cannot be changed after registration      |
| Start odometer        | No         | Cannot be changed after the first trip    |
| Owner/Leasing company | Yes        | E.g., when switching lease contracts      |

## Deactivate a vehicle

If you no longer use a vehicle (sold, end of lease, etc.), you can deactivate it. Deletion is not possible if trips are linked to it.

1. Go to **ZZP** → **Trip Registration** → **Vehicles**
2. Click on the vehicle
3. Click **Deactivate**
4. Confirm the action

### What happens after deactivation?

| Aspect         | Effect                                               |
| -------------- | ---------------------------------------------------- |
| Existing trips | Remain saved and visible in the overview             |
| New trips      | Can no longer be created for this vehicle            |
| Reports        | Historical data remains available for export and tax |
| Vehicle list   | The vehicle is shown dimmed with status "Inactive"   |
| Reactivation   | You can reactivate a deactivated vehicle later       |

## Troubleshooting

| Problem                        | Cause                               | Solution                                     |
| ------------------------------ | ----------------------------------- | -------------------------------------------- |
| Vehicle cannot be deleted      | Trips are linked to the vehicle     | Use **Deactivate** instead of delete         |
| Vehicle type cannot be changed | Trips have already been registered  | Create a new vehicle with the correct type   |
| Start odometer is wrong        | Entered incorrectly at registration | Contact your Tenant Admin for a correction   |
| Vehicle not shown for new trip | The vehicle is deactivated          | Reactivate the vehicle via the vehicles list |
