# Rapportages

> Dashboards, winst- en verliesrekeningen, balansen en Excel-exports.

## Overzicht

De module Rapportages biedt twee groepen rapporten: **Financieel** (transacties, W&V, BTW, IB) en **BNB** (kortetermijnverhuur omzet en analyses). Alle rapporten zijn filterbaar per periode, administratie en categorie.

## Rapportgroepen

### Financiële rapporten

Beschikbaar via **Rapportages** → **Financieel**:

| Rapport                                                | Wat het toont                                                    |
| ------------------------------------------------------ | ---------------------------------------------------------------- |
| [Mutaties](dashboards.md#mutaties)                     | Alle transacties met filters op datum, rekening en administratie |
| [Actuals (W&V)](pnl-balance-sheets.md)                 | Winst- en verliesrekening en balans per jaar/kwartaal/maand      |
| [BTW](../tax/btw.md)                                   | BTW-aangifte per kwartaal                                        |
| [Referentie-analyse](dashboards.md#referentie-analyse) | Transacties gegroepeerd per referentienummer                     |
| [Aangifte IB](../tax/income-tax-ib.md)                 | Inkomstenbelasting overzicht per jaar                            |

### BNB rapporten

Beschikbaar via **Rapportages** → **BNB**:

| Rapport                                  | Wat het toont                              |
| ---------------------------------------- | ------------------------------------------ |
| [BNB Omzet](../str/revenue-summaries.md) | Omzet per accommodatie/kanaal met filters  |
| BNB Actuals                              | Jaar-op-jaar netto omzettotalen            |
| Viooldiagrammen                          | Verdeling prijs per nacht en verblijfsduur |
| Terugkerende gasten                      | Gasten met meerdere boekingen              |
| Toekomstige omzet                        | Geplande boekingen als trendlijn           |
| Toeristenbelasting                       | Berekende toeristenbelasting per periode   |
| Land van herkomst                        | Gastherkomst per land                      |

## Toegang

Je hebt specifieke rechten nodig om rapporten te bekijken:

| Rapportgroep | Vereiste rechten                                   |
| ------------ | -------------------------------------------------- |
| Financieel   | `Finance_CRUD`, `Finance_Read` of `Finance_Export` |
| BNB          | `STR_CRUD`, `STR_Read` of `STR_Export`             |

!!! info
Als je geen toegang hebt tot een rapportgroep, neem dan contact op met je beheerder.

## Gemeenschappelijke functies

Alle rapporten bieden:

- **Datumfilters** — Selecteer een periode (van/tot)
- **Tenant-filtering** — Data wordt automatisch gefilterd op je administratie
- **Sorteren** — Klik op kolomkoppen om te sorteren
- **Zoeken** — Typ in de zoekbalk om te filteren
- **Exporteren** — [Excel/CSV export](exporting-excel.md) voor verdere analyse

!!! tip
Selecteer altijd eerst de juiste tenant in de navigatiebalk voordat je rapporten bekijkt. Rapporten tonen alleen data van de geselecteerde administratie.
