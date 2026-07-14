# Rittenregistratie

> Zakelijke en privé kilometers bijhouden conform de eisen van de Belastingdienst.

## Overzicht

Met de rittenregistratie houd je een sluitende kilometeradministratie bij voor je voertuig(en). Dit is verplicht als je:

- **Privéauto voor zakelijk gebruik** hebt — je claimt €0,23/km aftrek voor zakelijke ritten
- **Zakelijke auto** hebt — je moet aantonen dat je minder dan 500 km/jaar privé rijdt om bijtelling te voorkomen

De Belastingdienst vereist per rit: datum, begin- en eindadres, begin- en eindstand, gereden afstand, ritdoel en categorie (zakelijk/privé/woon-werk). myAdmin registreert al deze gegevens en biedt export in het juiste formaat.

!!! info
De rittenregistratie is onderdeel van de ZZP-module. Vraag je Tenant Admin om de module in te schakelen als je deze niet ziet.

## Wat je nodig hebt

- Toegang tot de ZZP-module (`zzp_crud` rechten)
- Minimaal één geregistreerd voertuig (zie [Voertuigen](voertuigen.md))

## Ritten registreren

### Nieuwe rit toevoegen

1. Ga naar **ZZP** → **Rittenregistratie**
2. Klik op **Nieuwe rit**
3. Vul de velden in:

| Veld           | Verplicht   | Beschrijving                                                         |
| -------------- | ----------- | -------------------------------------------------------------------- |
| Datum          | Ja          | Datum van de rit                                                     |
| Starttijd      | Nee         | Tijdstip van vertrek                                                 |
| Eindtijd       | Nee         | Tijdstip van aankomst                                                |
| Startadres     | Ja          | Vertreklocatie                                                       |
| Eindadres      | Ja          | Bestemming                                                           |
| Begin km-stand | Ja          | Kilometerstand bij vertrek (wordt automatisch ingevuld)              |
| Eind km-stand  | Ja          | Kilometerstand bij aankomst                                          |
| Afstand        | Automatisch | Berekend als eind km-stand minus begin km-stand                      |
| Ritdoel        | Ja          | Reden van de rit (bijv. Klantbezoek, Vergadering, Materiaal ophalen) |
| Categorie      | Ja          | Zakelijk, Privé of Woon-werk                                         |
| Voertuig       | Ja          | Het voertuig waarmee je rijdt                                        |
| Klant/project  | Nee         | Koppeling aan een contact of project                                 |
| Opmerkingen    | Nee         | Vrije tekst voor toelichting                                         |

4. Klik op **Opslaan**

!!! tip
De begin km-stand wordt automatisch ingevuld met de eindstand van je vorige rit. Controleer of deze klopt met je dashboard.

### Route presets gebruiken

Als je regelmatig dezelfde route rijdt, biedt het systeem je veelgebruikte routes aan als snelkeuze:

1. Klik op **Nieuwe rit**
2. Onder **Favoriete routes** verschijnen je meestgebruikte trajecten
3. Klik op een route — het startadres, eindadres, categorie en ritdoel worden automatisch ingevuld
4. Vul de km-stand in en klik op **Opslaan**

!!! info
Het systeem leert automatisch je veelgebruikte routes. Na enkele weken gebruik verschijnen je top-routes als suggesties.

## Ritten bewerken

De Belastingdienst vereist dat wijzigingen in je rittenadministratie traceerbaar zijn. Daarom kun je een rit niet zomaar overschrijven.

1. Ga naar **ZZP** → **Rittenregistratie**
2. Klik op de rit die je wilt corrigeren
3. Klik op **Bewerken**
4. Pas de velden aan
5. Vul verplicht een **Correctiereden** in (bijv. "Km-stand verkeerd afgelezen")
6. Klik op **Opslaan**

Het systeem bewaart de oude waarden en de reden van wijziging in een onwijzigbare audittrail. Zo kun je altijd aantonen wat er is gewijzigd en waarom.

[Screenshot: correctiemodal met reden-veld]

## Ritten annuleren

Ritten kun je niet verwijderen — alleen annuleren (soft-delete). Dit is bewust, zodat je administratie compleet en controleerbaar blijft.

1. Open de rit die je wilt annuleren
2. Klik op **Annuleren**
3. Vul verplicht een **Annuleringsreden** in (bijv. "Dubbel ingevoerd")
4. Klik op **Bevestigen**

De rit wordt doorgestreept weergegeven in het overzicht en telt niet meer mee in je totalen.

!!! warning
Een geannuleerde rit kan niet worden hersteld. Maak indien nodig een nieuwe rit aan.

## Categorieën

Elke rit krijgt een categorie die bepaalt hoe de kilometers fiscaal worden verwerkt:

| Categorie     | Betekenis                                            | Fiscaal effect                                             |
| ------------- | ---------------------------------------------------- | ---------------------------------------------------------- |
| **Zakelijk**  | Rit voor je bedrijf (klantbezoek, vergadering, etc.) | Aftrekbaar bij privéauto; geen bijtelling bij bedrijfsauto |
| **Privé**     | Persoonlijke rit                                     | Telt mee voor de 500 km-grens bij bedrijfsauto             |
| **Woon-werk** | Rit van huis naar je vaste werkplek                  | Telt mee voor de 500 km-grens bij bedrijfsauto             |

!!! info
Woon-werkverkeer telt volgens de Belastingdienst als privégebruik. Deze kilometers tellen dus mee voor de bijtellinggrens van 500 km/jaar.

