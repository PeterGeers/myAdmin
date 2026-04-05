# Toeristenbelasting

> Gemeentelijke belasting op overnachtingen berekenen en rapporteren.

## Overzicht

Het toeristenbelastingrapport berekent de verschuldigde toeristenbelasting op basis van je STR-boekingen. De berekening is gebaseerd op het aantal overnachtingen en het geldende tarief.

## Wat je nodig hebt

- Geïmporteerde STR-boekingen (via de [STR-module](../str/importing-bookings.md))
- Toegang tot BNB-rapporten (`STR_Read` rechten)

## Hoe werkt de berekening?

De toeristenbelasting wordt berekend per boeking:

```
Toeristenbelasting = Bruto bedrag / (100 + toeristenbelasting%) × toeristenbelasting%
```

### Tarieven

| Periode    | Tarief | Berekenbasis                        |
| ---------- | ------ | ----------------------------------- |
| Vóór 2026  | 6,02%  | Over het bruto bedrag exclusief BTW |
| Vanaf 2026 | 6,9%   | Over het bruto bedrag exclusief BTW |

!!! info
Het tarief wordt automatisch bepaald op basis van de incheckdatum van de boeking. Je hoeft het tarief niet handmatig in te stellen.

## Stap voor stap

### 1. Open het rapport

Ga naar **Rapportages** → **BNB** → **Toeristenbelasting**.

### 2. Selecteer het jaar

Kies het jaar waarvoor je de toeristenbelasting wilt berekenen. Het systeem toont de beschikbare jaren op basis van je boekingsdata.

### 3. Genereer het rapport

Het rapport wordt automatisch geladen en toont:

- Totale toeristenbelasting voor het jaar
- Uitsplitsing per kwartaal
- Uitsplitsing per accommodatie
- Aantal overnachtingen per periode

### 4. Exporteer het rapport

Klik op **Export HTML** om het rapport te downloaden als HTML-bestand: `Aangifte_Toeristenbelasting_[Jaar].html`

Dit bestand kun je printen of meesturen met je aangifte bij de gemeente.

## Wat toont het rapport?

| Gegeven            | Beschrijving                             |
| ------------------ | ---------------------------------------- |
| Accommodatie       | Naam van het verhuurobject               |
| Kanaal             | Airbnb, Booking.com, VRBO of Direct      |
| Aantal boekingen   | Totaal aantal gerealiseerde boekingen    |
| Aantal nachten     | Totaal aantal overnachtingen             |
| Bruto omzet        | Totale boekingsprijs                     |
| Toeristenbelasting | Berekend bedrag per accommodatie/periode |

## Tips

!!! tip
Controleer het rapport per kwartaal als je gemeente kwartaalaangiften vereist. Sommige gemeenten vragen een jaarlijkse aangifte.

- De toeristenbelasting wordt alleen berekend over gerealiseerde boekingen (niet over geplande)
- Geannuleerde boekingen zonder inkomsten worden niet meegeteld
- Importeer alle boekingsbestanden voordat je het rapport genereert

## Problemen oplossen

| Probleem              | Oorzaak                                | Oplossing                                                                  |
| --------------------- | -------------------------------------- | -------------------------------------------------------------------------- |
| Rapport is leeg       | Geen STR-boekingen geïmporteerd        | Importeer eerst boekingen via de STR-module                                |
| Bedrag lijkt te laag  | Niet alle boekingen geïmporteerd       | Controleer of alle platforms (Airbnb, Booking.com, etc.) zijn geïmporteerd |
| Verkeerd tarief       | Incheckdatum valt in verkeerde periode | Controleer of de incheckdatums correct zijn in de boekingsdata             |
| Jaar niet beschikbaar | Geen boekingen in dat jaar             | Importeer boekingen voor het gewenste jaar                                 |
