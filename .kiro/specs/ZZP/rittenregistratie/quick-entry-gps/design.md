# Design Document — Quick Entry GPS Address Autofill

Parent spec: .kiro/specs/ZZP/rittenregistratie/

## 1. Overview

Two UX improvements to the existing "Snelle invoer" (Quick Entry) page (frontend/src/pages/ZZPTripQuick.tsx):

1. **GPS-based destination address lookup** — A "Locatie ophalen" button next to the END address field. Uses browser Geolocation API then reverse geocoding via OpenStreetMap Nominatim to fill the destination address.
2. **Auto-fill start address from last trip** — On page load / vehicle change, pre-fill start address with the previous trip's end_address for the selected vehicle.

All logic is frontend-only; no backend changes required.

## 2. Component Changes (ZZPTripQuick.tsx)

### 2.1 New state

- fetchingEndLoc: loading state for the GPS button (end address only)
- startAddress / endAddress (existing): populated by preset, auto-fill, or GPS lookup
- selectedVehicleId / lastTrip (existing): used to fetch previous trip end_address

### 2.2 GPS location handler (for end address only)

On tap: navigator.geolocation.getCurrentPosition({enableHighAccuracy:true, timeout:10000}) -> coords
-> fetch Nominatim reverse (?format=json&lat={lat}&lon={lon}&accept-language=nl&User-Agent header)
-> display_name -> setEndAddress.

Errors handled with toast messages (permission denied, timeout, no address, network error).
Button shows loading spinner while in flight. Debounced (~1.5s) to respect Nominatim 1 request/second limit.

### 2.3 UI

The END address field row (FormControl) gets an extra tappable button inside its HStack.
Label "Locatie ophalen" changes to "Locatie ophalen..." while fetching.
Min 44px touch target, orange color scheme matching page accents.

The START address field does NOT get a GPS button; it is auto-filled from last trip.

### 2.4 Auto-fill start address from last trip

Extend existing useEffect that fetches lastTrip when selectedVehicleId changes:
after fetching, if lastTrip?.end_address exists, setStartAddress(lastTrip.end_address); otherwise leave empty.

## 3. Data Flow

```
User taps "Locatie ophalen" (end field)
     -> navigator.geolocation.getCurrentPosition -> coords
     -> fetch Nominatim reverse (NL) -> display_name
     -> setEndAddress
```

```
Page load / vehicle change -> getTrips({vehicle_id, limit:1})
     -> lastTrip.end_address -> setStartAddress
```

## 4. Backend Changes

None — GPS lookup runs entirely in the browser.
Only resolved address string stored in zzp_trips.start_address / end_address.

## 5. Security & Privacy

- Browser prompts for location permission; denial handled gracefully
- GPS coordinates NOT persisted
- HTTPS required (browsers block geolocation on non-secure origins except localhost)
- Nominatim max 1 request/second; User-Agent header included

## 6. Translation Keys (trips.* namespace, NL default)

| Key | Value |
|---|---|
| trips.getLocation | Locatie ophalen |
| trips.gettingLocation | Locatie ophalen... |
| trips.locationError | Kon locatie niet bepalen |
| trips.locationPermissionDenied | Locatie toegang afgewezen |
| trips.noAddressFound | Geen adres gevonden voor deze locatie |
| trips.startAddressFromLastTrip | Vertrekadres automatisch ingevuld uit vorige rit |

## 7. Error Handling

| Situation | Behavior |
|---|---|
| Geolocation not supported | Toast: browser not supported |
| Permission denied | Toast: locatie toegang afgewezen |
| Timeout | Toast: kon locatie niet bepalen |
| No address returned | Toast: geen adres gevonden |
| Network error | Toast: fout bij ophalen adres |

## 8. Definition of Done

- GPS button renders next to end address field only
- Destination lookup completes and populates endAddress field
- Auto-fill start address from last trip works when previous trip exists
- Loading states, error toasts, rate-limit debounce present
- Unit tests for geolocation handler + auto-fill logic
- E2E Playwright tests for GPS flow + auto-fill flow
- CI/CD tasks listed (see tasks.md)
