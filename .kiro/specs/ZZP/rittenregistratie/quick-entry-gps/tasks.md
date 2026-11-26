# Implementation Plan — Quick Entry GPS Address Autofill

Parent spec: .kiro/specs/ZZP/rittenregistratie/

## Overview
Add two UX improvements to `frontend/src/pages/ZZPTripQuick.tsx`:
1. "Locatie ophalen" button next to the END address field → browser Geolocation API + OpenStreetMap Nominatim reverse geocoding.
2. Auto-fill start address from the selected vehicle's last trip end_address (NOT via GPS).

No backend changes required.

## Task Dependencies
- Existing services: `getTrips`, `vehicleService`, route presets, odometer tracking.
- New: none.

## Tasks

### Wave 1: Frontend Core (~1.5 days)
- [x] Add "Locatie ophalen" tappable button beside the `endAddress` input in ZZPTripQuick.tsx (only end address, not start)
- [x] Implement shared geolocation handler (`navigator.geolocation.getCurrentPosition({enableHighAccuracy:true, timeout:10000})`)
- [x] On success, fetch Nominatim reverse JSON (`https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}&accept-language=nl`); set resolved address into `endAddress` state
- [x] Handle errors: permission denied, timeout, no results → user-friendly toast messages
- [x] Button shows loading spinner while fetching; apply debounce (~1.5s) to respect Nominatim's 1 request/second limit
- [x] Include `User-Agent` header in Nominatim request for production compliance
- [x] Add i18n keys under `trips.*` namespace (NL default): `trips.getLocation`, `trips.gettingLocation`, `trips.locationError`, `trips.locationPermissionDenied`, `trips.noAddressFound`, `trips.startAddressFromLastTrip`
- [x] Unit tests: geolocation handler (success, error, permission denial), Nominatim response parsing, auto-fill start address from last trip
- [x] E2E Playwright tests: GPS button fills end address, auto-fill start address works, error handling

### Wave 2: Auto-fill Start Address from Last Trip (~0.5 day)
- [x] Extend existing effect that updates `selectedVehicleId` → after fetching last trip, if `lastTrip?.end_address` exists, set `startAddress = lastTrip.end_address`
- [x] Allow manual edit/overwrite of auto-filled value
- [x] Test consecutive-trip flow: same vehicle, zero manual typing

### Wave 3: PWA Manifest (Mobile Quick Entry)
- [x] Add `/zzp/ritten/quick` standalone entry point, icons, theme colors, background color
- [x] Verify "Add to Home Screen" works on mobile browsers

### Wave 4: CI/CD & Quality Gates
- [x] **Deploy frontend → PRODUCTION**: Configure `deploy-frontend.yml` so the `frontend` branch builds, runs `npm run test:run` (vitest) + E2E Playwright tests, lints, typechecks, and publishes to GitHub Pages (PROD_URL). Trigger on push to `main`/`frontend`.
- [x] **CodeQL scan**: Run `codeql.yml` matrix (actions, javascript-typescript, python) on every PR and on push; no critical/high findings allowed before merge.
- [x] **GitGuardian (ggshield) pre-commit & PR gate**: Install `ggshield` locally (`ggshield install --mode local --force`), enable offline scanning per `.gitguardian.yaml`, and require clean scans on PRs targeting `main`.
- [x] **PR test requirements**: Every PR must include frontend unit tests (`npx vitest run`) and E2E Playwright tests (`npx playwright test -t e2e`); pipeline fails on failure.
- [x] **Build & test job**: Extend `frontend-ci.yml` build step to run the full test suite and upload reports.
- [x] **Env parity guard**: Keep `frontend-env-parity` job verifying VITE_* env vars match build and deploy jobs.
- [x] **PWA manifest tag**: Confirm `manifest.json` includes the `apple-mobile-web-app-capable` meta tag.

## Notes
- Estimated total ~3 days work across parallel tracks.
