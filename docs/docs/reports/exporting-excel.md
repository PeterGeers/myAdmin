# Excel export

> Rapportages exporteren naar Excel en CSV voor verdere analyse.

## Overzicht

myAdmin biedt meerdere exportmogelijkheden zodat je data kunt gebruiken in Excel, je boekhoudsoftware of voor je belastingadviseur.

## Beschikbare exports

| Export             | Formaat | Waar te vinden                                         |
| ------------------ | ------- | ------------------------------------------------------ |
| Mutaties           | CSV     | Rapportages → Financieel → Mutaties → CSV export       |
| Aangifte IB        | HTML    | Rapportages → Financieel → Aangifte IB → Export HTML   |
| Aangifte IB        | XLSX    | Rapportages → Financieel → Aangifte IB → Generate XLSX |
| BNB Omzet          | CSV     | Rapportages → BNB → BNB Omzet → Export                 |
| Financieel rapport | XLSX    | Via de XLSX-exportfunctie met sjabloon                 |

## Mutaties exporteren (CSV)

De snelste manier om transactiedata te exporteren:

1. Ga naar **Rapportages** → **Financieel** → **Mutaties**
2. Stel de gewenste filters in (datum, administratie, W&V/Balans)
3. Klik op **CSV export**
4. Het bestand wordt gedownload als `mutaties-[van]-[tot].csv`

Het CSV-bestand bevat: datum, referentie, omschrijving, bedrag, debet, credit en administratie.

## Aangifte IB exporteren

### HTML-export

1. Ga naar **Rapportages** → **Financieel** → **Aangifte IB**
2. Selecteer het jaar
3. Klik op **Export HTML**
4. Een opgemaakt HTML-bestand wordt gedownload dat je kunt printen of opslaan

### XLSX-export (Excel)

1. Ga naar **Rapportages** → **Financieel** → **Aangifte IB**
2. Selecteer het jaar
3. Klik op **Generate XLSX**
4. Het systeem genereert een Excel-bestand met:
   - Beginbalans
   - Alle transacties van het jaar
   - Gegroepeerd per grootboekrekening
   - Google Drive-links naar facturen (indien beschikbaar)

!!! info
De XLSX-export kan even duren omdat het systeem alle transacties verwerkt en Google Drive-links ophaalt. Je ziet een voortgangsbalk tijdens het genereren.

Het Excel-bestand wordt gegenereerd op basis van een sjabloon dat per administratie is geconfigureerd.

## Financieel rapport (XLSX)

Het uitgebreide financiële rapport bevat:

| Onderdeel           | Beschrijving                                               |
| ------------------- | ---------------------------------------------------------- |
| Beginbalans         | Saldi van alle balansrekeningen aan het begin van het jaar |
| Transacties         | Alle boekingen van het geselecteerde jaar                  |
| Grootboekrekeningen | Gegroepeerd per rekening met subtotalen                    |
| Documenten          | Links naar facturen in Google Drive                        |

## Tips

!!! tip
Exporteer je Aangifte IB als XLSX aan het einde van het boekjaar. Dit bestand bevat alles wat je belastingadviseur nodig heeft.

- CSV-exports bevatten de gefilterde data — pas eerst je filters aan
- XLSX-exports gebruiken een sjabloon met opmaak en formules
- HTML-exports zijn geschikt om te printen
- Alle exports respecteren de tenant-filtering — je ziet alleen data van je eigen administratie

## Problemen oplossen

| Probleem                   | Oorzaak                                | Oplossing                                                              |
| -------------------------- | -------------------------------------- | ---------------------------------------------------------------------- |
| Export is leeg             | Geen data in de geselecteerde periode  | Controleer je filters en datumperiode                                  |
| XLSX-export mislukt        | Sjabloon niet gevonden                 | Neem contact op met je beheerder                                       |
| Export duurt lang          | Veel transacties of Google Drive-links | Wacht tot de voortgangsbalk klaar is                                   |
| CSV bevat verkeerde tekens | Encoding-probleem                      | Open het bestand in Excel via "Gegevens importeren" met UTF-8 encoding |
