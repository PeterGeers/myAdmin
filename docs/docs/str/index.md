# STR (Kortetermijnverhuur)

> Verwerk boekingen van Airbnb, Booking.com, VRBO en directe reserveringen.

## Overzicht

De STR-module verwerkt omzetbestanden van verhuurplatforms. Je importeert boekingsbestanden, het systeem berekent automatisch BTW, toeristenbelasting en kanaalkosten, en slaat alles op gescheiden in gerealiseerde en geplande boekingen.

## Wat kun je hier doen?

| Taak                                              | Beschrijving                                                          |
| ------------------------------------------------- | --------------------------------------------------------------------- |
| [Boekingen importeren](importing-bookings.md)     | Bestanden van Airbnb, Booking.com, VRBO of directe boekingen uploaden |
| [Gerealiseerd vs gepland](realized-vs-planned.md) | Het verschil tussen afgeronde en toekomstige boekingen                |
| [Omzet overzichten](revenue-summaries.md)         | Omzet, bezetting en trends bekijken                                   |

## Ondersteunde platforms

| Platform    | Bestandstype              | Bijzonderheden                                                |
| ----------- | ------------------------- | ------------------------------------------------------------- |
| Airbnb      | CSV                       | Nederlands formaat met kolommen als "Begindatum", "Inkomsten" |
| Booking.com | Excel (.xlsx/.xls) of CSV | Check-in/check-out, gastnamen, prijzen                        |
| VRBO        | CSV (meerdere bestanden)  | Reserveringen + Uitbetalingen apart                           |
| Direct      | Excel (.xlsx)             | Eigen directe boekingen                                       |
| Payout      | CSV                       | Booking.com maandelijkse afrekeningen                         |

## Wat wordt er berekend?

Bij elke boeking berekent het systeem automatisch:

| Gegeven            | Beschrijving                              |
| ------------------ | ----------------------------------------- |
| Bruto bedrag       | Totale boekingsprijs                      |
| Kanaalkosten       | Platformcommissie (bijv. 15% voor Airbnb) |
| BTW                | 9% (vóór 2026) of 21% (vanaf 2026)        |
| Toeristenbelasting | 6,02% (vóór 2026) of 6,9% (vanaf 2026)    |
| Netto bedrag       | Uitbetaald aan eigenaar                   |
| Prijs per nacht    | Netto bedrag ÷ aantal nachten             |

!!! info
Belastingtarieven worden automatisch bepaald op basis van de incheckdatum. Boekingen met inchecken vanaf 1 januari 2026 gebruiken de nieuwe tarieven.

## Typische workflow

1. **Download** het omzetbestand van je verhuurplatform
2. **Selecteer** het platform en upload het bestand
3. **Bekijk** de preview met gerealiseerde en geplande boekingen
4. **Controleer** de berekende bedragen
5. **Sla op** naar de database

!!! tip
Importeer regelmatig (maandelijks) om je omzetoverzichten actueel te houden. Geplande boekingen worden bij elke import bijgewerkt.
