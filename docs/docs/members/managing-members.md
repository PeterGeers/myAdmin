# Leden beheren

> Een lid bekijken, toevoegen, bewerken en verwijderen.

## Overzicht

Vanuit het Leden Overzicht beheer je individuele leden: je bekijkt de gegevens van een lid, voegt een nieuw lid toe, past bestaande gegevens aan of verwijdert een lid.

## Wat je nodig hebt

- `Members_Read` om leden te bekijken
- `Members_CRUD` om leden toe te voegen, te bewerken of te verwijderen

## Een lid bekijken

1. Ga naar **Ledenadministratie** → **Overzicht**
2. Klik op de rij van het lid dat je wilt bekijken
3. Er opent een alleen-lezen venster met de volledige gegevens van het lid
4. Sluit het venster om terug te keren naar de tabel

!!! info
Het bekijkvenster is alleen-lezen. Om iets te wijzigen gebruik je **Bewerken** (zie hieronder).

## Een lid toevoegen

1. Ga naar **Ledenadministratie** → **Overzicht**
2. Klik rechtsboven op **Nieuw lid**
3. Vul het aanmeld-/toevoegformulier in:

| Veld              | Verplicht | Beschrijving                                                     |
| ----------------- | --------- | ---------------------------------------------------------------- |
| Naam              | Ja        | Volledige naam van het lid                                       |
| E-mail            | Ja        | E-mailadres van het lid                                          |
| Lidmaatschapstype | Ja        | Kies een type uit de keuzelijst                                  |
| Regio             | Ja        | De regio/subgroep waartoe het lid behoort                        |

4. Klik op **Opslaan**

!!! info
De keuzelijst **Lidmaatschapstype** toont alleen de **actieve** typen. Typen die zijn gedeactiveerd verschijnen niet, zodat je geen leden aanmaakt op een verlopen type.

## Een lid bewerken

1. Ga naar **Ledenadministratie** → **Overzicht**
2. Open het lid en klik op **Bewerken** (of gebruik de bewerkactie)
3. Pas de gewenste velden aan in het formulier
4. Klik op **Opslaan**

De wijzigingen zijn direct zichtbaar in de tabel.

!!! tip
Ook bij bewerken toont de keuzelijst **Lidmaatschapstype** alleen actieve typen.

## Een lid verwijderen

1. Ga naar **Ledenadministratie** → **Overzicht**
2. Open het lid en kies **Verwijderen**
3. Bevestig de actie in het bevestigingsvenster

!!! warning
Verwijderen kan niet ongedaan worden gemaakt. Controleer of je het juiste lid hebt geselecteerd voordat je bevestigt.

## Status wijzigen

Het bekijken en bewerken van gegevens verandert niet de lidmaatschapsstatus. Om een lid naar een andere status te brengen (bijvoorbeeld van *Aangevraagd* naar *Actief*) gebruik je de statusovergangen — zie [Status & overgangen](transitions.md).

## Onboarding en rollen

Het aanmaken van *gebruikers* (accounts die inloggen) en het toewijzen van rollen en regiobereik valt onder [Tenant Beheer](../tenant-admin/index.md). Zie [Gebruikersbeheer](../tenant-admin/user-management.md) — dit wordt hier niet gedupliceerd. Op deze pagina beheer je *leden* als administratieve records, niet de inlogaccounts.

## Problemen oplossen

| Probleem                            | Oorzaak                                   | Oplossing                                                    |
| ----------------------------------- | ----------------------------------------- | ------------------------------------------------------------ |
| Knop **Nieuw lid** ontbreekt        | Je hebt geen `Members_CRUD` recht         | Vraag je Tenant Admin om het juiste recht                    |
| Gewenst lidmaatschapstype ontbreekt | Het type is niet actief                   | Vraag je Tenant Admin om het type te activeren               |
| Lid kan niet bewerkt worden         | Alleen-lezen (`Members_Read`)             | Vraag je Tenant Admin om `Members_CRUD`                      |
