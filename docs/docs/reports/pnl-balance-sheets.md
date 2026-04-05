# W&V & Balans

> Winst- en verliesrekening en balans bekijken per jaar, kwartaal of maand.

## Overzicht

Het Actuals-rapport toont je financiële resultaten in een hiërarchische structuur. Je kunt inzoomen van jaarniveau naar kwartaal- en maandniveau, en meerdere jaren naast elkaar vergelijken.

## Wat je nodig hebt

- Geïmporteerde transacties in de database
- Toegang tot financiële rapporten (`Finance_Read` rechten)

## Structuur van het rapport

Het rapport is opgebouwd uit twee delen:

### Balans (VW = N)

Toont je bezittingen en schulden, gegroepeerd per hoofdcategorie:

| Categorie | Voorbeelden                            |
| --------- | -------------------------------------- |
| 1000      | Liquide middelen (bankrekeningen, kas) |
| 2000      | Schulden (BTW, crediteuren)            |
| 3000      | Eigen vermogen                         |

### Winst & Verlies (VW = W)

Toont je inkomsten en uitgaven:

| Categorie | Voorbeelden       |
| --------- | ----------------- |
| 4000      | Omzet (inkomsten) |
| 6000      | Bedrijfskosten    |
| 7000      | Overige kosten    |
| 8000      | Overige inkomsten |

## Stap voor stap

### 1. Open het rapport

Ga naar **Rapportages** → **Financieel** → **Actuals**.

### 2. Selecteer jaren

Kies een of meer jaren om te vergelijken. Je kunt meerdere jaren naast elkaar tonen.

### 3. Kies het detailniveau

| Niveau       | Wat je ziet                      |
| ------------ | -------------------------------- |
| **Jaar**     | Totalen per jaar per categorie   |
| **Kwartaal** | Q1, Q2, Q3, Q4 kolommen per jaar |
| **Maand**    | Jan t/m Dec kolommen per jaar    |

### 4. Kies het weergaveformaat

| Formaat           | Voorbeeld |
| ----------------- | --------- |
| 2 decimalen       | €1.234,56 |
| 0 decimalen       | €1.235    |
| Duizendtallen (K) | €1,2K     |
| Miljoenen (M)     | €0,0M     |

### 5. Bekijk de hiërarchie

Het rapport toont een uitklapbare structuur:

1. **Hoofdcategorie** (bijv. "4000") — Klik om uit te klappen
2. **Grootboekrekening** (bijv. "4010 Omzet verhuur") — Bedragen per periode

De beginbalans wordt automatisch berekend op basis van alle transacties vóór het geselecteerde jaar.

### 6. Grafieken

Het rapport bevat ook visuele weergaven:

- **Staafdiagram** — Inkomsten vs uitgaven per categorie
- **Taartdiagram** — Verdeling van kosten per categorie

## Tips

!!! tip
Vergelijk twee opeenvolgende jaren om trends te herkennen. Selecteer bijvoorbeeld 2025 en 2026 om de groei te zien.

- De beginbalans wordt automatisch berekend — je hoeft deze niet handmatig in te voeren
- Gebruik het kwartaalniveau voor BTW-aangiften
- Gebruik het maandniveau voor gedetailleerde cashflow-analyse
- Klik op een hoofdcategorie om de onderliggende rekeningen te zien

## Problemen oplossen

| Probleem               | Oorzaak                                    | Oplossing                                                 |
| ---------------------- | ------------------------------------------ | --------------------------------------------------------- |
| Beginbalans klopt niet | Transacties van voorgaande jaren ontbreken | Importeer alle historische transacties                    |
| Categorie toont €0     | Geen transacties in die periode            | Controleer of de juiste datumperiode is geselecteerd      |
| Rapport is leeg        | Geen data voor geselecteerd jaar           | Selecteer een jaar waarvoor transacties zijn geïmporteerd |
