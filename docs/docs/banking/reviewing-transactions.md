# Transacties controleren

> Geïmporteerde transacties bekijken, bewerken en opslaan naar de database.

## Overzicht

Na het importeren van een bankafschrift verschijnen de transacties in een bewerkbare tabel. Hier controleer je of alles klopt, vul je ontbrekende velden in en sla je de transacties op.

## Wat je nodig hebt

- Geïmporteerde transacties (via [Afschriften importeren](importing-statements.md))
- Toegang tot de module Bankzaken

## Stap voor stap

### 1. Bekijk de transactietabel

Na het importeren zie je een tabel met alle transacties. Elke transactie toont:

| Kolom            | Bewerkbaar | Beschrijving                                                        |
| ---------------- | ---------- | ------------------------------------------------------------------- |
| Datum            | ✅         | Transactiedatum (verplicht)                                         |
| Omschrijving     | ✅         | Beschrijving van de transactie (verplicht)                          |
| Bedrag           | ✅         | Transactiebedrag, moet groter zijn dan 0 (verplicht)                |
| Debet            | ✅         | Debetrekening met autocomplete dropdown (verplicht\*)               |
| Credit           | ✅         | Creditrekening met autocomplete dropdown (verplicht\*)              |
| Referentienummer | ✅         | Referentie, wordt vaak automatisch ingevuld door patronen           |
| Ref1             | ❌         | IBAN/rekeningnummer (alleen-lezen)                                  |
| Ref2             | ❌         | Volgnummer (alleen-lezen)                                           |
| Ref3             | ❌         | Saldo — klikbaar: opent Google Drive-link of kopieert naar klembord |
| Ref4             | ❌         | Bronbestandsnaam (alleen-lezen)                                     |
| Administratie    | ❌         | Automatisch ingesteld op je huidige tenant                          |

_\* Debet of Credit moet ingevuld zijn — niet allebei leeg._

### 2. Bewerk transacties

Klik op een veld om het te bewerken. Gebruik **Tab** of **Enter** om naar het volgende veld te gaan.

**Debet en Credit velden:**

- Typ een rekeningnummer om de autocomplete te activeren
- Het systeem toont beschikbare grootboekrekeningen voor je administratie
- Selecteer een rekening uit de lijst of typ het nummer handmatig

!!! tip
Gebruik eerst [Patronen toepassen](pattern-matching.md) om zoveel mogelijk velden automatisch te laten invullen. Daarna hoef je alleen de uitzonderingen handmatig aan te passen.

### 3. Voeg handmatig transacties toe

Je kunt ook handmatig nieuwe transacties toevoegen:

1. Klik op **Nieuw record toevoegen**
2. Vul alle verplichte velden in
3. De transactie verschijnt onderaan de tabel

### 4. Sla op

Als alle transacties correct zijn, klik je op **Opslaan**. Het systeem:

- Controleert of alle verplichte velden zijn ingevuld
- Controleert op duplicaten (op basis van volgnummer en IBAN)
- Slaat de transacties op in de database
- Toont een samenvatting: aantal opgeslagen, totaal, en eventueel overgeslagen duplicaten

!!! warning
Controleer altijd de debet- en creditrekeningen voordat je opslaat. Verkeerde toewijzingen beïnvloeden je rapportages en belastingaangiften.

## Tips

- Gebruik de **Tab**-toets om snel door de velden te navigeren
- Klik op het **Ref3**-veld om een Google Drive-link te openen (als het een URL bevat)
- Je kunt bestaande transacties ook bijwerken via dezelfde interface

## Problemen oplossen

| Probleem                      | Oorzaak                     | Oplossing                                                                          |
| ----------------------------- | --------------------------- | ---------------------------------------------------------------------------------- |
| Kan niet opslaan              | Verplichte velden zijn leeg | Controleer of Datum, Omschrijving, Bedrag en Debet/Credit zijn ingevuld            |
| Geen rekeningen in dropdown   | Geen lookup-data geladen    | Ververs de pagina — de rekeningen worden geladen bij het openen van de module      |
| Transactie wordt overgeslagen | Duplicaat volgnummer        | Het systeem slaat transacties over die al bestaan met hetzelfde volgnummer en IBAN |
