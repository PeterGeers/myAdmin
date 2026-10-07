# Filteren & weergave

> De ledentabel doorzoeken, filteren, sorteren en zelf je kolommen kiezen.

## Overzicht

Het Leden Overzicht kan lange lijsten bevatten. Met het zoekveld, kolomfilters, sorteerbare kolomkoppen en de kolommenkiezer breng je snel de leden in beeld die je zoekt — en bepaal je zelf welke gegevens je ziet.

## Wat je nodig hebt

- Toegang tot de module Ledenadministratie (`Members_Read` of `Members_CRUD`)

## Zoeken over alle velden

Boven de tabel staat één zoekveld. Typ een naam, e-mailadres, lidnummer of een andere waarde en de lijst wordt direct ingekort tot de rijen die overeenkomen.

Het zoekveld kijkt naar **alle** velden van een lid — ook velden die niet als kolom in de tabel staan. Zo vind je een lid ook terug op een gegeven dat je niet als kolom hebt gekozen.

!!! tip
Wis het zoekveld met het kruisje om weer de volledige (binnen jouw bereik zichtbare) lijst te tonen.

## Kolommen filteren

Naast het zoekveld filter je ook per kolom. Elke zichtbare kolom heeft een eigen filter in de kolomkop. Veelgebruikte filters zijn:

| Filter            | Werking                                                        |
| ----------------- | -------------------------------------------------------------- |
| Regio             | Toont alleen leden van de gekozen regio/subgroep               |
| Status            | Toont alleen leden met de gekozen lidmaatschapsstatus          |
| Lidmaatschapstype | Toont alleen leden met het gekozen type                        |

### Stap voor stap

1. Ga naar **Ledenadministratie** → **Overzicht**
2. Typ in het filterveld in de kop van de kolom die je wilt filteren
3. De tabel toont direct alleen de rijen die aan het filter voldoen

Filters en zoekopdracht worden gecombineerd: een filter op regio *Noord* en status *Actief* toont alleen actieve leden in Noord.

!!! info
Filteren gebeurt binnen wat je al mag zien. Een gebruiker met bereik over alleen Noord ziet in het regiofilter alleen Noord — je kunt met een filter geen leden buiten je bereik in beeld brengen. Zie [Overzicht](index.md) voor uitleg over regiobereik.

## Sorteren

Elke sorteerbare kolomkop kun je aanklikken om de lijst op die kolom te ordenen:

1. Klik op de kolomkop (bijv. **Naam**) om oplopend te sorteren
2. Klik opnieuw om aflopend te sorteren

Sorteren houdt rekening met het type gegeven: getallen en datums worden op waarde geordend, niet alfabetisch.

## Zelf je kolommen kiezen

In plaats van een vaste "compact / volledig"-schakelaar bepaal je nu zelf welke kolommen de tabel toont, met de knop **Kolommen** in de werkbalk.

### Stap voor stap

1. Ga naar **Ledenadministratie** → **Overzicht**
2. Klik op **Kolommen**
3. Vink de velden aan die je als kolom wilt tonen en vink af wat je wilt verbergen
4. Sluit de kiezer — de tabel verschijnt direct met jouw kolommen

Je keuze wordt **per gebruiker onthouden**: de volgende keer dat je het overzicht opent, staan je kolommen er weer zoals je ze hebt ingesteld.

!!! info
De kolom **Lidnummer** staat altijd vooraan en kun je niet verbergen. Alle overige kolommen komen uit de veldconfiguratie van je tenant (vaste velden ⊕ extra velden ⊕ berekende velden). Ontbreekt er een veld dat je verwacht, vraag dan je Tenant Admin om de veldconfiguratie aan te passen.

## Weergaven (vooraf ingestelde kolommensets)

Heeft je tenant **weergaven** ingesteld, dan verschijnt links in de werkbalk een keuzelijst. Een weergave is een kant-en-klare combinatie van kolommen en een standaardsortering voor een bepaald doel (bijvoorbeeld "Contactgegevens" of "Financieel").

- Kies een weergave in de lijst om in één klik naar die kolommenset te schakelen.
- De keuzelijst verschijnt alleen als er minstens twee weergaven voor jou beschikbaar zijn.
- Welke weergaven je ziet, kan afhangen van je rol — je Tenant Admin bepaalt dit.

!!! info
Een weergave bepaalt alleen welke *kolommen* je ziet, nooit welke *rijen*. Je regiobereik en je zoekopdracht/filters blijven altijd bepalen welke leden in beeld komen.

## De statistiekenstrip

Boven de tabel tonen vier tellers live hoeveel leden je in beeld hebt: **Totaal** (alle leden binnen je bereik), **Gefilterd** (de nu getoonde rijen), **Actief** (leden met status Actief) en **Regio's** (aantal verschillende regio's). De tellers bewegen automatisch mee met je zoekopdracht, filters en gekozen weergave.

## Problemen oplossen

| Probleem                          | Oorzaak                                       | Oplossing                                                     |
| --------------------------------- | --------------------------------------------- | ------------------------------------------------------------- |
| Filter toont niet alle regio's    | Je bereik omvat maar één regio                | Dit is correct — je ziet alleen regio's binnen je bereik      |
| Verwachte kolom ontbreekt         | Kolom is niet aangevinkt of staat niet in de veldconfiguratie | Zet de kolom aan via **Kolommen**; ontbreekt het veld, vraag je Tenant Admin om de veldconfiguratie aan te passen |
| Lijst lijkt leeg                  | Er staat nog een zoekopdracht of filter aan   | Wis het zoekveld en de actieve filters om de volledige lijst weer te tonen |
| Geen **Weergave**-keuzelijst      | Je tenant heeft (voor jou) maar één weergave  | Dit is normaal; de keuzelijst verschijnt pas bij twee of meer weergaven |
