# Ledenadministratie

> Leden bekijken, filteren, beheren en exporteren binnen je organisatie.

## Overzicht

Met de module Ledenadministratie beheer je de leden van je organisatie in één overzichtelijke tabel — het **Leden Overzicht**. Je ziet per lid de belangrijkste gegevens, filtert en sorteert de lijst, voegt leden toe of bewerkt ze, wijzigt de lidmaatschapsstatus en exporteert de getoonde rijen naar CSV.

Wat je in de tabel ziet, hangt af van het **regiobereik** dat aan jouw account is toegewezen. Een gebruiker met bereik over één regio (bijvoorbeeld Noord) ziet uitsluitend de leden van die regio; een gebruiker met volledige toegang ziet alle leden. Dit filteren gebeurt door het systeem op basis van jouw toegewezen rol — niet door een instelling op deze pagina.

!!! info
De module Ledenadministratie moet door je SysAdmin zijn ingeschakeld voor je tenant. Het aanmaken van gebruikers en het toewijzen van rollen (inclusief het regiobereik) gebeurt in [Tenant Beheer](../tenant-admin/index.md) — zie [Gebruikersbeheer](../tenant-admin/user-management.md).

## Wat kun je hier doen?

| Taak                                              | Beschrijving                                                   |
| ------------------------------------------------- | -------------------------------------------------------------- |
| [Filteren & weergave](filters-and-views.md)       | Kolommen filteren, sorteren en wisselen tussen compact en volledig |
| [Leden beheren](managing-members.md)              | Lid bekijken, toevoegen, bewerken en verwijderen               |
| [Status & overgangen](transitions.md)             | Één lid of meerdere leden tegelijk naar een andere status brengen |
| [Exporteren](export.md)                           | De getoonde leden exporteren naar CSV                          |

## De ledentabel

Het Leden Overzicht toont je leden in een tabel met de volgende standaardkolommen:

| Kolom             | Beschrijving                                              |
| ----------------- | -------------------------------------------------------- |
| Naam              | Volledige naam van het lid                               |
| E-mail            | E-mailadres van het lid                                  |
| Status            | Huidige lidmaatschapsstatus (bijv. Actief, Aangevraagd)  |
| Lidmaatschapstype | Het type lidmaatschap van het lid                        |
| Regio             | De regio/subgroep waartoe het lid behoort (als badge)    |

Elke rij toont de regio als een **badge**, zodat je in één oogopslag ziet tot welke subgroep een lid behoort.

!!! tip
Klik op een rij om de gegevens van een lid in een alleen-lezen venster te bekijken. Zie [Leden beheren](managing-members.md).

## Compacte en volledige weergave

Boven de tabel staat een schakelaar tussen **compacte** en **volledige** weergave:

- **Compact** — toont alleen de kernkolommen (Naam, E-mail, Status, Lidmaatschapstype, Regio).
- **Volledig** — toont daarnaast de extra kolommen die via de veldconfiguratie van je tenant zijn ingesteld.

Welke extra velden in de volledige weergave verschijnen, bepaalt je Tenant Admin via de veldconfiguratie. Zie [Filteren & weergave](filters-and-views.md).

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
| `Members_Read`   | Leden bekijken (tabel, filters, alleen-lezen venster) |
| `Members_CRUD`   | Leden aanmaken, bewerken, verwijderen en van status wijzigen |
| `Members_Export` | Leden exporteren naar CSV                         |

!!! warning
Welke rechten beschikbaar zijn hangt af van de modules die de SysAdmin voor je tenant heeft ingeschakeld en de rollen die je Tenant Admin toewijst. Zonder een Members-rol is de Ledenadministratie niet zichtbaar.
