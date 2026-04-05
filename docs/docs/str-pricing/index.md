# STR Prijzen

> AI-gestuurde prijsaanbevelingen voor je kortetermijnverhuur.

## Overzicht

De module STR Prijzen genereert dagelijkse prijsaanbevelingen voor je verhuurobjecten. Het systeem combineert historische boekingsdata, bezettingsgraden, seizoenspatronen en evenementen om optimale prijzen te berekenen voor de komende 14 maanden.

## Wat kun je hier doen?

| Taak                                                 | Beschrijving                                     |
| ---------------------------------------------------- | ------------------------------------------------ |
| [Aanbevelingen bekijken](viewing-recommendations.md) | Dagelijkse prijsaanbevelingen en trends bekijken |
| [Evenement prijzen](event-pricing.md)                | Prijsopslagen tijdens evenementen en seizoenen   |
| [Suggesties toepassen](applying-suggestions.md)      | Prijsstrategie genereren en gebruiken            |

## Hoe werkt het?

De prijsberekening gebruikt 7 factoren die samen de aanbevolen prijs bepalen:

| Factor             | Beschrijving                                   | Bereik    |
| ------------------ | ---------------------------------------------- | --------- |
| Basistarief        | Doordeweeks of weekend tarief per accommodatie | €85–€160  |
| Historische factor | Prestatie op dezelfde datum vorig jaar         | 0,5–1,0×  |
| Bezettingsfactor   | Bezettingsgraad in de betreffende periode      | 0,9–1,2×  |
| Tempo-factor       | Boekingstempo vergeleken met vorig jaar        | 0,9–1,15× |
| Evenement-factor   | Opslag tijdens evenementen en seizoenen        | 1,0–1,5×  |
| AI-correctie       | Vaste opslag op basis van AI-analyse           | 1,05×     |
| BTW-aanpassing     | Correctie voor BTW-tariefwijzigingen           | 1,0×      |

**Formule:**

```
Aanbevolen prijs = Basistarief × Historisch × Bezetting × Tempo × Evenement × AI × BTW
```

## Wat zie je?

De prijzenpagina toont:

- **Overzichtstabel** — Gemiddelde factoren per accommodatie
- **Trendgrafiek** — Historische ADR vs aanbevolen ADR vs basistarief over maanden
- **Maandelijks overzicht** — Uitklapbare tabel met alle factoren per maand
- **Kwartaaloverzicht** — Aanbevolen vs historische ADR per kwartaal
- **Dagelijkse aanbevelingen** — Gedetailleerde tabel met prijs per dag

!!! info
ADR staat voor Average Daily Rate — de gemiddelde dagprijs. Dit is de standaard maatstaf in de verhuurbranche.

## Typische workflow

1. **Genereer** een prijsstrategie voor de komende 14 maanden
2. **Bekijk** de aanbevelingen per accommodatie
3. **Analyseer** de trends en factoren
4. **Gebruik** de aanbevolen prijzen als richtlijn voor je platforms

!!! tip
Genereer regelmatig nieuwe aanbevelingen (maandelijks) om rekening te houden met recente boekingsdata en veranderende marktomstandigheden.
