# Filteren & weergave

> De ledentabel filteren, sorteren en wisselen tussen compacte en volledige weergave.

## Overzicht

Het Leden Overzicht kan lange lijsten bevatten. Met kolomfilters, sorteerbare kolomkoppen en de weergaveschakelaar breng je snel de leden in beeld die je zoekt.

## Wat je nodig hebt

- Toegang tot de module Ledenadministratie (`Members_Read` of `Members_CRUD`)

## Kolommen filteren

Je filtert de lijst per kolom. De beschikbare filters zijn:

| Filter            | Werking                                                        |
| ----------------- | -------------------------------------------------------------- |
| Regio             | Toont alleen leden van de gekozen regio/subgroep               |
| Status            | Toont alleen leden met de gekozen lidmaatschapsstatus          |
| Lidmaatschapstype | Toont alleen leden met het gekozen type                        |

### Stap voor stap

1. Ga naar **Ledenadministratie** → **Overzicht**
2. Klik op het filtericoon in de kop van de kolom die je wilt filteren
3. Kies één of meer waarden
4. De tabel toont direct alleen de rijen die aan het filter voldoen

Filters kunnen worden gecombineerd: een filter op regio *Noord* en status *Actief* toont alleen actieve leden in Noord.

!!! tip
Wis een filter door het filtericoon opnieuw te openen en de selectie te verwijderen. Zo krijg je weer de volledige (binnen jouw bereik zichtbare) lijst.

!!! info
Filteren gebeurt binnen wat je al mag zien. Een gebruiker met bereik over alleen Noord ziet in het regiofilter alleen Noord — je kunt met een filter geen leden buiten je bereik in beeld brengen. Zie [Overzicht](index.md) voor uitleg over regiobereik.

## Sorteren

Elke sorteerbare kolomkop kun je aanklikken om de lijst op die kolom te ordenen:

1. Klik op de kolomkop (bijv. **Naam**) om oplopend te sorteren
2. Klik opnieuw om aflopend te sorteren

Zo sorteer je bijvoorbeeld op naam, status of lidmaatschapstype.

## Compacte en volledige weergave

Met de weergaveschakelaar boven de tabel wissel je tussen:

- **Compact** — alleen de kernkolommen (Naam, E-mail, Status, Lidmaatschapstype, Regio).
- **Volledig** — de kernkolommen plus de extra kolommen uit de veldconfiguratie van je tenant.

### Stap voor stap

1. Ga naar **Ledenadministratie** → **Overzicht**
2. Gebruik de schakelaar **Compact / Volledig** boven de tabel
3. In de volledige weergave verschijnen de extra velden als aanvullende kolommen

!!! info
De extra kolommen in de volledige weergave komen uit de veldconfiguratie die je Tenant Admin instelt. Ontbreekt er een kolom die je verwacht, vraag dan je Tenant Admin om de veldconfiguratie aan te passen.

## Problemen oplossen

| Probleem                          | Oorzaak                                       | Oplossing                                                     |
| --------------------------------- | --------------------------------------------- | ------------------------------------------------------------- |
| Filter toont niet alle regio's    | Je bereik omvat maar één regio                | Dit is correct — je ziet alleen regio's binnen je bereik      |
| Verwachte kolom ontbreekt         | Kolom staat niet in de veldconfiguratie       | Vraag je Tenant Admin om de veldconfiguratie aan te passen    |
| Lijst lijkt leeg                  | Er staat nog een filter aan                   | Wis de actieve filters om de volledige lijst weer te tonen    |
