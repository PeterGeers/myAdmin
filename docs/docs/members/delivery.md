# Verzenden & bezorging

> Een analyseresultaat mailen, sjablonen gebruiken, een bezorging op een set bewaren, op een schema laten draaien en adresetiketten maken.

## Overzicht

Als je een pivotweergave hebt uitgevoerd op de [Analyse](analytics.md)-pagina, kun je het resultaat niet alleen exporteren naar CSV en mailen, maar ook meer ermee doen:

- een resultaat **mailen naar een extern adres** dat niet in de ledenlijst staat;
- een opgeslagen **sjabloon** kiezen om het bericht niet elke keer opnieuw te typen;
- op een **opgeslagen set** een vaste **bezorging** instellen, zodat uitvoeren of inplannen de verzending herhaalt zonder dat je alles opnieuw invult;
- een bezorging **nu draaien** (de verzending gebeurt op de achtergrond);
- een bezorging op een **schema** laten draaien (bijvoorbeeld maandelijks);
- rechtstreeks vanaf een resultaat **adresetiketten** maken.

!!! info
Mailen is pas beschikbaar als je tenant is vrijgegeven om te verzenden. Je Tenant Admin regelt dit eenmalig door een afzenderadres te verifiëren — zie [Afzender verifiëren](../tenant-admin/sender-verification.md). Zolang die vrijgave er niet is, zie je de mailacties niet.

!!! info
Je werkt altijd binnen je eigen **regiobereik**. Een bezorging kan alleen versturen wat je zelf binnen je bereik al zou mogen exporteren; er komt geen nieuw recht bij.

## Mailen naar een extern adres

Soms wil je een resultaat mailen naar iemand die níet in de ledenlijst staat — bijvoorbeeld een drukker, een bezorgdienst of een bestuurslid dat het overzicht alleen ter info krijgt.

In het mailvenster (de knop **Mailen** onder een resultaat) staat daarvoor het veld **Externe ontvangers**:

1. Voer het resultaat uit op de [Analyse](analytics.md)-pagina en klik op **Mailen**.
2. Typ in het veld **Externe ontvangers** een of meer e-mailadressen die niet in de dataset staan.
3. Stel onderwerp en bericht in (of kies een sjabloon — zie hieronder).
4. Kies eventueel een bijlage: het **CSV-bestand** en — als je tenant adresvelden heeft gekoppeld — **PDF-adresetiketten**.
5. Verstuur.

!!! info
De bijlagen werken precies zoals je gewend bent: CSV voor zowel tellingen als lijsten, en PDF-adresetiketten als je tenant de adresvelden heeft gekoppeld.

!!! tip
Je kunt externe ontvangers combineren met de gewone verzending; het externe adres krijgt dezelfde mail met dezelfde bijlagen.

## Sjablonen gebruiken

Een **sjabloon** is een opgeslagen, benoemd bericht (NL/EN) dat onderwerp en tekst alvast invult, zodat je niet elke keer opnieuw hoeft te typen.

### Een sjabloon kiezen in het mailvenster

1. Open het mailvenster via **Mailen**.
2. Kies een sjabloon in de keuzelijst **Sjabloon**.
3. Onderwerp en bericht worden ingevuld. Je kunt ze daarna gewoon **nog aanpassen** voordat je verstuurt.

!!! info
Een sjabloon mag **samenvoegvelden** bevatten (bijvoorbeeld de voornaam). Bij het verzenden worden die per ontvanger ingevuld met de gegevens uit de rij van dat lid.

### Sjablonen beheren

Je beheert je sjablonen in het sjabloonbeheer:

- **Aanmaken** — maak een nieuw sjabloon met een naam, onderwerp en tekst (NL en/of EN).
- **Bewerken** — pas een bestaand sjabloon aan.
- **Verwijderen** — verwijder een sjabloon dat je niet meer gebruikt.
- **Uploaden** — upload een kant-en-klaar sjabloon.

Een sjabloon kan ook een **logo** bevatten uit de huisstijl van je tenant.

### Verbeteren met AI

Bij het bewerken van een sjabloon kun je **Verbeteren met AI** gebruiken: je geeft een korte instructie (bijvoorbeeld "maak de toon vriendelijker" of "korter"), en de tekst wordt voor je herschreven. Je houdt zelf de controle — je ziet het resultaat en kunt het aanpassen of weggooien.

!!! info
De AI ziet **nooit ledengegevens**. Alleen de sjabloontekst (en de huisstijl) gaan naar de AI, nooit namen, adressen of andere gegevens van je leden. De samenvoegvelden worden pas ná de AI-stap, bij het verzenden, ingevuld.

!!! info
Er worden uitsluitend **gratis** AI-modellen gebruikt. Lukt het de AI niet, dan houd je gewoon je oorspronkelijke tekst — er gebeurt niets vervelends.

## Een bezorging op een opgeslagen set bewaren

Op een [opgeslagen set](analytics.md) kun je een **bezorging** instellen: de set onthoudt dan wat er met zijn resultaat moet gebeuren. Zo herhaal je het verzenden (handmatig of op schema) zonder alles opnieuw in te vullen.

Een bezorging kent twee **modi**:

| Modus           | Wat het doet                                                                                   |
| --------------- | ---------------------------------------------------------------------------------------------- |
| Per ontvanger   | Mail elk lid in het resultaat afzonderlijk, met **echte samenvoeging**: de samenvoegvelden van het sjabloon worden per lid ingevuld, zodat iedereen een persoonlijke mail krijgt. De adressen komen uit de gegevens en worden niet apart opgeslagen. |
| Naar vast adres | Verstuur het resultaat als **bijlage** naar een vaste lijst met adressen (vaak één).           |

Je stelt een bezorging in op de set:

