# Belastingen

> BTW-aangiften, inkomstenbelasting en toeristenbelasting voorbereiden.

## Overzicht

De module Belastingen helpt je bij het voorbereiden van je belastingaangiften. Het systeem berekent de bedragen op basis van je geïmporteerde transacties en boekingen, zodat je de juiste gegevens hebt voor de Belastingdienst.

## Wat kun je hier doen?

| Taak                                        | Beschrijving                                 |
| ------------------------------------------- | -------------------------------------------- |
| [BTW aangifte](btw.md)                      | Kwartaalaangifte omzetbelasting voorbereiden |
| [Inkomstenbelasting (IB)](income-tax-ib.md) | Jaarlijkse aangifte inkomstenbelasting       |
| [Toeristenbelasting](toeristenbelasting.md) | Gemeentelijke belasting op overnachtingen    |

## Overzicht belastingtypen

| Belasting          | Frequentie   | Bron                   | Berekening                           |
| ------------------ | ------------ | ---------------------- | ------------------------------------ |
| BTW                | Per kwartaal | Financiële transacties | Omzet × BTW-tarief − Voorbelasting   |
| IB                 | Per jaar     | Alle transacties       | Winst uit onderneming − Aftrekposten |
| Toeristenbelasting | Per jaar     | STR-boekingen          | Aantal nachten × Tarief per nacht    |

## BTW-tarieven

| Tarief | Toepassing                                           |
| ------ | ---------------------------------------------------- |
| 21%    | Standaardtarief (de meeste goederen en diensten)     |
| 9%     | Verlaagd tarief (o.a. kortetermijnverhuur vóór 2026) |
| 0%     | Vrijgesteld                                          |

!!! warning
Vanaf 1 januari 2026 is het BTW-tarief voor kortetermijnverhuur gewijzigd van 9% naar 21%. Het systeem past automatisch het juiste tarief toe op basis van de datum.

## Waar vind je de rapporten?

De belastingrapporten zijn beschikbaar op twee plekken:

- **Rapportages** → **Financieel** → **BTW** en **Aangifte IB** tabbladen
- **Rapportages** → **BNB** → **Toeristenbelasting** tabblad

## Tips

!!! tip
Bereid je BTW-aangifte voor aan het einde van elk kwartaal. Zo heb je altijd actuele gegevens voor de Belastingdienst.

- Zorg dat alle transacties zijn geïmporteerd voordat je een aangifte genereert
- Exporteer rapporten als HTML of XLSX voor je administratie
- De toeristenbelasting wordt berekend op basis van je STR-boekingen — importeer deze eerst
