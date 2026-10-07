# Lidmaatschapstypen

> De lidmaatschapstypen (de "catalogus") die je tenant gebruikt voor leden.

## Overzicht

Elk lid krijgt een **lidmaatschapstype** (bijvoorbeeld *Gewoon lid*, *Erelid* of *Jeugdlid*). De beschikbare typen vormen samen de **lidmaatschapstypen-catalogus** van je tenant, ook wel **Lidmaatschap Beheer** genoemd. Deze catalogus is tenant-eigen: de typen zijn geen vaste, ingebouwde lijst maar worden per organisatie beheerd.

Waar je de catalogus tegenkomt:

- In het formulier **Nieuw lid** / **Bewerken** vul je de keuzelijst **Lidmaatschapstype** met de typen uit deze catalogus. Zie [Leden beheren](managing-members.md).
- In het Leden Overzicht kun je op **Lidmaatschapstype** filteren en sorteren.

## Actieve en gearchiveerde typen

Elk type is óf **actief** óf **gearchiveerd** (teruggetrokken):

| Status        | Betekenis                                                                 |
| ------------- | ------------------------------------------------------------------------- |
| Actief        | Het type is toewijsbaar: het verschijnt in de keuzelijst bij toevoegen/bewerken |
| Gearchiveerd  | Het type is teruggetrokken: het verschijnt niet meer in de keuzelijst, maar blijft bewaard voor bestaande leden en historie |

!!! info
Een type wordt nooit "hard" verwijderd. Terugtrekken is een **archiveren** (op niet-actief zetten): leden die al op dat type staan en de historie blijven kloppen. Zo voorkom je dat je een type weggooit waar nog leden aan hangen.

!!! tip
Wil je een type niet meer gebruiken voor nieuwe leden, maar wel behouden voor bestaande leden? Archiveer het dan in plaats van het aan te passen. Nieuwe aanmeldingen krijgen het type dan niet meer aangeboden, terwijl bestaande leden onveranderd blijven.

## De catalogus beheren

Het aanmaken, aanpassen en archiveren van lidmaatschapstypen is een **beheertaak**: het valt onder het recht `Members_CRUD` (de administratieve/beheerrechten binnen Ledenadministratie) en is voorbehouden aan beheerders. Het wijzigt de typevocabulaire voor de hele tenant, niet een los lid.

Per type worden onder andere een referentiecode (de waarde die bij een lid wordt opgeslagen) en een weergavenaam (NL/EN) vastgelegd.

!!! info
Het beheer van de catalogus is een administratieve functie. Beschik je niet over de beheerrechten (`Members_CRUD`), dan kun je de typen wel zien in de keuzelijsten en filters, maar ze niet aanmaken, aanpassen of archiveren. Vraag in dat geval je Tenant Admin.

## Problemen oplossen

| Probleem                                   | Oorzaak                                             | Oplossing                                                       |
| ------------------------------------------ | --------------------------------------------------- | --------------------------------------------------------------- |
| Een type ontbreekt in de keuzelijst        | Het type is gearchiveerd (niet-actief)              | Zet het type weer op actief (vereist `Members_CRUD`)            |
| Een gearchiveerd type kan niet weg         | Typen worden gearchiveerd, nooit hard verwijderd    | Dit is bewust — bestaande leden en historie blijven kloppen     |
| Je kunt typen niet beheren                 | Je hebt geen `Members_CRUD` recht                   | Vraag je Tenant Admin om de beheerrechten                       |
