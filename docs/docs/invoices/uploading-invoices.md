# Facturen uploaden

> PDF's en andere bestanden uploaden en verwerken in myAdmin.

## Overzicht

Je uploadt facturen door een bestand te selecteren en een leveranciersmap te kiezen. Het systeem uploadt het bestand naar Google Drive, leest de inhoud uit en bereidt transacties voor die je kunt controleren en goedkeuren.

## Wat je nodig hebt

- Een factuurbestand (PDF, afbeelding, e-mail of CSV)
- Toegang tot de module Facturen (`invoices_create` rechten)

## Stap voor stap

### 1. Open de module Facturen

Ga in myAdmin naar **Facturen**. Je ziet het uploadformulier.

### 2. Kies een leveranciersmap

Typ de naam van de leverancier in het zoekveld. Het systeem filtert de beschikbare mappen terwijl je typt.

- Selecteer de juiste map uit de lijst
- Het filter moet precies 1 map tonen voordat je kunt uploaden

!!! info
Bestaat de leverancier nog niet? Klik op **Nieuwe map aanmaken** en voer de naam in. De map wordt aangemaakt in Google Drive.

### 3. Selecteer het bestand

Klik op **Bestand kiezen** en selecteer de factuur. Ondersteunde formaten:

- PDF (`.pdf`) — meest gebruikt
- Afbeeldingen (`.jpg`, `.jpeg`, `.png`)
- E-mailberichten (`.eml`, `.mhtml`)
- Spreadsheets (`.csv`)

### 4. Upload

Klik op **Uploaden**. Het systeem:

1. Uploadt het bestand naar Google Drive in de gekozen leveranciersmap
2. Controleert op duplicaten (bestandsnaam + map)
3. Leest de tekst uit het bestand
4. Laat AI de gegevens extraheren
5. Bereidt transactierecords voor op basis van sjablonen

Je ziet een voortgangsbalk tijdens het uploaden.

### 5. Duplicaatdetectie

Als het bestand al eerder is geüpload, verschijnt een waarschuwing met:

- Details van de bestaande transactie (datum, bedrag, omschrijving)
- Link naar het bestaande bestand in Google Drive

Je kunt kiezen:

| Actie             | Wat het doet                                        |
| ----------------- | --------------------------------------------------- |
| **Toch uploaden** | Het bestand opnieuw verwerken (maakt een duplicaat) |
| **Annuleren**     | De upload stoppen                                   |

!!! warning
Duplicaatdetectie controleert op bestandsnaam en leveranciersmap in de afgelopen 6 maanden. Hernoem een bestand niet om de controle te omzeilen.

### 6. Volgende stappen

Na een succesvolle upload zie je:

- De uitgelezen gegevens (zie [AI extractie](ai-extraction.md))
- Voorbereide transacties klaar voor controle (zie [Bewerken & goedkeuren](editing-approving.md))

## Tips

- Upload één factuur tegelijk voor de beste resultaten
- Gebruik duidelijke mapnamen die overeenkomen met de leveranciersnaam
- PDF-bestanden geven de beste extractieresultaten

## Problemen oplossen

| Probleem                                 | Oorzaak                           | Oplossing                                                                   |
| ---------------------------------------- | --------------------------------- | --------------------------------------------------------------------------- |
| "No file provided"                       | Geen bestand geselecteerd         | Selecteer eerst een bestand voordat je uploadt                              |
| "Invalid file type"                      | Niet-ondersteund bestandsformaat  | Gebruik PDF, JPG, PNG, EML, MHTML of CSV                                    |
| "No tenant selected"                     | Geen administratie geselecteerd   | Selecteer eerst een tenant in de navigatiebalk                              |
| "Please narrow down to exactly 1 folder" | Meerdere mappen in het filter     | Typ meer tekst om het filter te verfijnen tot 1 map                         |
| Upload mislukt                           | Google Drive-verbinding verbroken | Neem contact op met je beheerder om de Google Drive-koppeling te vernieuwen |
