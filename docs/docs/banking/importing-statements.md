# Afschriften importeren

> Bankafschriften uploaden als CSV en verwerken in myAdmin.

## Overzicht

Je kunt bankafschriften importeren door CSV-bestanden te uploaden die je hebt gedownload vanuit je internetbankieren. myAdmin herkent automatisch het bankformaat en zet de gegevens om naar transacties.

## Wat je nodig hebt

- Een CSV-bestand van je bank (Rabobank, Revolut of creditcard)
- Toegang tot de module Bankzaken (`banking_process` rechten)

## Stap voor stap

### 1. Download je bankafschrift

Log in bij je internetbankieren en download het afschrift als CSV-bestand.

**Rabobank:**

- Ga naar Transacties → Downloaden
- Kies formaat: CSV
- Bestanden beginnen met `CSV_O` of `CSV_A`

**Revolut:**

- Ga naar je transactieoverzicht
- Klik op Exporteren → CSV of TSV

### 2. Open de module Bankzaken

Ga in myAdmin naar **Bankzaken**. Je ziet het importscherm.

### 3. Selecteer bestanden

Klik op **Bestanden kiezen** en selecteer een of meer CSV-bestanden. Je kunt meerdere bestanden tegelijk selecteren.

!!! info
Het systeem controleert automatisch of de IBAN in het bestand bij jouw administratie hoort. Als dat niet het geval is, krijg je een foutmelding.

### 4. Verwerk de bestanden

Klik op **Verwerken**. myAdmin leest de bestanden en toont de transacties in een overzichtstabel.

Voor elke transactie worden de volgende velden ingevuld:

| Veld            | Bron                                  |
| --------------- | ------------------------------------- |
| Transactiedatum | Uit het CSV-bestand                   |
| Omschrijving    | Uit het CSV-bestand                   |
| Bedrag          | Uit het CSV-bestand (altijd positief) |
| Ref1            | IBAN/rekeningnummer                   |
| Ref2            | Volgnummer                            |
| Ref3            | Saldo na transactie                   |
| Ref4            | Bestandsnaam                          |

De velden **Debet**, **Credit** en **Referentienummer** zijn nog leeg — die vul je in de volgende stap in (handmatig of via patronen).

### 5. Volgende stappen

Na het importeren kun je:

- [Patronen toepassen](pattern-matching.md) om automatisch rekeningen in te vullen
- [Transacties controleren](reviewing-transactions.md) en handmatig aanpassen
- [Duplicaten controleren](handling-duplicates.md) voordat je opslaat

## Tips

!!! tip
Importeer afschriften in chronologische volgorde. Dit helpt bij het correct bijhouden van saldi en volgnummers.

- Je kunt meerdere CSV-bestanden tegelijk importeren
- Het systeem herkent automatisch welk bankformaat het bestand heeft
- Bestanden met een onbekend formaat worden overgeslagen met een foutmelding

## Problemen oplossen

| Probleem                                        | Oorzaak                              | Oplossing                                                                                       |
| ----------------------------------------------- | ------------------------------------ | ----------------------------------------------------------------------------------------------- |
| "No data found in files"                        | Leeg bestand of verkeerd formaat     | Controleer of het bestand transacties bevat en het juiste CSV-formaat heeft                     |
| "Access denied: IBAN does not belong to tenant" | IBAN hoort niet bij je administratie | Controleer of je het juiste bestand hebt geselecteerd en of je in de juiste administratie werkt |
| Bestand wordt niet herkend                      | Onbekend bankformaat                 | Controleer of het een ondersteund formaat is (Rabobank CSV, Revolut TSV/CSV)                    |
| Verkeerde tekens in omschrijvingen              | Encoding-probleem                    | Rabobank-bestanden gebruiken Latin-1 encoding — dit wordt automatisch afgehandeld               |
