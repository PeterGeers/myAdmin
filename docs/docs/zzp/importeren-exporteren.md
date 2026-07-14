# Importeren & Exporteren

> Historische ritten importeren en je administratie exporteren voor de Belastingdienst.

## Overzicht

Met de import- en exportfunctie kun je:

- **Importeren** — historische ritten inladen vanuit CSV of Excel (bijv. bij overstap van een ander systeem)
- **Exporteren** — je rittenadministratie downloaden als PDF, CSV of Excel

!!! info
Importeren is bedoeld voor eenmalige migratie van historische data. Voor dagelijks gebruik registreer je ritten via het reguliere invoerscherm of de [Snelle Invoer](snelle-invoer.md).

## Wat je nodig hebt

- Toegang tot de ZZP-module (`zzp_crud` rechten)
- Minimaal één geregistreerd voertuig
- Een CSV- of Excel-bestand met je ritgegevens (voor import)

---

## Importeren

### Stap 1: Template downloaden

Download eerst de importtemplate zodat je bestand het juiste formaat heeft:

1. Ga naar **ZZP** → **Rittenregistratie**
2. Klik op **Importeren**
3. Klik op **Download template**
4. Kies **CSV** of **Excel**

De template bevat alle kolommen met voorbeelddata en uitleg.

[Screenshot: importdialoog met download template knop]

### Stap 2: Bestand voorbereiden

Vul de template in met je historische ritten. Let op de volgende vereisten:

| Kolom          | Formaat                      | Verplicht | Voorbeeld                    |
| -------------- | ---------------------------- | --------- | ---------------------------- |
| Datum          | DD-MM-JJJJ                   | Ja        | 15-03-2025                   |
| Startadres     | Vrije tekst                  | Ja        | Amsterdam, Keizersgracht 100 |
| Eindadres      | Vrije tekst                  | Ja        | Utrecht, Jaarbeursplein 1    |
| Begin km-stand | Geheel getal                 | Ja        | 45000                        |
| Eind km-stand  | Geheel getal                 | Ja        | 45045                        |
| Ritdoel        | Tekst uit de keuzelijst      | Ja        | Klantbezoek                  |
| Categorie      | Zakelijk / Privé / Woon-werk | Ja        | Zakelijk                     |
| Klant          | Naam of klant-ID             | Nee       | Bedrijf BV                   |
| Opmerkingen    | Vrije tekst                  | Nee       | Bespreking Q1 resultaten     |

!!! warning "Belangrijk voor CSV-bestanden" - Gebruik **puntkomma (;)** als scheidingsteken (standaard voor Nederlandse Excel) - Gebruik **UTF-8** als tekencodering - De eerste rij moet kolomkoppen bevatten - Datums in formaat DD-MM-JJJJ (niet Amerikaans MM/DD/YYYY)

!!! tip
Sorteer je ritten op datum en km-stand (oplopend) voordat je importeert. Dit maakt de validatie eenvoudiger.

### Stap 3: Importeren

1. Ga naar **ZZP** → **Rittenregistratie** → **Importeren**
2. Selecteer het **voertuig** waarvoor je importeert
3. Klik op **Bestand kiezen** en selecteer je CSV of Excel-bestand
4. Klik op **Uploaden**

### Stap 4: Kolommen koppelen

Als je kolomnamen afwijken van de template, verschijnt het koppelscherm:

1. Koppel elke kolom uit je bestand aan het juiste veld
2. Markeer kolommen die je wilt overslaan
3. Klik op **Volgende**

[Screenshot: kolom-mapping interface]

!!! info
Als je de template hebt gebruikt, worden de kolommen automatisch herkend en kun je deze stap overslaan.

### Stap 5: Validatie controleren

Het systeem controleert alle records en toont de resultaten:

| Status          | Pictogram | Betekenis                                          | Actie                 |
| --------------- | --------- | -------------------------------------------------- | --------------------- |
| ✅ OK           | Groen     | Record is geldig en klaar voor import              | Geen actie nodig      |
| ⚠️ Waarschuwing | Oranje    | Record is geldig maar heeft een aandachtspunt      | Controleer en beslis  |
| ❌ Fout         | Rood      | Record is ongeldig en kan niet worden geïmporteerd | Corrigeer of sla over |

#### Veelvoorkomende validatiefouten

