# Quick Entry GPS Address Autofill

## Reading Order

1. **requirements.md** — User stories, acceptance criteria, success metrics
2. **design.md** — Architecture, frontend component changes, API contracts
3. **tasks.md** — Phased implementation plan with checkboxes

## Context

This spec adds two UX improvements to the existing "Snelle invoer" (Quick Entry) page (`ZZPTripQuick.tsx`):

1. **GPS-based address lookup** — A "Locatie ophalen" button next to start/end address fields that uses the browser Geolocation API + OpenStreetMap Nominatim reverse geocoding to auto-fill the address.
2. **Auto-fill start address from last trip** — When loading the page or switching vehicles, the start address is automatically pre-filled from the previous trip's end address for that vehicle.

These address the user feedback:
> VAN: Is het mogelijk dat de plek waar je vandaan komt automatisch wordt ingevoerd aan de hand van de laatste bestemming waar je was? Bij nieuwe bestemmingen is dat nu wat gedoe
> NAAR: Het bestemmingsadres opvragen op basis van GPS waar de app is of ik ben met behulp van een Button.

## Status

| Document     | Status |
| ------------ | ------ |
| Requirements | ✅ Complete |
| Design       | ✅ Complete |
| Tasks        | ✅ Complete |

## Parent Spec

This enhancement belongs to the ZZP → Rittenregistratie feature area (see parent spec at `../`).
