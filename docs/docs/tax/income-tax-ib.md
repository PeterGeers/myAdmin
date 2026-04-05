# Inkomstenbelasting (IB)

> Jaarlijkse aangifte inkomstenbelasting voorbereiden en exporteren.

## Overzicht

Het Aangifte IB-rapport geeft een compleet overzicht van je financiële positie per jaar. Het toont alle grootboekrekeningen gegroepeerd in een hiërarchische structuur: balansrekeningen (bezittingen en schulden) en resultaatrekeningen (inkomsten en uitgaven).

## Wat je nodig hebt

- Alle transacties van het betreffende jaar geïmporteerd
- Toegang tot financiële rapporten (`Finance_Read` rechten)
- Een geselecteerde tenant/administratie

## Structuur van het rapport

Het rapport is opgebouwd uit drie niveaus:

| Niveau                  | Beschrijving                  | Voorbeeld                   |
| ----------------------- | ----------------------------- | --------------------------- |
| Hoofdcategorie (Parent) | Groep van rekeningen          | 1000, 2000, 4000            |
| Aangifte-categorie      | Subcategorie binnen de groep  | "Liquide middelen", "BTW"   |
| Rekening                | Individuele grootboekrekening | Bankrekening, Huurinkomsten |

### Balansrekeningen (1000–3000)

| Categorie | Inhoud                                 |
| --------- | -------------------------------------- |
| 1000      | Liquide middelen (bankrekeningen, kas) |
| 2000      | Schulden (BTW, crediteuren, leningen)  |
| 3000      | Eigen vermogen                         |

### Resultaatrekeningen (4000+)

| Categorie | Inhoud                                  |
| --------- | --------------------------------------- |
| 4000      | Omzet (inkomsten uit verhuur, diensten) |
| 5000–7000 | Kosten (bedrijfskosten, afschrijvingen) |
| 8000–9000 | Overige inkomsten en kosten             |

Het rapport berekent automatisch:

- **Resultaat** — Totaal van alle resultaatrekeningen (4000+)
- **Eindtotaal** — Moet dicht bij nul liggen als de boekhouding klopt

## Stap voor stap

### 1. Open het rapport

Ga naar **Rapportages** → **Financieel** → **Aangifte IB**.

### 2. Selecteer het jaar

Kies het jaar waarvoor je de aangifte wilt voorbereiden.

### 3. Bekijk het overzicht

Het rapport toont een uitklapbare tabel:

- Klik op een **hoofdcategorie** om de aangifte-categorieën te zien
- Klik op een **aangifte-categorie** om de individuele rekeningen te zien
- Elke rekening toont het totaalbedrag voor het jaar

### 4. Exporteer het rapport

Je hebt twee exportopties:

| Export            | Formaat       | Gebruik                                               |
| ----------------- | ------------- | ----------------------------------------------------- |
| **Export HTML**   | HTML-bestand  | Printen, opslaan, delen met belastingadviseur         |
| **Generate XLSX** | Excel-bestand | Gedetailleerde analyse, alle transacties per rekening |

!!! info
De XLSX-export bevat alle individuele transacties per grootboekrekening, inclusief beginbalans en Google Drive-links naar facturen. Dit kan even duren bij veel transacties.

## Jaarafsluiting

Het rapport bevat ook een sectie voor jaarafsluiting:

- Controle of het eindtotaal in balans is
- Overzicht van het resultaat (winst of verlies)
- Voorbereiding voor het volgende boekjaar

## Tips

!!! tip
Exporteer het XLSX-bestand aan het einde van het boekjaar en bewaar het samen met je belastingaangifte. Dit is je complete financiële dossier.

- Controleer of het eindtotaal dicht bij €0 ligt — grote afwijkingen duiden op ontbrekende of verkeerde boekingen
- Het resultaat (winst/verlies) is de basis voor je inkomstenbelasting
- Gebruik de HTML-export voor een snel overzicht, de XLSX-export voor details

## Problemen oplossen

| Probleem               | Oorzaak                                      | Oplossing                                         |
| ---------------------- | -------------------------------------------- | ------------------------------------------------- |
| Rapport is leeg        | Geen transacties voor het geselecteerde jaar | Importeer transacties of selecteer een ander jaar |
| Eindtotaal is niet nul | Boekhouding is niet in balans                | Controleer op ontbrekende of dubbele transacties  |
| XLSX-export duurt lang | Veel transacties en Google Drive-links       | Wacht tot de voortgangsbalk klaar is              |
| Rekening ontbreekt     | Geen transacties op die rekening             | Normaal als er geen boekingen zijn geweest        |
