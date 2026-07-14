# Voertuigen

> Voertuigen registreren en beheren voor je rittenadministratie.

## Overzicht

Voordat je ritten kunt registreren, moet je minimaal één voertuig toevoegen. Per voertuig houdt het systeem de kilometerstand bij en berekent het de juiste fiscale totalen.

!!! info
Je kunt meerdere voertuigen registreren. Het systeem houdt per voertuig een aparte kilometeradministratie bij.

## Wat je nodig hebt

- Toegang tot de ZZP-module (`zzp_crud` rechten)
- Je kentekenbewijs bij de hand (voor kenteken, merk, type en bouwjaar)

## Voertuig toevoegen

1. Ga naar **ZZP** → **Rittenregistratie** → **Voertuigen**
2. Klik op **Voertuig toevoegen**
3. Vul de velden in:

| Veld                       | Verplicht | Beschrijving                                         |
| -------------------------- | --------- | ---------------------------------------------------- |
| Kenteken                   | Ja        | Nederlands kenteken (bijv. AB-123-CD)                |
| Merk                       | Ja        | Merk van het voertuig (bijv. Volkswagen)             |
| Type/Model                 | Ja        | Model van het voertuig (bijv. Golf)                  |
| Bouwjaar                   | Ja        | Bouwjaar van het voertuig                            |
| Chassisnummer (VIN)        | Nee       | Vehicle Identification Number (17 tekens)            |
| Voertuigtype               | Ja        | Privé voor zakelijk gebruik **of** Zakelijk voertuig |
| Eenheid                    | Ja        | Kilometers (standaard) of Mijlen                     |
| Begin km-stand             | Ja        | Huidige kilometerstand bij registratie               |
| Eigenaar/Leasemaatschappij | Nee       | Naam van de eigenaar of leasemaatschappij            |

4. Klik op **Opslaan**

[Screenshot: formulier voertuig toevoegen]

!!! tip
Neem de begin km-stand over van je dashboard op het moment dat je het voertuig registreert. Dit is het startpunt van je digitale administratie.

## Voertuigtypes

Het type voertuig bepaalt hoe het systeem je kilometers fiscaal verwerkt:

### Privé voor zakelijk gebruik

Je rijdt in je eigen (privé)auto en gebruikt deze ook voor zakelijke ritten.

| Kenmerk               | Toelichting                          |
| --------------------- | ------------------------------------ |
| Eigendom              | Privébezit of privélease             |
| Fiscale aftrek        | €0,23/km voor zakelijke ritten       |
| Wat wordt bijgehouden | Totaal zakelijke kilometers per jaar |
| Bijtelling            | Niet van toepassing                  |

### Zakelijk voertuig

De auto staat op naam van je bedrijf of is zakelijk geleast.

| Kenmerk               | Toelichting                                       |
| --------------------- | ------------------------------------------------- |
| Eigendom              | Zakelijk bezit of zakelijke lease                 |
| Fiscale aftrek        | Alle kosten zijn al zakelijk                      |
| Wat wordt bijgehouden | Privé + woon-werk kilometers (max 500 km/jaar)    |
| Bijtelling            | Vrijgesteld als je onder 500 km privé/jaar blijft |

!!! warning
Kies het juiste voertuigtype bij registratie. Dit bepaalt welke fiscale berekeningen het systeem uitvoert. Wijzigen van het type na registratie heeft gevolgen voor je historische rapportages.

## Voertuig bewerken

Je kunt de meeste gegevens van een voertuig achteraf wijzigen:

1. Ga naar **ZZP** → **Rittenregistratie** → **Voertuigen**
2. Klik op het voertuig dat je wilt bewerken
3. Klik op **Bewerken**
4. Pas de velden aan
5. Klik op **Opslaan**

### Wat kan worden gewijzigd

| Veld                       | Wijzigbaar | Toelichting                                      |
| -------------------------- | ---------- | ------------------------------------------------ |
| Kenteken                   | Ja         | Bij bijv. een personalisatie                     |
| Merk / Type / Bouwjaar     | Ja         | Correctie van invoerfouten                       |
| Chassisnummer              | Ja         | Kan later worden toegevoegd                      |
| Voertuigtype               | Beperkt    | Alleen als er nog geen ritten zijn geregistreerd |
| Eenheid (km/mijlen)        | Nee        | Kan niet worden gewijzigd na registratie         |
| Begin km-stand             | Nee        | Kan niet worden gewijzigd na de eerste rit       |
| Eigenaar/Leasemaatschappij | Ja         | Bijv. bij overstap naar ander leasecontract      |

!!! info
Het voertuigtype kan alleen worden gewijzigd als er nog geen ritten aan het voertuig zijn gekoppeld. Na de eerste rit is het type vergrendeld.

## Voertuig deactiveren

Als je een voertuig niet meer gebruikt (verkocht, einde lease, etc.), kun je het deactiveren. Verwijderen is niet mogelijk als er ritten aan zijn gekoppeld.

### Wanneer deactiveren?

- Je hebt het voertuig verkocht
- Je leasecontract is afgelopen
- Je wilt het voertuig niet meer gebruiken voor rittenregistratie

### Hoe deactiveren

1. Ga naar **ZZP** → **Rittenregistratie** → **Voertuigen**
2. Klik op het voertuig
3. Klik op **Deactiveren**
4. Bevestig de actie

### Wat gebeurt er na deactiveren?

| Aspect           | Effect                                                       |
| ---------------- | ------------------------------------------------------------ |
| Bestaande ritten | Blijven bewaard en zichtbaar in het overzicht                |
| Nieuwe ritten    | Kunnen niet meer worden aangemaakt voor dit voertuig         |
| Rapportages      | Historische data blijft beschikbaar voor export en belasting |
| Voertuiglijst    | Het voertuig wordt gedimd weergegeven met status "Inactief"  |
| Heractiveren     | Je kunt een gedeactiveerd voertuig later weer activeren      |

[Screenshot: voertuiglijst met actief en inactief voertuig]

!!! tip
Deactiveer een voertuig pas aan het einde van een belastingjaar, zodat je rapportages voor dat jaar compleet zijn.

## Meerdere voertuigen

Je kunt meerdere voertuigen tegelijk actief hebben. Bij het aanmaken van een rit kies je het voertuig waarmee je rijdt. Elk voertuig heeft zijn eigen:

- Kilometerstand-keten (geen gaten tussen ritten)
- Bijtelling-berekening (bij zakelijke voertuigen)
- Rapportages en exports

!!! info
Bij het aanmaken van een nieuwe rit wordt standaard je laatst gebruikte voertuig geselecteerd.

## Problemen oplossen

| Probleem                                | Oorzaak                                   | Oplossing                                              |
| --------------------------------------- | ----------------------------------------- | ------------------------------------------------------ |
| Voertuig kan niet worden verwijderd     | Er zijn ritten gekoppeld aan het voertuig | Gebruik **Deactiveren** in plaats van verwijderen      |
| Voertuigtype kan niet worden gewijzigd  | Er zijn al ritten geregistreerd           | Maak een nieuw voertuig aan met het juiste type        |
| Begin km-stand klopt niet               | Fout ingevoerd bij registratie            | Neem contact op met je Tenant Admin voor een correctie |
| Voertuig verschijnt niet bij nieuwe rit | Het voertuig is gedeactiveerd             | Heractiveer het voertuig via de voertuigenlijst        |
