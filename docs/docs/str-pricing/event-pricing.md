# Evenement prijzen

> Automatische prijsopslagen tijdens evenementen en seizoenen.

## Overzicht

Het systeem past automatisch prijsopslagen toe wanneer een datum samenvalt met een bekend evenement of seizoen. Dit zorgt ervoor dat je hogere prijzen hanteert op momenten van grote vraag.

## Hoe werkt het?

Evenementen zijn geconfigureerd met een datumbereik en een opslagpercentage. Wanneer een datum binnen het bereik van een evenement valt, wordt de evenement-factor toegepast op de aanbevolen prijs.

**Berekening:**

```
Evenement-factor = 1 + (opslagpercentage / 100)
```

Bijvoorbeeld: een evenement met 35% opslag geeft een factor van 1,35×.

## Geconfigureerde evenementen

| Evenement             | Periode                 | Opslag | Type            |
| --------------------- | ----------------------- | ------ | --------------- |
| Keukenhof             | Maart – Mei             | 25%    | Seizoen         |
| F1 Dutch Grand Prix   | Eind augustus (3 dagen) | 35–50% | Groot evenement |
| Amsterdam Dance Event | Half oktober (5 dagen)  | 35%    | Groot evenement |

!!! info
Evenementen worden jaarlijks bijgewerkt met de juiste datums. De exacte datums kunnen per jaar verschillen.

## Soorten evenementen

| Type                                | Beschrijving                                           | Typische opslag |
| ----------------------------------- | ------------------------------------------------------ | --------------- |
| **Seizoen** (`seasonal`)            | Langere periodes met verhoogde vraag (bijv. Keukenhof) | 5–25%           |
| **Groot evenement** (`major_event`) | Korte periodes met piekbelasting (bijv. F1, ADE)       | 35–50%          |

## Wat zie je in de aanbevelingen?

In de dagelijkse aanbevelingentabel zie je voor elke datum:

- **Evenement** — Naam van het evenement (leeg als er geen evenement is)
- **Opslag** — Het opslagpercentage
- **Evenement-factor** — De vermenigvuldigingsfactor in het factoroverzicht

Datums met een evenement hebben een merkbaar hogere aanbevolen prijs.

## Voorbeeld

Een accommodatie met een basistarief van €100 op een weekdag:

| Situatie            | Factoren                                  | Aanbevolen prijs |
| ------------------- | ----------------------------------------- | ---------------- |
| Normale dag         | 100 × 0,8 × 1,0 × 1,0 × **1,0** × 1,05 =  | €84              |
| Keukenhof (25%)     | 100 × 0,8 × 1,0 × 1,0 × **1,25** × 1,05 = | €105             |
| F1 Grand Prix (50%) | 100 × 0,8 × 1,0 × 1,0 × **1,50** × 1,05 = | €126             |

_Overige factoren vereenvoudigd voor dit voorbeeld._

## Tips

!!! tip
Controleer de evenementdatums aan het begin van elk jaar. Zorg dat ze overeenkomen met de officiële data.

- Grote evenementen hebben de hoogste opslag — dit zijn je beste verdienmomenten
- Seizoensevenementen duren langer maar hebben een lagere opslag
- De opslag wordt automatisch toegepast — je hoeft niets handmatig aan te passen

## Problemen oplossen

| Probleem                        | Oorzaak                               | Oplossing                                                                 |
| ------------------------------- | ------------------------------------- | ------------------------------------------------------------------------- |
| Geen evenement-opslag zichtbaar | Datum valt buiten het evenementbereik | Controleer de evenementdatums                                             |
| Opslag lijkt te laag            | Evenement is van het type "seizoen"   | Seizoensevenementen hebben bewust een lagere opslag dan grote evenementen |
| Evenement ontbreekt             | Nog niet geconfigureerd               | Neem contact op met je beheerder om het evenement toe te voegen           |
