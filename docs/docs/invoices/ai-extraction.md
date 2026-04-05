# AI extractie

> Automatisch gegevens laten uitlezen uit facturen door AI.

## Overzicht

Wanneer je een factuur uploadt, leest AI automatisch de belangrijkste gegevens uit. Het systeem combineert AI-modellen met 250+ leverancierspecifieke parsers om de beste resultaten te leveren.

## Hoe werkt het?

### Stap 1: Tekst extractie

Het systeem leest eerst de tekst uit het bestand:

- **PDF**: Tekst wordt direct uit het document gehaald
- **Afbeeldingen**: OCR (optische tekenherkenning) wordt gebruikt
- **E-mail**: De berichttekst en bijlagen worden verwerkt

### Stap 2: AI-analyse

De uitgelezen tekst wordt naar een AI-model gestuurd dat de volgende gegevens probeert te herkennen:

| Gegeven      | Formaat    | Voorbeeld                                |
| ------------ | ---------- | ---------------------------------------- |
| Datum        | JJJJ-MM-DD | 2026-03-15                               |
| Totaalbedrag | Getal      | 125.50                                   |
| BTW-bedrag   | Getal      | 21.84                                    |
| Omschrijving | Tekst      | Factuurnummer: 2026-0042, Klantnr: 12345 |
| Leverancier  | Tekst      | Eneco                                    |

!!! info
Het systeem gebruikt eerdere transacties van dezelfde leverancier als context. Hierdoor worden herhalende facturen steeds nauwkeuriger herkend.

### Stap 3: Leverancierspecifieke parsers

Naast AI heeft het systeem 250+ ingebouwde parsers voor veelvoorkomende leveranciers. Deze parsers kennen het exacte formaat van facturen van leveranciers zoals:

- Amazon, Bol.com
- Booking.com, Airbnb
- Energiebedrijven (Eneco, Vattenfall)
- Telecombedrijven (KPN, T-Mobile)
- En vele anderen

De parser wordt automatisch gekozen op basis van de leveranciersmap.

## Wat zie je na de extractie?

Na het uploaden verschijnt een overzicht met de uitgelezen gegevens:

- **Map** — De leveranciersmap
- **Bestandsnaam** — Naam van het geüploade bestand
- **Datum** — Uitgelezen factuurdatum
- **URL** — Link naar het bestand in Google Drive
- **Totaalbedrag** — Uitgelezen bedrag (€)
- **BTW-bedrag** — Uitgelezen BTW (€)
- **Omschrijving** — Factuurnummer en andere identificatie

!!! tip
Controleer altijd de uitgelezen gegevens. AI is goed maar niet perfect — vooral bij ongebruikelijke factuurindelingen kan het resultaat afwijken.

## Wanneer werkt AI-extractie het beste?

- **Digitale PDF's** (niet gescand) geven de beste resultaten
- **Standaard factuurindelingen** met duidelijke labels
- **Leveranciers die eerder zijn verwerkt** — het systeem leert van eerdere transacties

## Wanneer werkt het minder goed?

- **Gescande documenten** met slechte kwaliteit
- **Handgeschreven facturen**
- **Ongebruikelijke indelingen** zonder duidelijke labels
- **Buitenlandse facturen** met onbekende valuta

In deze gevallen kun je de gegevens handmatig aanpassen in de volgende stap (zie [Bewerken & goedkeuren](editing-approving.md)).

## Problemen oplossen

| Probleem                 | Oorzaak                              | Oplossing                                                                   |
| ------------------------ | ------------------------------------ | --------------------------------------------------------------------------- |
| Geen gegevens uitgelezen | Bestand bevat geen leesbare tekst    | Controleer of het een digitale PDF is (niet een scan van slechte kwaliteit) |
| Verkeerd bedrag          | AI heeft het verkeerde bedrag gepakt | Pas het bedrag handmatig aan in het bewerkingsscherm                        |
| Verkeerde datum          | Meerdere datums in het document      | Selecteer de juiste datum handmatig                                         |
| BTW is 0.00              | BTW niet gevonden in het document    | Vul het BTW-bedrag handmatig in                                             |
