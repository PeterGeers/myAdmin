# Requirements Document — Quick Entry GPS Address Autofill

Parent spec: .kiro/specs/ZZP/rittenregistratie/

## Introduction

This spec adds GPS location capture and automatic address pre-fill functionality to the ZZP Rittenregistratie quick-entry view. The feature addresses user feedback that manually typing start/end addresses is cumbersome for consecutive trips.

## Requirements

### Requirement 1: GPS Location Capture & Destination Address Lookup

**User Story:** As a ZZP user on the road, I want to capture my current GPS location and use it as the destination address with a single button tap, so that I do not have to manually type the destination.

#### Acceptance Criteria

1. THE quick-entry view SHALL provide a "Locatie ophalen" (Get Location) button next to the END address field only.
2. WHEN the user taps the button, THE system SHALL request GPS location via the browser Geolocation API (navigator.geolocation.getCurrentPosition).
3. UPON receiving coordinates, THE system SHALL perform reverse geocoding via OpenStreetMap Nominatim (https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}&accept-language=nl) to obtain a human-readable address.
4. THE fetched address SHALL be auto-populated into the endAddress field (destination).
5. THE system SHALL handle GPS permission denial gracefully with a user-friendly toast message.
6. THE system SHALL handle geocoding failures (timeout, no results) gracefully with a user-friendly toast message.
7. THE button SHALL show a loading state while fetching location/address.
8. THE system SHALL respect the 1 request/second rate limit of Nominatim by debouncing rapid clicks.
9. THE START address SHALL NOT be resolved via GPS; it SHALL be auto-filled from the previous trip (Requirement 2).
10. GPS coordinates SHALL NOT be stored in the database; only the resolved address string is saved.

#### Success Metrics

- Destination lookup completes in under 3 seconds on 4G.
- User can fill the destination address in under 5 seconds using the GPS button.
- Consecutive trips require zero manual typing.

### Requirement 2: Automatic Start Address Pre-fill from Last Trip

**User Story:** As a ZZP user, I want the start address to be automatically pre-filled from my last trip's end address, so that I don't have to re-enter it for consecutive trips.

#### Acceptance Criteria

1. WHEN loading the quick-entry view, IF the selected vehicle has a previous trip, THE start address field SHALL be pre-filled with the end_address of that last trip.
2. THE pre-fill SHALL happen automatically without user action.
3. THE start address SHALL NOT be auto-filled from the current GPS location; it SHALL only be set via auto-fill or manual entry.
4. THE user SHALL be able to override the pre-filled address manually (or via the GPS button if appropriate).
5. IF no previous trip exists for the vehicle, THE start address SHALL remain empty (user fills manually or via GPS).

#### Success Metrics

- Consecutive trips require zero manual start address entry.
- User never needs to type the same address twice in a row.