1. Kies de modus (**Per ontvanger** of **Naar vast adres**).
2. **Per ontvanger:** kies het sjabloon waarmee elk lid wordt gemaild.
3. **Naar vast adres:** vul de vaste ontvangerslijst in en kies de bijlage.

!!! info
Als bijlage voor **Naar vast adres** gebruik je het **CSV-bestand**. (PDF-adresetiketten als bijlage per ontvanger zijn nog niet beschikbaar bij een server-side bezorging; voor etiketten gebruik je voorlopig de [actie Adresetiketten genereren](#adresetiketten-maken) of de PDF-bijlage in het mailvenster.)

!!! info
Oude sets zonder bezorging blijven gewoon werken. De bezorging staat los van de pivotdefinitie — je verandert niets aan hoe de set rekent.

## Een bezorging nu draaien

Heeft een set een bezorging, dan kun je hem direct laten lopen met **Nu draaien**:

- De verzending wordt **in de wachtrij** gezet en op de achtergrond verstuurd. Je venster blijft niet hangen op een lange verzending, en een grote run kan niet aflopen op een time-out.
- De verzending **respecteert de verzendlimieten**: er wordt op het juiste tempo verstuurd, zodat de limieten van de mailservice niet worden overschreden.

!!! info
Elke verzending wordt vastgelegd in het auditlogboek (alleen de metagegevens, geen berichtinhoud) — ook de runs die vanzelf op een schema lopen.

## Op een schema laten draaien

Je kunt een opgeslagen set met een bezorging op een **schema** laten draaien, zodat een terugkerende verzending vanzelf gebeurt.

1. Zorg dat de set een **bezorging** heeft (zie hierboven).
2. Koppel een schema aan de set, bijvoorbeeld **maandelijks** of **wekelijks**.
3. Zet het schema **aan** (of later weer **uit**).

!!! warning
Inplannen is voorbehouden aan gebruikers met **tenant-brede** ledentoegang: een **Tenant Admin**, of een gebruiker met wijzigrechten (`Members_CRUD`) én volledige (tenant-brede) toegang. Een gebruiker die tot één regio is beperkt, kan **niet** inplannen — een onbemande run mag nooit per ongeluk maar een deel van de tenant versturen.

!!! info
Een geplande run draait altijd **tenant-breed**. De tenant ligt vast in het schema en de verzending gebruikt dezelfde achtergrondverwerking als **Nu draaien**.

## Adresetiketten maken

Naast de PDF-bijlage in het mailvenster kun je adresetiketten ook **rechtstreeks vanaf een resultaat** maken, met de actie **Adresetiketten genereren** (naast CSV en Mailen onder een resultaat).

1. Voer het resultaat uit op de [Analyse](analytics.md)-pagina.
2. Klik op **Adresetiketten genereren**.
3. Kies het **Avery-formaat** en de opties (zoals sortering, lettergrootte, uitlijning, rand, land en de startpositie op het vel).
4. Download het PDF met de etiketten.

!!! tip
De actie is alleen beschikbaar als je tenant de **adresvelden heeft gekoppeld** (naam, straat, postcode, plaats, land) en je over het exportrecht beschikt. Ontbreekt die koppeling, dan werkt de CSV-export nog gewoon.

## Rechten

| Recht                               | Wat de gebruiker kan                                                       |
| ----------------------------------- | -------------------------------------------------------------------------- |
| `Members_Export` (of `Members_CRUD`) | Resultaten mailen (incl. externe ontvangers), CSV meesturen, adresetiketten genereren, een bezorging op een set instellen en **Nu draaien** |
| `Members_Export` of `Members_CRUD`  | Sjablonen aanmaken, bewerken, verwijderen, uploaden en verbeteren met AI   |
| `Members_Admin`, of `Members_CRUD` met volledige toegang | Een schema aan een set koppelen en aan-/uitzetten    |

!!! info
Een bezorging gebruikt geen nieuw recht: wat je kunt verzenden is begrensd door je exportrecht en je regiobereik — precies wat je zelf al zou mogen exporteren.

## Config-afhankelijkheden

- **Afzender verifiëren (vrijgave om te mailen)** — de mailacties verschijnen pas als je Tenant Admin een afzenderadres heeft geverifieerd en je tenant is vrijgegeven. Zie [Afzender verifiëren](../tenant-admin/sender-verification.md).
- **Adreskoppeling** — maakt de adresetiketten mogelijk (zowel de actie als de PDF-bijlage).

## Problemen oplossen

| Probleem                                   | Oorzaak                                               | Oplossing                                                        |
| ------------------------------------------ | ----------------------------------------------------- | ---------------------------------------------------------------- |
| Geen mailacties zichtbaar                  | Je tenant is nog niet vrijgegeven om te mailen        | Laat je Tenant Admin een afzenderadres verifiëren                |
| Geen veld **Externe ontvangers**           | Je hebt geen exportrecht                              | Vraag je Tenant Admin om `Members_Export`                        |
| Geen **PDF-adresetiketten** als bijlage    | Je tenant heeft geen adresvelden gekoppeld            | Laat de adreskoppeling toevoegen; CSV werkt ondertussen wel      |
| Geen actie **Adresetiketten genereren**    | Geen adreskoppeling, of geen exportrecht             | Laat de adreskoppeling toevoegen en vraag `Members_Export`       |
| Ik kan geen schema instellen               | Inplannen vereist tenant-brede toegang               | Vraag een Tenant Admin, of volledige toegang met wijzigrechten   |
| Een verbetering met AI gebeurde niet       | De AI-stap lukte niet                                | Je oorspronkelijke tekst blijft staan; probeer het later opnieuw |
| Een geplande verzending liep niet          | Het schema staat uit, of de set heeft geen bezorging  | Zet het schema aan en controleer dat de set een bezorging heeft  |
