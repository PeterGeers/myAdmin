# Status & overgangen

> Eén lid of meerdere leden tegelijk naar een andere lidmaatschapsstatus brengen.

## Overzicht

Elk lid heeft een lidmaatschapsstatus (bijvoorbeeld *Aangevraagd*, *Actief* of *Beëindigd*). Een statuswijziging heet een **overgang**. Je voert een overgang uit voor één lid of voor meerdere leden tegelijk (bulk).

Welke statussen je als doel kunt kiezen, wordt bepaald door de ingestelde **levenscyclus** van je tenant. Je ziet alleen de overgangen die vanuit de huidige status zijn toegestaan.

## Wat je nodig hebt

- `Members_CRUD` recht

## Eén lid: status wijzigen

1. Ga naar **Ledenadministratie** → **Overzicht**
2. Open het lid en kies **Status wijzigen**
3. Kies een doelstatus uit de lijst met toegestane overgangen
4. Bevestig de wijziging

De nieuwe status is direct zichtbaar in de kolom **Status**.

!!! info
De lijst met doelstatussen is niet vast: hij komt uit de levenscyclus die voor je tenant is geconfigureerd. Vanuit een bepaalde status zijn alleen bepaalde vervolgstatussen mogelijk.

## Meerdere leden: bulkovergang

1. Ga naar **Ledenadministratie** → **Overzicht**
2. Selecteer de rijen van de leden die je wilt wijzigen (aankruisvakjes per rij)
3. Kies de bulkactie **Status wijzigen**
4. Kies de doelstatus
5. Bevestig de wijziging

De statuswijziging wordt toegepast op alle geselecteerde leden.

!!! tip
Combineer bulkovergangen met filters: filter bijvoorbeeld op status *Aangevraagd*, selecteer de leden die je wilt goedkeuren en zet ze in één keer op *Actief*. Zie [Filteren & weergave](filters-and-views.md).

!!! warning
Een bulkovergang raakt alle geselecteerde rijen. Controleer je selectie voordat je bevestigt.

## Problemen oplossen

| Probleem                             | Oorzaak                                          | Oplossing                                                        |
| ------------------------------------ | ------------------------------------------------ | ---------------------------------------------------------------- |
| Gewenste doelstatus ontbreekt        | De overgang is niet toegestaan vanuit de huidige status | Controleer de toegestane overgangen; de levenscyclus bepaalt dit |
| **Status wijzigen** is niet beschikbaar | Je hebt geen `Members_CRUD` recht             | Vraag je Tenant Admin om het juiste recht                        |
| Bulkactie ontbreekt                  | Er zijn geen rijen geselecteerd                  | Selecteer eerst één of meer rijen                                |
