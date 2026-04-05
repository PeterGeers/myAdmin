# Aanbevelingen bekijken

> Dagelijkse prijsaanbevelingen en trends bekijken per accommodatie.

## Overzicht

Na het genereren van een prijsstrategie kun je de aanbevelingen bekijken in verschillende weergaven: van een overzicht op hoog niveau tot gedetailleerde dagprijzen met alle onderliggende factoren.

## Wat je nodig hebt

- Gegenereerde prijsaanbevelingen (via [Suggesties toepassen](applying-suggestions.md))
- Toegang tot de STR Prijzen module (`str_read` rechten)

## Beschikbare weergaven

### Overzichtstabel met factoren

Toont de gemiddelde waarde van elke prijsfactor per accommodatie:

| Kolom        | Beschrijving                                |
| ------------ | ------------------------------------------- |
| Accommodatie | Naam van het verhuurobject                  |
| Basistarief  | Gemiddeld basistarief (doordeweeks/weekend) |
| Historisch   | Gemiddelde historische factor               |
| Bezetting    | Gemiddelde bezettingsfactor                 |
| Tempo        | Gemiddelde tempo-factor                     |
| Evenement    | Gemiddelde evenement-factor                 |
| AI-correctie | Vaste AI-opslag (1,05×)                     |

### Trendgrafiek

Een lijngrafiek die per maand toont:

- **Historische ADR** — Wat je vorig jaar verdiende per nacht
- **Aanbevolen ADR** — Wat het systeem aanbeveelt
- **Basistarief** — Je ingestelde basisprijzen

Hiermee zie je in één oogopslag of de aanbevelingen hoger of lager liggen dan je historische prestaties.

### Maandelijks overzicht

Een uitklapbare tabel per accommodatie met per maand:

- Alle 7 factoren afzonderlijk
- Aanbevolen prijs
- Vergelijking met vorig jaar

Klik op een accommodatie om de maandelijkse details te zien.

### Kwartaaloverzicht

Samenvatting per kwartaal (Q1–Q4):

- Aanbevolen ADR
- Historische ADR
- Verschil in percentage

### Dagelijkse aanbevelingen

Gedetailleerde tabel met per dag:

| Kolom            | Beschrijving                                   |
| ---------------- | ---------------------------------------------- |
| Datum            | De specifieke dag                              |
| Aanbevolen prijs | Berekende optimale prijs                       |
| AI ADR           | Door AI aanbevolen prijs                       |
| Historische ADR  | Prijs vorig jaar op dezelfde datum             |
| Verschil         | Procentueel verschil met historisch            |
| Weekend          | Of het een weekend-dag is                      |
| Evenement        | Naam van het evenement (indien van toepassing) |
| Opslag           | Evenement-opslag in procenten                  |
| Redenering       | AI-uitleg voor de aanbeveling                  |

!!! info
De tabel toont de eerste 50 dagen. Gebruik de filters om een specifieke accommodatie te selecteren.

## Stap voor stap

1. Ga naar **STR Prijzen**
2. Selecteer een accommodatie uit de dropdown (of bekijk alle)
3. Bekijk de trendgrafiek voor het grote plaatje
4. Klik op een accommodatie in het maandoverzicht voor details
5. Scroll naar de dagelijkse tabel voor specifieke datums

## Tips

!!! tip
Let op datums met een hoge evenement-factor — dit zijn de dagen waarop je de meeste omzet kunt genereren.

- Vergelijk de aanbevolen prijs met je huidige prijs op het platform
- Weekenddagen hebben doorgaans een hoger basistarief
- Een lage historische factor betekent dat je vorig jaar op die datum minder verdiende

## Problemen oplossen

| Probleem                     | Oorzaak                                | Oplossing                                                      |
| ---------------------------- | -------------------------------------- | -------------------------------------------------------------- |
| Geen aanbevelingen zichtbaar | Nog niet gegenereerd                   | Klik op "Generate Pricing" om aanbevelingen te genereren       |
| Historische ADR is 0         | Geen boekingen vorig jaar op die datum | Normaal voor nieuwe accommodaties of periodes zonder boekingen |
| Alle prijzen zijn gelijk     | Onvoldoende historische data           | Het systeem heeft minimaal een paar maanden boekingsdata nodig |
