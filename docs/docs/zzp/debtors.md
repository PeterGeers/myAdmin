# Debiteuren & crediteuren

> Openstaande vorderingen en schulden beheren.

## Overzicht

Het debiteuren- en crediteurenoverzicht geeft je inzicht in wie jou nog geld verschuldigd is (debiteuren) en aan wie jij nog geld verschuldigd bent (crediteuren). Je ziet in één oogopslag welke facturen openstaan, welke verlopen zijn, en je kunt betalingsherinneringen versturen.

## Wat je nodig hebt

- Toegang tot de ZZP-module (`zzp_read` rechten)
- Verstuurde facturen in je administratie

## Stap voor stap

### 1. Openstaande vorderingen bekijken (debiteuren)

1. Ga naar **ZZP** → **Debiteuren**
2. Je ziet een overzicht van alle uitgaande facturen met de status "verstuurd" of "verlopen"
3. De facturen zijn gegroepeerd per contact

| Kolom         | Beschrijving                            |
| ------------- | --------------------------------------- |
| Contact       | Naam en Klant-ID van de debiteur        |
| Factuurnummer | Nummer van de openstaande factuur       |
| Factuurdatum  | Datum van de factuur                    |
| Vervaldatum   | Datum waarop de betaling verwacht wordt |
| Bedrag        | Openstaand bedrag                       |
| Status        | Verstuurd of verlopen                   |
| Dagen open    | Aantal dagen sinds de factuurdatum      |

### 2. Openstaande schulden bekijken (crediteuren)

1. Ga naar **ZZP** → **Crediteuren**
2. Je ziet een overzicht van alle inkomende facturen die nog niet betaald zijn
3. De facturen zijn gegroepeerd per leverancier

### 3. Verouderingsanalyse

De verouderingsanalyse toont openstaande bedragen per ouderdomscategorie:

| Categorie   | Beschrijving                          |
| ----------- | ------------------------------------- |
| Lopend      | Nog niet verlopen                     |
| 1-30 dagen  | 1 tot 30 dagen over de vervaldatum    |
| 31-60 dagen | 31 tot 60 dagen over de vervaldatum   |
| 61-90 dagen | 61 tot 90 dagen over de vervaldatum   |
| 90+ dagen   | Meer dan 90 dagen over de vervaldatum |

!!! warning
Facturen in de categorie 90+ dagen vereisen extra aandacht. Overweeg juridische stappen of het afboeken van de vordering.

### 4. Betalingen controleren

Het systeem kan automatisch controleren of openstaande facturen zijn betaald:

1. Ga naar **ZZP** → **Debiteuren**
2. Klik op **Betalingen controleren**
3. Het systeem vergelijkt bankbetalingen met openstaande facturen
4. Gematchte facturen worden automatisch op "betaald" gezet

!!! info
De betalingscontrole matcht op basis van het Klant-ID in de betalingsreferentie en het bedrag. Zorg ervoor dat je klanten het Klant-ID vermelden bij hun betaling.

### 5. Betalingsherinnering versturen

Voor verlopen facturen kun je een herinnering sturen:

1. Ga naar **ZZP** → **Debiteuren**
2. Selecteer de verlopen factuur
3. Klik op **Herinnering versturen**
4. De herinnering wordt per e-mail verstuurd naar het contact

## Automatische verloopdetectie

Het systeem controleert dagelijks of facturen verlopen zijn:

- Facturen met de status "verstuurd" waarvan de vervaldatum is verstreken, worden automatisch op "verlopen" gezet
- Je ziet verlopen facturen direct in het debiteurenoverzicht

## Tips

!!! tip
Controleer je debiteurenoverzicht wekelijks. Hoe sneller je actie onderneemt bij verlopen facturen, hoe groter de kans dat je betaald wordt.

- Gebruik de verouderingsanalyse om prioriteiten te stellen bij het opvolgen van openstaande facturen
- Stuur een herinnering zodra een factuur verlopen is — wacht niet te lang
- Het Klant-ID op je facturen helpt bij automatische betalingsmatching
- Bekijk het crediteurenoverzicht om je eigen betalingsverplichtingen bij te houden

## Problemen oplossen

| Probleem                           | Oorzaak                                    | Oplossing                                                                              |
| ---------------------------------- | ------------------------------------------ | -------------------------------------------------------------------------------------- |
| Betaling niet automatisch gematcht | Klant-ID ontbreekt in betalingsreferentie  | Vraag je klant om het Klant-ID te vermelden bij de betaling                            |
| Factuur staat nog op "verstuurd"   | Betaling nog niet geïmporteerd             | Importeer eerst je bankafschriften via [Bankzaken](../banking/importing-statements.md) |
| Bedrag komt niet overeen           | Gedeeltelijke betaling of afwijkend bedrag | Controleer het betaalde bedrag — gedeeltelijke betalingen worden apart bijgehouden     |
| Herinnering niet ontvangen         | E-mail in spam of verkeerd adres           | Controleer het e-mailadres van het contact                                             |
