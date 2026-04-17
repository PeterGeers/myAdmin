# Facturen aanmaken

> Conceptfacturen opstellen met regelitems, berekeningen en betalingsvoorwaarden.

## Overzicht

Je maakt facturen aan als concept (draft). Je selecteert een contact, voegt regelitems toe vanuit je productcatalogus of handmatig, en het systeem berekent automatisch de BTW en totalen. Pas als je tevreden bent, verstuur je de factuur.

## Wat je nodig hebt

- Toegang tot de ZZP-module (`zzp_crud` rechten)
- Minimaal één contact in je contactenregister
- Minimaal één product in je productcatalogus (of je voert regelitems handmatig in)

## Stap voor stap

### 1. Nieuwe factuur aanmaken

1. Ga naar **ZZP** → **Facturen**
2. Klik op **Nieuwe factuur**
3. Selecteer het **contact** waarvoor je factureert
4. Controleer de factuurdatum en betalingstermijn

| Veld             | Standaard               | Beschrijving                               |
| ---------------- | ----------------------- | ------------------------------------------ |
| Contact          | —                       | De klant waarvoor je factureert            |
| Factuurdatum     | Vandaag                 | Datum op de factuur                        |
| Betalingstermijn | 30 dagen (instelbaar)   | Aantal dagen tot de vervaldatum            |
| Vervaldatum      | Automatisch berekend    | Factuurdatum + betalingstermijn            |
| Valuta           | EUR (instelbaar)        | Valuta van de factuur                      |
| Omzetrekening    | Standaard omzetrekening | Grootboekrekening voor de omzet            |
| Opmerkingen      | —                       | Vrij tekstveld voor notities op de factuur |

### 2. Regelitems toevoegen

Klik op **Regel toevoegen** om een regelitem toe te voegen. Je hebt twee opties:

**Vanuit productcatalogus:**

1. Selecteer een product uit de dropdown
2. De naam, prijs en BTW-code worden automatisch ingevuld
3. Vul de hoeveelheid in
4. Pas eventueel de omschrijving of prijs aan

**Handmatig:**

1. Vul de omschrijving in
2. Vul de hoeveelheid en eenheidsprijs in
3. Selecteer de BTW-code

Elk regelitem bevat:

| Veld          | Beschrijving                                    |
| ------------- | ----------------------------------------------- |
| Product       | Optioneel — selecteer uit je catalogus          |
| Omschrijving  | Beschrijving van de geleverde dienst of product |
| Hoeveelheid   | Aantal eenheden                                 |
| Eenheidsprijs | Prijs per eenheid (excl. BTW)                   |
| BTW-code      | Hoog, laag of nul                               |
| BTW-bedrag    | Automatisch berekend                            |
| Regeltotaal   | Hoeveelheid × eenheidsprijs (excl. BTW)         |

### 3. Totalen controleren

Het systeem berekent automatisch:

| Berekening    | Formule                               |
| ------------- | ------------------------------------- |
| Subtotaal     | Som van alle regeltotalen (excl. BTW) |
| BTW-overzicht | BTW-bedragen gegroepeerd per BTW-code |
| Totaal BTW    | Som van alle BTW-bedragen             |
| Eindtotaal    | Subtotaal + totaal BTW                |

!!! info
BTW-bedragen worden berekend op basis van het tarief dat geldt op de factuurdatum. Het systeem haalt het juiste tarief automatisch op uit je administratie.

### 4. Factuur opslaan

Klik op **Opslaan** om de factuur als concept op te slaan. Je kunt het concept later bewerken voordat je het verstuurt.

## Laatste factuur kopiëren

Voor terugkerende klanten kun je snel een nieuwe factuur aanmaken op basis van de vorige:

1. Ga naar **ZZP** → **Facturen**
2. Klik op **Kopieer laatste factuur** bij het gewenste contact
3. De regelitems van de vorige factuur worden overgenomen
4. Pas de datum, hoeveelheden en eventuele wijzigingen aan
5. Klik op **Opslaan**

!!! tip
Gebruik "Kopieer laatste factuur" voor klanten die je maandelijks factureert. Je hoeft dan alleen de uren of hoeveelheden aan te passen.

## Meerdere valuta's

Je kunt facturen aanmaken in andere valuta's dan euro:

1. Selecteer de gewenste valuta bij het aanmaken van de factuur
2. Voer de bedragen in de gekozen valuta in
3. De wisselkoers wordt opgeslagen bij de factuur
4. Bij het boeken in FIN worden bedragen omgerekend naar euro

## Omzetrekening selecteren

Je kunt per factuur kiezen naar welke omzetrekening de omzet wordt geboekt:

1. Open de dropdown **Omzetrekening** bij het aanmaken van de factuur
2. Selecteer de gewenste rekening uit je rekeningschema
3. Alleen rekeningen die zijn gemarkeerd als "ZZP Factuur Grootboek" verschijnen in de lijst

!!! info
Als er geen omzetrekeningen zijn geconfigureerd, wordt de standaard omzetrekening uit je tenant-instellingen gebruikt. Vraag je Tenant Admin om de juiste rekeningen te markeren in het rekeningschema.

## Tips

!!! tip
Controleer altijd de totalen voordat je een factuur verstuurt. Eenmaal verstuurd kunnen de financiële gegevens niet meer worden gewijzigd.

- Je kunt meerdere regelitems per factuur toevoegen
- Conceptfacturen kunnen onbeperkt worden bewerkt
- Het factuurnummer wordt pas definitief toegewezen bij het versturen
- Gebruik de opmerkingen voor betalingsinstructies of projectreferenties

## Problemen oplossen

| Probleem                       | Oorzaak                                      | Oplossing                                                             |
| ------------------------------ | -------------------------------------------- | --------------------------------------------------------------------- |
| Geen contacten beschikbaar     | Nog geen contacten aangemaakt                | Maak eerst een contact aan via [Contacten](contacts.md)               |
| Geen producten in de dropdown  | Nog geen producten aangemaakt                | Maak eerst een product aan via [Producten](products.md)               |
| BTW wordt niet berekend        | BTW-tarieven niet geconfigureerd             | Vraag je Tenant Admin om de BTW-tarieven in te stellen                |
| Omzetrekening niet beschikbaar | Geen rekeningen gemarkeerd als ZZP-grootboek | Vraag je Tenant Admin om rekeningen te markeren in het rekeningschema |
