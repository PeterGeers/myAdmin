# Dashboards

> Interactieve overzichten van je financiële transacties en analyses.

## Overzicht

De dashboards geven je een direct overzicht van je financiële data. Je kunt transacties doorzoeken, filteren en analyseren per referentienummer.

## Mutaties

Het Mutaties-rapport toont al je financiële transacties in een doorzoekbare tabel.

### Beschikbare filters

| Filter        | Beschrijving                                          |
| ------------- | ----------------------------------------------------- |
| Datum van/tot | Periode selecteren (standaard: huidig jaar)           |
| Administratie | Automatisch gefilterd op je tenant                    |
| W&V / Balans  | Filter op winst & verlies (W) of balansrekeningen (N) |

### Kolommen

| Kolom         | Beschrijving                  |
| ------------- | ----------------------------- |
| Datum         | Transactiedatum               |
| Referentie    | Referentienummer              |
| Omschrijving  | Transactieomschrijving        |
| Bedrag        | Transactiebedrag              |
| Rekening      | Grootboekrekeningnummer       |
| Rekeningnaam  | Naam van de grootboekrekening |
| Administratie | Tenant/administratie          |

### Functies

- **Sorteren** — Klik op een kolomkop om oplopend/aflopend te sorteren
- **Zoeken** — Typ in de zoekbalk onder elke kolom om te filteren
- **CSV export** — Klik op de exportknop om de gefilterde data als CSV te downloaden

!!! tip
Gebruik de zoekbalk onder "Omschrijving" om snel specifieke transacties te vinden, bijvoorbeeld een leveranciersnaam of factuurnummer.

## Referentie-analyse

Het Referentie-analyse rapport groepeert transacties per referentienummer. Dit is handig om alle boekingen bij een specifieke leverancier of project te zien.

### Hoe te gebruiken

1. Ga naar **Rapportages** → **Financieel** → **Referentie-analyse**
2. Stel de datumperiode in
3. Het rapport toont alle referentienummers met hun totaalbedragen
4. Klik op een referentienummer om de onderliggende transacties te zien

## Stap voor stap

### Transacties bekijken

1. Ga naar **Rapportages** → **Financieel** → **Mutaties**
2. Stel de gewenste datumperiode in
3. Gebruik de filters om de resultaten te verfijnen
4. Klik op kolomkoppen om te sorteren
5. Gebruik de zoekbalken voor specifieke zoekopdrachten

### Data exporteren

1. Pas de gewenste filters toe
2. Klik op de **CSV export** knop
3. Het bestand wordt gedownload met de gefilterde data

## Problemen oplossen

| Probleem             | Oorzaak                         | Oplossing                                          |
| -------------------- | ------------------------------- | -------------------------------------------------- |
| Geen data zichtbaar  | Verkeerde datumperiode          | Pas de datum van/tot aan                           |
| "No tenant selected" | Geen administratie geselecteerd | Selecteer een tenant in de navigatiebalk           |
| Tabel laadt langzaam | Grote datumperiode              | Beperk de periode of gebruik specifiekere filters  |
| Maximaal 1000 rijen  | Limiet bereikt                  | Verfijn je filters om minder resultaten te krijgen |
