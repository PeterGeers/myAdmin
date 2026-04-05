# Patronen herkenning

> Automatisch debet- en creditrekeningen laten invullen op basis van historische transacties.

## Overzicht

Patroonherkenning analyseert je transactiegeschiedenis van de afgelopen 2 jaar en gebruikt die om automatisch rekeningen toe te wijzen aan nieuwe transacties. Hoe meer transacties je verwerkt, hoe slimmer het systeem wordt.

## Wat je nodig hebt

- Geïmporteerde transacties in de bewerkingstabel
- Historische transacties in de database (hoe meer, hoe beter)

## Hoe werkt het?

Het systeem kijkt naar eerder verwerkte transacties en zoekt overeenkomsten:

1. **Analyse** — Het systeem doorzoekt de laatste 2 jaar aan transacties voor je administratie
2. **Patronen ontdekken** — Op basis van omschrijvingen en referentienummers worden patronen herkend
3. **Voorspellen** — Bij nieuwe transacties met vergelijkbare kenmerken worden rekeningen automatisch ingevuld

**Wat wordt er voorspeld?**

| Veld             | Wanneer                                                |
| ---------------- | ------------------------------------------------------ |
| Debetrekening    | Als de creditrekening een bankrekening is              |
| Creditrekening   | Als de debetrekening een bankrekening is               |
| Referentienummer | Als de omschrijving overeenkomt met een bekend patroon |

!!! info
Het systeem leert al vanaf de eerste transactie. Na één handmatige toewijzing kan het dezelfde toewijzing bij de volgende import automatisch voorstellen.

## Stap voor stap

### 1. Importeer transacties

Importeer eerst je bankafschrift via [Afschriften importeren](importing-statements.md). De transacties verschijnen in de tabel.

### 2. Klik op "Patronen toepassen"

Klik op de knop **Patronen toepassen** boven de transactietabel.

### 3. Bekijk de resultaten

Het systeem toont een samenvatting:

- **Patronen gevonden** — Aantal herkende patronen in je historie
- **Debet voorspellingen** — Aantal automatisch ingevulde debetrekeningen
- **Credit voorspellingen** — Aantal automatisch ingevulde creditrekeningen
- **Referentie voorspellingen** — Aantal automatisch ingevulde referentienummers
- **Gemiddelde betrouwbaarheid** — Percentage zekerheid van de voorspellingen

### 4. Controleer de resultaten

Automatisch ingevulde velden zijn visueel gemarkeerd in de tabel. Controleer of de voorspellingen kloppen:

- **Klopt het?** — Laat het staan en ga door
- **Klopt het niet?** — Pas het handmatig aan

!!! tip
De betrouwbaarheid stijgt naarmate je meer transacties verwerkt. Bij de eerste keer zijn er misschien weinig patronen, maar na een paar maanden worden de meeste transacties automatisch herkend.

## Hoe worden patronen opgebouwd?

Het systeem analyseert:

- **Trefwoorden** uit de transactieomschrijving
- **Referentienummers** van eerdere transacties
- **Combinaties** van omschrijving + referentie

Een patroon wordt aangemaakt wanneer:

- Eén kant van de boeking een bankrekening is (debet of credit)
- De andere kant een grootboekrekening is
- Er minimaal 1 eerdere transactie met dezelfde kenmerken bestaat

De betrouwbaarheidsscore groeit met het aantal overeenkomsten (maximaal 100% bij 10+ matches).

## Tips

- Pas patronen toe **vóór** het handmatig bewerken — zo bespaar je het meeste tijd
- Patronen zijn specifiek per administratie — elke tenant heeft eigen patronen
- Na het opslaan van nieuwe transacties worden de patronen automatisch bijgewerkt
- Je kunt patronen meerdere keren toepassen op dezelfde set transacties

## Problemen oplossen

| Probleem                       | Oorzaak                                         | Oplossing                                                              |
| ------------------------------ | ----------------------------------------------- | ---------------------------------------------------------------------- |
| Geen patronen gevonden         | Geen historische transacties                    | Verwerk eerst handmatig een paar maanden aan transacties               |
| Verkeerde rekening voorgesteld | Patroon gebaseerd op verkeerde historische data | Corrigeer de toewijzing handmatig — het systeem leert van de correctie |
| Weinig voorspellingen          | Te weinig historische data                      | Het systeem wordt beter naarmate je meer transacties verwerkt          |