| Fout                     | Oorzaak                                       | Oplossing                                      |
| ------------------------ | --------------------------------------------- | ---------------------------------------------- |
| Km-stand niet oplopend   | Eind km-stand ≤ begin km-stand                | Corrigeer de km-standen                        |
| Km-gat gedetecteerd      | Begin km-stand sluit niet aan op vorige rit   | Voeg ontbrekende rit toe of accepteer gap-fill |
| Ongeldig datumformaat    | Datum niet in DD-MM-JJJJ formaat              | Pas het datumformaat aan                       |
| Verplicht veld ontbreekt | Een verplichte kolom is leeg                  | Vul het ontbrekende veld in                    |
| Duplicaat gedetecteerd   | Zelfde voertuig + datum + km-stand bestaat al | Verwijder het duplicaat of sla het record over |
| Ongeldige categorie      | Categorie komt niet overeen met de keuzelijst | Gebruik: Zakelijk, Privé of Woon-werk          |

### Stap 6: Fouten corrigeren of overslaan

1. Klik op een rij met een fout om deze te bewerken
2. Corrigeer de waarde in het inline bewerkingsveld
3. Of klik op **Overslaan** om het record niet te importeren
4. Klik op **Opnieuw valideren** om de wijzigingen te controleren

### Stap 7: Import bevestigen

1. Controleer de samenvatting:
   - Aantal records: OK / Waarschuwing / Fout / Overgeslagen
2. Klik op **Importeren**
3. Wacht tot de import is voltooid
4. Bekijk het resultaat: aantal geïmporteerde ritten en eventuele fouten

!!! info
De import wordt vastgelegd in de audittrail met: wie, wanneer, hoeveel records en het bronbestand.

---

## Exporteren

### Beschikbare formaten

| Formaat   | Beste voor                                   | Bevat                                                  |
| --------- | -------------------------------------------- | ------------------------------------------------------ |
| **PDF**   | Belastingdienst, accountant, archief         | Alle wettelijk vereiste velden, totalen, ondertekening |
| **CSV**   | Eigen verwerking in Excel of andere software | Ruwe data, geschikt voor filtering en berekeningen     |
| **Excel** | Kant-en-klaar overzicht met opmaak           | Opgemaakte tabel, samenvattingen per categorie         |

### Exporteren

1. Ga naar **ZZP** → **Rittenregistratie**
2. Stel de gewenste filters in:
   - **Datumbereik** — bijv. 01-01-2025 tot 31-12-2025
   - **Voertuig** — één specifiek voertuig of alle voertuigen
   - **Categorie** — alle, alleen zakelijk, alleen privé, of alleen woon-werk
   - **Klant** — optioneel filteren op klant
3. Klik op **Exporteren**
4. Kies het formaat: **PDF**, **CSV** of **Excel**
5. Het bestand wordt gedownload

[Screenshot: exportdialoog met filters en formaatkeuze]

### PDF-export voor de Belastingdienst

De PDF-export is specifiek ontworpen om te voldoen aan de eisen van de Belastingdienst:

- Alle ritten per voertuig, gesorteerd op datum
- Per rit: datum, startadres, eindadres, begin km-stand, eind km-stand, afstand, ritdoel, categorie
- Totaaloverzicht per categorie (zakelijk / privé / woon-werk)
- Jaaroverzicht geschikt voor aangifte inkomstenbelasting (IB)

!!! tip
Exporteer aan het einde van elk kalenderjaar een volledige PDF voor je archief. Bewaar deze minimaal 7 jaar (wettelijke bewaarplicht).

### CSV/Excel-export voor eigen gebruik

De CSV- en Excel-exports bevatten alle beschikbare velden:

- Alle velden uit de PDF-export
- Plus: klant, project, opmerkingen, factuurnummer, status, correctiehistorie

Dit formaat is geschikt voor:

- Eigen analyses in Excel of Google Sheets
- Doorlevering aan je boekhouder
- Import in andere software

## Problemen oplossen

| Probleem                     | Oorzaak                                  | Oplossing                                              |
| ---------------------------- | ---------------------------------------- | ------------------------------------------------------ |
| Import mislukt volledig      | Bestand is niet leesbaar                 | Controleer of het een geldig CSV of xlsx-bestand is    |
| Veel validatiefouten         | Verkeerd datumformaat of scheidingsteken | Gebruik DD-MM-JJJJ en puntkomma als scheidingsteken    |
| Kolommen worden niet herkend | Kolomnamen wijken af van de template     | Gebruik de kolomkoppeling of download de template      |
| Export bevat geen data       | Filters zijn te strikt                   | Verruim het datumbereik of verwijder filters           |
| PDF is leeg                  | Geen ritten in de geselecteerde periode  | Controleer of er ritten zijn voor het gekozen voertuig |
