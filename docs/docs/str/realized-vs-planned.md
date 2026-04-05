# Gerealiseerd vs gepland

> Het verschil tussen afgeronde en toekomstige boekingen en hoe ze worden opgeslagen.

## Overzicht

Bij het importeren van boekingen scheidt myAdmin ze automatisch in twee categorieën: **gerealiseerd** (verleden) en **gepland** (toekomst). Dit onderscheid is belangrijk voor je omzetrapportages en belastingaangiften.

## Hoe wordt het bepaald?

De scheiding is gebaseerd op de **incheckdatum** ten opzichte van vandaag:

| Categorie        | Regel                      | Voorbeeld                             |
| ---------------- | -------------------------- | ------------------------------------- |
| **Gerealiseerd** | Incheckdatum ≤ vandaag     | Inchecken was 15 maart → gerealiseerd |
| **Gepland**      | Incheckdatum > vandaag     | Inchecken is 20 juni → gepland        |
| **Geannuleerd**  | Status bevat "Geannuleerd" | Ongeacht datum, als er inkomsten zijn |

!!! info
Geannuleerde boekingen met inkomsten > €0 worden opgeslagen als gerealiseerd (je hebt immers annuleringskosten ontvangen). Geannuleerde boekingen zonder inkomsten worden overgeslagen.

## Waar worden ze opgeslagen?

| Categorie             | Database tabel | Gedrag                                                                             |
| --------------------- | -------------- | ---------------------------------------------------------------------------------- |
| **Gerealiseerd**      | `bnb`          | Permanent archief — boekingen worden toegevoegd, nooit overschreven                |
| **Gepland**           | `bnbplanned`   | Tijdelijk — wordt gewist en opnieuw gevuld bij elke import per kanaal/accommodatie |
| **Toekomstige omzet** | `bnbfuture`    | Samenvatting — geaggregeerde geplande omzet per datum/kanaal/accommodatie          |

### Waarom worden geplande boekingen overschreven?

Geplande boekingen veranderen voortdurend: nieuwe reserveringen komen erbij, bestaande worden geannuleerd of gewijzigd. Daarom vervangt elke import de geplande boekingen volledig voor het betreffende kanaal en accommodatie. Zo heb je altijd de meest actuele stand.

Gerealiseerde boekingen daarentegen zijn definitief en worden alleen toegevoegd (met duplicaatcontrole op reserveringscode).

## Wat zie je in de interface?

Na het importeren van een bestand zie je drie tabbladen:

### Tabblad "Gerealiseerd"

Toont alle boekingen met een incheckdatum in het verleden:

- Gastnaam, accommodatie, datums
- Aantal nachten en gasten
- Bruto bedrag, kanaalkosten, netto bedrag
- BTW en toeristenbelasting
- Reserveringscode en status

### Tabblad "Gepland"

Toont alle boekingen met een incheckdatum in de toekomst:

- Dezelfde velden als gerealiseerd
- Bedragen zijn schattingen (kunnen nog wijzigen)

### Tabblad "Al geladen"

Toont boekingen die al in de database staan (duplicaten):

- Deze worden niet opnieuw opgeslagen
- Herkenning op basis van reserveringscode + kanaal

## Impact op rapportages

| Rapportage         | Gebruikt                               |
| ------------------ | -------------------------------------- |
| BNB Omzet          | Gerealiseerde boekingen                |
| BNB Actuals        | Gerealiseerde boekingen (jaar-op-jaar) |
| Toeristenbelasting | Gerealiseerde boekingen                |
| Toekomstige omzet  | Geplande boekingen                     |
| Viooldiagrammen    | Gerealiseerde boekingen                |

!!! tip
Importeer regelmatig om de scheiding tussen gerealiseerd en gepland actueel te houden. Een boeking die vorige maand "gepland" was, wordt bij de volgende import automatisch "gerealiseerd" als de incheckdatum is verstreken.

## Problemen oplossen

| Probleem                                            | Oorzaak                                              | Oplossing                                                                    |
| --------------------------------------------------- | ---------------------------------------------------- | ---------------------------------------------------------------------------- |
| Boeking staat als "gepland" maar gast is al geweest | Bestand niet opnieuw geïmporteerd na de incheckdatum | Importeer het bestand opnieuw — de boeking wordt nu als gerealiseerd herkend |
| Geplande boekingen verdwenen                        | Normaal gedrag bij nieuwe import                     | Geplande boekingen worden vervangen bij elke import per kanaal               |
| Dubbele gerealiseerde boekingen                     | Zou niet moeten voorkomen                            | Het systeem controleert op reserveringscode + kanaal                         |
