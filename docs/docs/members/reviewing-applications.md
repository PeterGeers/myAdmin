# Aanmeldingen beoordelen

> Nieuwe aanmeldingen bekijken, markeringen herkennen en goedkeuren tot lid.

## Overzicht

Wanneer iemand het openbare [aanmeldformulier](application-form.md) invult, landt de aanmelding als een lid met status *Aangevraagd* ("Aanmelding"). Er is **geen apart scherm** voor aanmeldingen: de "aanmeldingen-inbox" is gewoon het bekende **Leden Overzicht**, gefilterd op status *Aangevraagd*. Zo blijft alles in één vertrouwde tabel.

Beoordelaars met een alle-regio's (`Regio_All`) `Members_CRUD`-recht krijgen bij elke nieuwe aanmelding een e-mail met een deep-link naar het record. Die e-mail is **best-effort**: ook als de mail niet aankomt, staat de aanmelding gewoon in het overzicht. Het overzicht is de bron van waarheid, niet de e-mail.

## Wat je nodig hebt

- `Members_Read` om aanmeldingen te bekijken
- `Members_CRUD` om een aanmelding goed te keuren (statusovergang) of te verwijderen

## De aanmeldingen-inbox openen

1. Ga naar **Ledenadministratie** → **Overzicht**
2. Filter de kolom **Status** op *Aangevraagd* ("Aanmelding")
3. De tabel toont nu alleen de openstaande aanmeldingen

!!! tip
Sla dit filter op als weergave zodat je er met één klik bij kunt. Zie [Filteren & weergave](filters-and-views.md).

## Markeringen: `DUP` en `NO_NOTIFY`

Sommige aanmeldingen dragen een **markering** in het veld *Aanvullende informatie* (`overlay.additional_info`). Dit zijn trefwoorden waarop je kunt filteren:

- **`DUP`** — mogelijke dubbele aanmelding. Het systeem vond een bestaand lid met dezelfde **naam + geboortedatum**. De aanmelding is tóch aangemaakt (de markering blokkeert nooit); controleer of het om dezelfde persoon gaat voordat je goedkeurt.
- **`NO_NOTIFY`** — er kon niemand per e-mail worden geïnformeerd over deze aanmelding (geen alle-regio's `Members_CRUD` en geen `TenantAdmin` als terugval). De aanmelding staat er wel; behandel hem handmatig.

!!! info
Deze markeringen zijn alleen zichtbaar aan de medewerkerskant. De aanvrager ziet ze nooit en de bevestiging naar de aanvrager verandert er niet door — de `DUP`-markering is dus geen lek dat verraadt of iemand al lid is.

!!! tip
Filter op het trefwoord `DUP` om in één keer alle mogelijke duplicaten te bekijken, of op `NO_NOTIFY` om aanmeldingen te vinden die niemand per mail heeft gezien.

## Een aanmelding beoordelen

1. Klik op de rij van de aanmelding om de ingevulde gegevens te bekijken (alleen-lezen)
2. Controleer de gegevens en eventuele `DUP`-markering
3. Is de aanmelding akkoord, dan **keur je hem goed via een statusovergang**: breng het lid van *Aangevraagd* naar bijvoorbeeld *Actief*

Goedkeuren is dus geen aparte knop maar een **statuswijziging** — dezelfde overgang als elders in de ledenadministratie. Welke doelstatussen beschikbaar zijn, bepaalt de levenscyclus van je tenant. Zie [Status & overgangen](transitions.md).

!!! tip
Keur meerdere aanmeldingen in één keer goed: filter op status *Aangevraagd*, selecteer de rijen en gebruik de bulk-statusovergang naar *Actief*. Zie [Status & overgangen](transitions.md).

## Een aanmelding afwijzen of opruimen

Wil je een aanmelding niet goedkeuren, dan verwijder je het record via **Verwijderen** (zie [Leden beheren](managing-members.md)). Het verwijderen van openstaande aanmeldingen is een handmatige actie en is voorbehouden aan een alle-regio's `Members_CRUD`-gebruiker.

!!! warning
Verwijderen kan niet ongedaan worden gemaakt. Er is bewust geen automatische verwijdering van openstaande aanmeldingen, zodat een goedgekeurd lid nooit per ongeluk verdwijnt.

## Problemen oplossen

| Probleem                               | Oorzaak                                               | Oplossing                                                        |
| -------------------------------------- | ----------------------------------------------------- | ---------------------------------------------------------------- |
| Geen aanmeldingen zichtbaar            | Het statusfilter staat niet op *Aangevraagd*          | Filter de kolom **Status** op *Aangevraagd*                      |
| Geen e-mail gekregen bij een aanmelding | Je hebt geen alle-regio's `Members_CRUD`, of de aanmelding droeg `NO_NOTIFY` | Controleer het overzicht zelf; het overzicht is de bron van waarheid |
| Kan niet goedkeuren                    | Je hebt alleen `Members_Read`                         | Vraag je Tenant Admin om `Members_CRUD`                          |
| Dubbele aanmeldingen (`DUP`)           | Naam + geboortedatum komen overeen met bestaand lid   | Controleer of het dezelfde persoon is; keur er één goed, verwijder de rest |
