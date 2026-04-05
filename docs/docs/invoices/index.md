# Facturen

> Upload facturen, laat AI de gegevens uitlezen en beheer alles via Google Drive.

## Overzicht

De module Facturen helpt je bij het verwerken van inkomende facturen. Upload een bestand, laat AI de belangrijkste gegevens uitlezen, controleer het resultaat en sla de transactie op in je administratie. Alle bestanden worden automatisch opgeslagen in Google Drive.

## Wat kun je hier doen?

| Taak                                          | Beschrijving                                    |
| --------------------------------------------- | ----------------------------------------------- |
| [Facturen uploaden](uploading-invoices.md)    | PDF's en andere bestanden uploaden en verwerken |
| [AI extractie](ai-extraction.md)              | Automatisch gegevens laten uitlezen door AI     |
| [Bewerken & goedkeuren](editing-approving.md) | Resultaten controleren, aanpassen en opslaan    |
| [Google Drive](google-drive.md)               | Bestanden beheren in Google Drive               |

## Typische workflow

```mermaid
graph LR
    A[Bestand uploaden] --> B[AI extractie]
    B --> C[Controleren]
    C --> D[Goedkeuren]
    D --> E[Opgeslagen]
```

1. **Upload** een factuur (PDF, afbeelding of e-mail)
2. **AI leest** automatisch de gegevens uit (datum, bedrag, BTW, leverancier)
3. **Controleer** de uitgelezen gegevens en pas aan waar nodig
4. **Keur goed** om de transactie op te slaan in de database
5. Het bestand wordt automatisch opgeslagen in **Google Drive**

## Ondersteunde bestandstypen

| Type            | Extensies               |
| --------------- | ----------------------- |
| PDF-documenten  | `.pdf`                  |
| Afbeeldingen    | `.jpg`, `.jpeg`, `.png` |
| E-mailberichten | `.eml`, `.mhtml`        |
| Spreadsheets    | `.csv`                  |

## Wat wordt er uitgelezen?

Bij elke factuur probeert het systeem de volgende gegevens te herkennen:

| Gegeven      | Beschrijving                                       |
| ------------ | -------------------------------------------------- |
| Datum        | Factuurdatum (omgezet naar JJJJ-MM-DD)             |
| Totaalbedrag | Eindbedrag inclusief BTW                           |
| BTW-bedrag   | Totaal BTW/omzetbelasting                          |
| Omschrijving | Factuurnummer, klantnummer of andere identificatie |
| Leverancier  | Naam van de leverancier                            |

!!! tip
Het systeem heeft 250+ leverancierspecifieke parsers als backup. Voor veelvoorkomende leveranciers zoals Amazon, Booking.com en energiebedrijven worden de gegevens extra nauwkeurig uitgelezen.