## Bijtelling (500 km-grens)

Als je een bedrijfsauto hebt, moet je aantonen dat je minder dan 500 km/jaar privé rijdt om bijtelling te voorkomen. Het systeem houdt dit automatisch bij.

### Dashboard widget

In het rittenoverszicht zie je een widget met:

- **Totaal km dit jaar** — al je gereden kilometers
- **Zakelijk** — kilometers voor je bedrijf
- **Privé + Woon-werk** — kilometers die meetellen voor de 500 km-grens
- **Resterend budget** — hoeveel privé-kilometers je nog kunt rijden

[Screenshot: bijtelling widget met km-teller]

!!! warning
Wanneer je de 400 km nadert (instelbaar), verschijnt een waarschuwing. Plan je ritten hierop.

### Wat als je over de 500 km komt?

Als je in een kalenderjaar meer dan 500 privékilometers rijdt met je bedrijfsauto, moet je bijtelling betalen over de cataloguswaarde van de auto. Het systeem waarschuwt je ruim van tevoren.

## Gap-fill (km-gaten)

Een km-gat ontstaat wanneer de begin km-stand van een nieuwe rit niet aansluit op de eindstand van je vorige rit. Dit kan gebeuren als je een rit vergeet te registreren.

### Hoe het werkt

1. Je voert een nieuwe rit in met begin km-stand 45.200
2. Je vorige rit eindigde op 45.050
3. Er is een gat van 150 km — het systeem waarschuwt je

### Wat je kunt doen

- **Gap-fill accepteren** — het systeem maakt automatisch een tussenrit aan (categorie: Privé, doel: "Niet geregistreerd")
- **Zelf invullen** — maak handmatig de ontbrekende rit(ten) aan
- **Later oplossen** — de rit wordt opgeslagen, het gat blijft zichtbaar als aandachtspunt

!!! info
Gap-fill ritten worden weergegeven met een oranje markering in het overzicht. Ze tellen als privékilometers totdat je ze corrigeert.

### Gap-fill ritten corrigeren

1. Klik op een oranje gemarkeerde gap-fill rit
2. Klik op **Bewerken**
3. Wijzig de categorie, het doel, of splits de rit op in meerdere ritten
4. Vul een correctiereden in en klik op **Opslaan**

## Filteren en sorteren

Het rittenoverszicht biedt uitgebreide filter- en sorteermogelijkheden:

| Filter      | Beschrijving                                   |
| ----------- | ---------------------------------------------- |
| Datumbereik | Bekijk ritten binnen een specifieke periode    |
| Categorie   | Alleen zakelijk, privé of woon-werk            |
| Voertuig    | Filter op een specifiek voertuig               |
| Klant       | Alleen ritten gekoppeld aan een bepaalde klant |
| Status      | Actief, geannuleerd, of gap-fill               |

### Sorteren

Klik op een kolomkop om te sorteren. Klik nogmaals om de sorteervolgorde om te draaien.

## Factureren

Zakelijke ritten die gekoppeld zijn aan een klant kun je direct factureren:

1. Ga naar **ZZP** → **Rittenregistratie**
2. Filter op de gewenste klant en periode
3. Selecteer de ritten die je wilt factureren (alleen niet-gefactureerde zakelijke ritten)
4. Klik op **Factuur aanmaken**
5. De geselecteerde ritten worden omgezet naar factuurregels (km × tarief)
6. Controleer de factuur en klik op **Opslaan**

!!! tip
Het kilometertarief wordt per klant/contract ingesteld. Stel dit in via het contactrecord van de klant.

Gefactureerde ritten worden gemarkeerd met een factuurbadge en kunnen niet opnieuw worden gefactureerd.

## Exporteren

Je kunt je rittenadministratie exporteren in verschillende formaten:

| Formaat   | Gebruik                                                   |
| --------- | --------------------------------------------------------- |
| **PDF**   | Officieel overzicht voor de Belastingdienst of accountant |
| **CSV**   | Verwerking in Excel of andere software                    |
| **Excel** | Kant-en-klaar spreadsheet met opmaak                      |

### Exporteren

1. Ga naar **ZZP** → **Rittenregistratie**
2. Stel de gewenste filters in (datumbereik, voertuig, categorie)
3. Klik op **Exporteren**
4. Kies het gewenste formaat
5. Het bestand wordt gedownload

!!! info
De PDF-export bevat alle door de Belastingdienst vereiste velden en is direct bruikbaar als bijlage bij je aangifte.

## Problemen oplossen

| Probleem                         | Oorzaak                                     | Oplossing                                                     |
| -------------------------------- | ------------------------------------------- | ------------------------------------------------------------- |
| Rittenregistratie niet zichtbaar | ZZP-module niet ingeschakeld                | Vraag je Tenant Admin om de module te activeren               |
| Geen voertuig beschikbaar        | Nog geen voertuig geregistreerd             | Registreer eerst een voertuig via [Voertuigen](voertuigen.md) |
| Km-stand wordt niet ingevuld     | Geen vorige rit voor dit voertuig           | Vul de begin km-stand handmatig in                            |
| Foutmelding bij opslaan          | Eind km-stand is lager dan begin km-stand   | Controleer je km-standen                                      |
| Gap-fill waarschuwing            | Begin km-stand sluit niet aan op vorige rit | Maak een tussenrit aan of accepteer de gap-fill               |
| Rit kan niet worden verwijderd   | Verwijderen is niet toegestaan              | Gebruik **Annuleren** in plaats van verwijderen               |
