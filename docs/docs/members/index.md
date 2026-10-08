# Ledenadministratie

> Leden bekijken, filteren, beheren en exporteren binnen je organisatie.

## Overzicht

Met de module Ledenadministratie beheer je de leden van je organisatie in één overzichtelijke tabel — het **Leden Overzicht**. Je ziet per lid de belangrijkste gegevens, zoekt en filtert de lijst, kiest zelf welke kolommen je toont, voegt leden toe of bewerkt ze, wijzigt de lidmaatschapsstatus en exporteert de leden naar CSV.

Wat je in de tabel ziet, hangt af van het **regiobereik** dat aan jouw account is toegewezen. Een gebruiker met bereik over één regio (bijvoorbeeld Noord) ziet uitsluitend de leden van die regio; een gebruiker met volledige toegang ziet alle leden. Dit filteren gebeurt door het systeem op basis van jouw toegewezen rol — niet door een instelling op deze pagina.

!!! info
De module Ledenadministratie moet door je SysAdmin zijn ingeschakeld voor je tenant. Het aanmaken van gebruikers en het toewijzen van rollen (inclusief het regiobereik) gebeurt in [Tenant Beheer](../tenant-admin/index.md) — zie [Gebruikersbeheer](../tenant-admin/user-management.md).

## Wat kun je hier doen?

| Taak                                              | Beschrijving                                                   |
| ------------------------------------------------- | -------------------------------------------------------------- |
| [Filteren & weergave](filters-and-views.md)       | Zoeken, filteren, sorteren en zelf je kolommen kiezen          |
| [Leden beheren](managing-members.md)              | Lid bekijken, toevoegen, bewerken en verwijderen               |
| [Status & overgangen](transitions.md)             | Één lid of meerdere leden tegelijk naar een andere status brengen |
| [Lidmaatschapstypen](membership-types.md)         | De lidmaatschapstypen van je tenant beheren (Lidmaatschap Beheer) |
| [Exporteren](export.md)                           | De leden exporteren naar CSV                                   |

## De ledentabel

Het Leden Overzicht toont je leden in een tabel. Standaard (voor wie nog geen eigen kolommen heeft gekozen) verschijnen deze kernkolommen:

| Kolom             | Beschrijving                                              |
| ----------------- | -------------------------------------------------------- |
| Lidnummer         | Het leesbare lidnummer (bijv. M00001) — staat altijd vooraan en kun je niet verbergen |
| Naam              | Volledige naam van het lid                               |
| E-mail            | E-mailadres van het lid                                  |
| Status            | Huidige lidmaatschapsstatus (bijv. Actief, Aangevraagd)  |
| Lidmaatschapstype | Het type lidmaatschap van het lid                        |

Daarnaast kun je zelf extra kolommen toevoegen (zoals **Regio** en andere velden uit de veldconfiguratie van je tenant) via de **Kolommen**-kiezer. Zie [Filteren & weergave](filters-and-views.md).

!!! tip
Klik op een rij om de gegevens van een lid in een alleen-lezen venster te bekijken. Zie [Leden beheren](managing-members.md).

## De werkbalk boven de tabel

Boven de tabel vind je de gereedschappen om de lijst naar je hand te zetten:

| Element            | Werking                                                                 |
| ------------------ | ----------------------------------------------------------------------- |
| **Zoeken**         | Eén zoekveld dat over *alle* velden van een lid zoekt — ook velden die niet als kolom zichtbaar zijn |
| **Kolommen**       | Kies zelf welke velden als kolom verschijnen; je keuze wordt per gebruiker onthouden |
| **Weergave**       | Een keuzelijst met vooraf ingestelde weergaven (kolommenset + sortering), als je tenant die heeft ingesteld |
| **Exporteren**     | Exporteer de leden naar CSV (alleen zichtbaar voor Tenant Admin / SysAdmin) |
| **Nieuw lid**      | Voeg een nieuw lid toe                                                   |

### Statistiekenstrip

Direct boven de tabel staat een strip met vier live-tellingen die meebewegen met je zoekopdracht en filters:

| Teller      | Betekenis                                                        |
| ----------- | ---------------------------------------------------------------- |
| Totaal      | Alle leden binnen jouw regiobereik                               |
| Gefilterd   | Het aantal rijen dat nu wordt getoond (na zoeken/filteren)       |
| Actief      | Aantal leden met status *Actief*                                 |
| Regio's     | Aantal verschillende regio's in de getoonde rijen                |

## Regiobereik: wat je ziet

Je regiobereik bepaalt welke leden je in de tabel ziet:

| Toegewezen bereik      | Wat je ziet                            |
| ---------------------- | -------------------------------------- |
| Eén regio (bijv. Noord) | Alleen de leden van die regio          |
| Volledige toegang      | Alle leden van alle regio's            |

!!! info
Het regiobereik wordt afgedwongen door het systeem, aan de serverzijde. Ook een export bevat alleen de rijen die binnen jouw bereik vallen — je kunt geen leden buiten je bereik zien of exporteren. Het bereik wijzig je niet hier; het wordt bepaald door de rol die je Tenant Admin toewijst in [Gebruikersbeheer](../tenant-admin/user-management.md).

## Rechten

| Recht            | Wat de gebruiker kan                              |
| ---------------- | ------------------------------------------------- |
| `Members_Read`   | Leden bekijken (tabel, zoeken, filteren, alleen-lezen venster) |
| `Members_CRUD`   | Leden aanmaken, bewerken, verwijderen, van status wijzigen en lidmaatschapstypen beheren |
| `Members_Export` | Leden exporteren naar CSV                         |

!!! info
De exportknop in het Leden Overzicht is bovendien alleen zichtbaar voor **Tenant Admin** en **SysAdmin**. Gewone gebruikers maken rijkere, gefilterde exports via de rapportage-/draaitabelweergaven. Zie [Exporteren](export.md).

!!! warning
Welke rechten beschikbaar zijn hangt af van de modules die de SysAdmin voor je tenant heeft ingeschakeld en de rollen die je Tenant Admin toewijst. Zonder een Members-rol is de Ledenadministratie niet zichtbaar.
