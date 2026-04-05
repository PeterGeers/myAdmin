# Suggesties toepassen

> Een prijsstrategie genereren en gebruiken voor je verhuurobjecten.

## Overzicht

Je genereert een prijsstrategie door het systeem 14 maanden aan dagelijkse prijzen te laten berekenen. De aanbevelingen worden opgeslagen en kun je gebruiken als richtlijn voor het instellen van prijzen op je verhuurplatforms.

## Wat je nodig hebt

- Historische boekingsdata (minimaal een paar maanden)
- Geconfigureerde accommodaties met basistarieven
- Toegang tot de STR Prijzen module

## Stap voor stap

### 1. Open STR Prijzen

Ga in myAdmin naar **STR Prijzen**. Je ziet het prijzendashboard.

### 2. Selecteer een accommodatie

Kies een specifieke accommodatie uit de dropdown, of laat het leeg om voor alle accommodaties tegelijk te genereren.

### 3. Genereer de prijsstrategie

Klik op **Generate Pricing**. Het systeem:

1. Haalt historische boekingsdata op (laatste 24 maanden)
2. Berekent basistarieven per accommodatie (doordeweeks/weekend)
3. Analyseert bezettingsgraden en boekingstempo
4. Controleert evenementkalender voor opslagen
5. Vraagt AI om strategische inzichten (30 dagen)
6. Berekent dagelijkse prijzen voor 14 maanden (~420 dagen)
7. Slaat alle aanbevelingen op in de database

!!! info
Het genereren kan even duren (30-60 seconden) omdat het systeem AI-modellen raadpleegt en honderden dagprijzen berekent.

### 4. Bekijk de resultaten

Na het genereren verschijnt een bevestiging met het aantal gegenereerde dagprijzen. De aanbevelingen zijn nu zichtbaar in alle weergaven (zie [Aanbevelingen bekijken](viewing-recommendations.md)).

### 5. Gebruik de aanbevelingen

De aanbevolen prijzen zijn een richtlijn. Je kunt ze gebruiken om:

- Prijzen in te stellen op **Airbnb**, **Booking.com** en andere platforms
- Seizoenspatronen te herkennen en je strategie aan te passen
- Te controleren of je huidige prijzen in lijn zijn met de markt

!!! warning
De aanbevelingen zijn gebaseerd op historische data en AI-analyse. Gebruik ze als richtlijn, niet als absolute waarheid. Houd altijd rekening met lokale marktomstandigheden.

## Wat gebeurt er bij opnieuw genereren?

Wanneer je opnieuw genereert:

- Alle bestaande aanbevelingen voor de geselecteerde accommodatie worden verwijderd
- Nieuwe aanbevelingen worden berekend met de meest recente data
- De trendgrafiek en tabellen worden bijgewerkt

Dit is normaal en gewenst — je wilt altijd de meest actuele aanbevelingen.

## Tips

!!! tip
Genereer nieuwe aanbevelingen na elke grote import van boekingsdata. Zo houdt het systeem rekening met je nieuwste prestaties.

- Genereer voor alle accommodaties tegelijk om een consistent overzicht te krijgen
- Vergelijk de aanbevelingen met je werkelijke prijzen op de platforms
- Let op de AI-redenering in de dagelijkse tabel — deze geeft context bij de aanbeveling
- Basistarieven worden ingesteld per accommodatie in de listings-configuratie

## Problemen oplossen

| Probleem                       | Oorzaak                           | Oplossing                                                                   |
| ------------------------------ | --------------------------------- | --------------------------------------------------------------------------- |
| Genereren mislukt              | Geen API-sleutel geconfigureerd   | Neem contact op met je beheerder om de OpenRouter API-sleutel in te stellen |
| Alle prijzen zijn hetzelfde    | Geen historische data beschikbaar | Importeer eerst boekingsdata via de STR-module                              |
| Genereren duurt lang           | AI-model is traag                 | Wacht tot het proces is afgerond — dit kan tot 60 seconden duren            |
| Geen accommodaties in dropdown | Geen listings geconfigureerd      | Neem contact op met je beheerder om accommodaties toe te voegen             |
