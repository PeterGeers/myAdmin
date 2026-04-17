# Contacten beheren

> Klanten en leveranciers registreren, bewerken en beheren.

## Overzicht

In het contactenregister beheer je alle zakelijke contacten waarmee je factureert of inkoopt. Elk contact heeft een uniek Klant-ID dat wordt gebruikt voor betalingsmatching en facturatie. Contacten worden gedeeld met toekomstige modules, zodat je ze maar één keer hoeft aan te maken.

## Wat je nodig hebt

- Toegang tot de ZZP-module (`zzp_crud` rechten)
- De bedrijfsnaam en een uniek Klant-ID voor elk contact

## Stap voor stap

### 1. Contact aanmaken

1. Ga naar **ZZP** → **Contacten**
2. Klik op **Nieuw contact**
3. Vul de verplichte velden in:

| Veld           | Verplicht | Beschrijving                                                                    |
| -------------- | --------- | ------------------------------------------------------------------------------- |
| Klant-ID       | Ja        | Korte unieke code (bijv. "ACME", "KPN") — wordt gebruikt voor betalingsmatching |
| Bedrijfsnaam   | Ja        | Officiële naam van het bedrijf                                                  |
| Contactpersoon | Nee       | Naam van de contactpersoon                                                      |
| Adres          | Nee       | Straat, postcode, plaats, land                                                  |
| BTW-nummer     | Nee       | BTW-identificatienummer                                                         |
| KvK-nummer     | Nee       | Kamer van Koophandel registratienummer                                          |
| Telefoon       | Nee       | Telefoonnummer                                                                  |
| IBAN           | Nee       | Bankrekeningnummer                                                              |

4. Klik op **Opslaan**

!!! tip
Kies een kort, herkenbaar Klant-ID. Dit ID verschijnt op facturen en wordt gebruikt om bankbetalingen automatisch te matchen met openstaande facturen.

### 2. E-mailadressen toevoegen

Elk contact kan meerdere e-mailadressen hebben met een type-aanduiding:

| Type     | Gebruik                                                     |
| -------- | ----------------------------------------------------------- |
| Algemeen | Standaard e-mailadres                                       |
| Factuur  | Wordt gebruikt als ontvanger bij het versturen van facturen |
| Overig   | Extra e-mailadressen                                        |

1. Open het contact
2. Klik op **E-mail toevoegen**
3. Vul het e-mailadres in en kies het type
4. Klik op **Opslaan**

!!! info
Als er geen factuur-e-mailadres is ingesteld, wordt het algemene e-mailadres gebruikt bij het versturen van facturen.

### 3. Contact bewerken

1. Ga naar **ZZP** → **Contacten**
2. Klik op het contact dat je wilt bewerken
3. Pas de gewenste velden aan
4. Klik op **Opslaan**

### 4. Contact verwijderen

1. Ga naar **ZZP** → **Contacten**
2. Klik op het contact dat je wilt verwijderen
3. Klik op **Verwijderen**

!!! warning
Contacten die gekoppeld zijn aan bestaande facturen kunnen niet worden verwijderd. Het contact wordt in dat geval gedeactiveerd (soft delete) zodat je factuurhistorie intact blijft.

## Contacttypen

Elk contact heeft een type dat aangeeft wat voor relatie het is:

| Type        | Beschrijving                   |
| ----------- | ------------------------------ |
| Klant       | Je factureert aan dit contact  |
| Leverancier | Dit contact factureert aan jou |
| Beide       | Zowel klant als leverancier    |
| Overig      | Andere zakelijke relatie       |

## Tips

!!! tip
Gebruik het Klant-ID consistent op al je facturen. Wanneer je klant dit ID vermeldt bij de bankbetaling, kan het systeem de betaling automatisch matchen met de openstaande factuur.

- Vul het BTW-nummer in voor zakelijke klanten — dit is nodig voor correcte BTW-facturatie
- Het KvK-nummer is handig voor je eigen administratie maar niet verplicht
- Je kunt de beschikbare velden aanpassen via de tenant-instellingen (velden verbergen of verplicht maken)

## Problemen oplossen

| Probleem                           | Oorzaak                                       | Oplossing                                                  |
| ---------------------------------- | --------------------------------------------- | ---------------------------------------------------------- |
| "Klant-ID bestaat al"              | Klant-ID is niet uniek binnen je tenant       | Kies een ander Klant-ID                                    |
| Contact kan niet verwijderd worden | Contact is gekoppeld aan facturen             | Het contact wordt gedeactiveerd in plaats van verwijderd   |
| Velden ontbreken in het formulier  | Velden zijn verborgen via tenant-instellingen | Vraag je Tenant Admin om de veldconfiguratie aan te passen |
