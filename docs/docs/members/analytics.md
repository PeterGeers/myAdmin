# Analyse

> Overzichten en draaitabellen over je leden maken, bekijken en exporteren.

## Overzicht

**Analyse** is een aparte pagina binnen Ledenadministratie, naast het Leden Overzicht. Je bereikt hem via het eigen menu-item **📊 Analyse** onder de sectie Leden. De pagina is **alleen-lezen**: je rekent en rapporteert hier over je leden, je wijzigt er geen ledengegevens.

Op de pagina:

- bovenaan een **filterbalk** (lidnummer, naam, e-mail, status, lidmaatschapstype en regio) waarmee je de dataset inkort;
- een live **teller** van het aantal leden dat na filteren overblijft;
- een paneel met analyses, waaronder de **pivotweergaven** (draaitabellen en lijsten) die hieronder worden beschreven.

Net als in het Leden Overzicht geldt je **regiobereik**: je werkt alleen met de leden die binnen jouw bereik vallen. De pagina haalt die set zelf op en kan hem alleen verder inperken met de filterbalk, nooit verbreden.

!!! info
Bij een heel grote ledenset toont de pagina een waarschuwing (resultaten kunnen onvolledig zijn) of, bij overschrijding van de limiet, een melding dat de set te groot is om te analyseren. Perk in dat geval eerst in met de filterbalk.

## De drie onderdelen

Het analysepaneel heeft drie onderdelen, waartussen je wisselt met de knoppen bovenaan het paneel. Er is er steeds één zichtbaar; **Overzicht** is het startonderdeel.

| Onderdeel      | Waarvoor                                                        |
| -------------- | --------------------------------------------------------------- |
| Overzicht      | Kerncijfers in één oogopslag (aantal, gemiddelden, verdeling per type) |
| Verdelingen    | Grafieken (viooldiagrammen) van leeftijd en jaren lidmaatschap  |
| Pivotweergaven | Draaitabellen en lijsten die je uitvoert, bouwt en exporteert   |

Alle drie werken op dezelfde dataset: je leden binnen je regiobereik, verder ingeperkt door de filterbalk. Wijzig je een filter, dan bewegen de cijfers en grafieken direct mee.

## Overzicht

Het onderdeel **Overzicht** toont kerncijfers over de gefilterde leden:

| Cijfer                    | Betekenis                                                 |
| ------------------------- | --------------------------------------------------------- |
| Aantal                    | Het aantal leden in de huidige (gefilterde) set           |
| Gemiddelde leeftijd       | De gemiddelde leeftijd                                     |
| Gemiddeld aantal jaren lid | Het gemiddelde aantal jaren lidmaatschap                  |

Onder de cijfers staat een **verdeling per lidmaatschapstype**: per type het aantal leden, aflopend gesorteerd.

!!! info
De gemiddelden worden berekend over de leden met een geldige waarde. Leden zonder (geldige) leeftijd of jaren-lid tellen niet mee als nul, maar worden overgeslagen. Zijn er zulke leden, dan staat er een regel als "N van M overgeslagen", zodat je het cijfer juist interpreteert.

!!! info
Leeftijd en jaren-lid zijn **berekende velden**. Heeft je tenant een van die velden niet, dan verdwijnt dat ene cijfer netjes (de rest blijft gewoon staan) — je ziet nooit een onzinwaarde.

## Verdelingen

Het onderdeel **Verdelingen** toont **viooldiagrammen** (violin plots): een grafiek die laat zien hoe een waarde over je leden is verdeeld. Er zijn er twee: één voor **leeftijd** en één voor **jaren lidmaatschap**.

### Groeperen

Standaard zie je per grafiek één verdeling over alle gefilterde leden. Met de keuzelijst **Groeperen op** splits je elke grafiek op in meerdere "violen", één per waarde van de gekozen dimensie:

- Regio
- Lidmaatschapstype
- Geslacht

!!! info
De keuzelijst toont alleen de dimensies die je tenant daadwerkelijk als veld heeft. Heeft je tenant bijvoorbeeld geen geslachtsveld, dan verschijnt die optie niet. Is er geen enkele dimensie beschikbaar, dan is er geen keuzelijst en zie je per metriek één verdeling.

!!! info
Een grafiek heeft een minimum aantal gegevenspunten nodig om zinvol te zijn. Zijn er te weinig leden met een geldige waarde, dan toont die grafiek de melding dat er te weinig gegevens zijn in plaats van een diagram. Dit wordt beoordeeld op het totaal; groeperen verbergt dus nooit een metriek die ongegroepeerd wél genoeg gegevens had.

## Pivotweergaven

Een **pivotweergave** (set) is een vooraf gedefinieerde telling of lijst over je leden. Er zijn twee soorten:

- **Telling** — groepeert leden en telt (of som/gemiddelde/min/max) per groep. Bijvoorbeeld "aantal leden per lidmaatschapstype".
- **Lijst** — toont één rij per lid met een vaste set kolommen. Bijvoorbeeld "leden per geboortemaand" met naam, verjaardag en adres.

### Een weergave uitvoeren

Er wordt **niets automatisch berekend**. Je kiest zelf wanneer een weergave draait:

1. Ga naar **Ledenadministratie** → **📊 Analyse**
2. Kies een set in de keuzelijst
3. Klik op **Uitvoeren**
4. Het resultaat verschijnt als tabel onder de knop

!!! info
De keuzelijst toont alleen de sets in **jouw voorkeurslijst** (zie hieronder). Wil je een andere set draaien, open dan **Alle sets** en voer hem daar uit of voeg hem toe aan je voorkeurslijst.

Bij twee presets verschijnt een extra keuzelijst naast **Uitvoeren**:

- **Jubilea** — kies een jubileumjaar; het resultaat beperkt zich tot leden die dat jubileum bereiken.
- **Nieuwe leden** — kies een jaar; het resultaat toont leden die in of na dat jaar lid zijn geworden.

## Ingebouwde weergaven (presets)

Er zijn standaardweergaven die altijd beschikbaar zijn, plus enkele die pas verschijnen als je tenant het bijbehorende veld heeft gekoppeld.

### Altijd beschikbaar

| Weergave               | Soort    | Toont                                                        |
| ---------------------- | -------- | ----------------------------------------------------------- |
| Lidmaatschapstypen     | Telling  | Aantal leden per lidmaatschapstype                          |
| Verjaardag / geboortemaand | Lijst | Leden per geboortemaand, met naam, verjaardag, regio en adres |
| Jubilea                | Lijst    | Jubileumleden op basis van het aantal jaren lidmaatschap    |
| Nieuwe leden           | Lijst    | Nieuwe leden op basis van hun inschrijfdatum                |

### Alleen zichtbaar na koppeling (rolgebonden)

Deze weergaven verschijnen pas als je tenant het bijbehorende veld heeft gekoppeld in de analyseconfiguratie:

| Weergave                   | Soort    | Vereist gekoppeld veld        |
| -------------------------- | -------- | ----------------------------- |
| Opzeggingen                | Lijst    | Opzeg-/einddatum              |
| Clubblad op papier (per land) | Telling | Clubblad-papier-markering     |
| Clubblad digitaal          | Lijst    | Clubblad-digitaal-markering   |
| Aanmeldbron                | Telling  | Aanmeldbron                   |

!!! info
Ontbreekt een rolgebonden weergave, dan is het bijbehorende veld niet gekoppeld in **Ledenconfiguratie → Analyse**. Een beheerder kan die koppeling toevoegen; daarna verschijnt de weergave vanzelf.

## Je voorkeurslijst en "Alle sets"

Er zijn twee overzichten van sets:

- **Je voorkeurslijst** — een persoonlijke, geordende shortlist. Dit is precies wat de keuzelijst bovenaan toont. De lijst is per gebruiker: jouw keuze geldt alleen voor jou.
- **Alle sets** — de volledige bibliotheek met alle presets én alle opgeslagen sets van je tenant, alfabetisch. Je opent hem met de knop **Alle sets** naast de keuzelijst.

In het venster **Alle sets** kun je per set:

- hem direct **uitvoeren**;
- hem **toevoegen aan** of **verwijderen uit** je voorkeurslijst, en de volgorde aanpassen;
- een opgeslagen (eigen) set **verwijderen** (presets kun je niet verwijderen).

## Een eigen set bouwen

Naast de presets maak je je eigen tellingen en lijsten met de **set-bouwer**. De acties staan boven het resultaat:

- **Nieuwe set** — bouw en bewaar een nieuwe set.
- **Opslaan als** — bewaar de gekozen set (of preset) als een nieuwe variant.
- **Bijwerken** — pas een opgeslagen set aan.

In de bouwer geef je op:

| Onderdeel        | Werking                                                                                   |
| ---------------- | ----------------------------------------------------------------------------------------- |
| Naam             | Verplicht; de naam waaronder de set verschijnt                                            |
| Groeperen op     | Nul of meer velden om op te groeperen. Géén groepering = een lijstset (één rij per lid)   |
| Lijstkolommen    | (Voor een lijstset) de kolommen die de lijst toont                                        |
| Maatstaven       | Nul of meer berekeningen: `COUNT`, `SUM`, `AVG`, `MIN`, `MAX` over een veld (of "alles tellen") |
| Filters          | Optionele vaste filters (veld = waarde) die bij de set horen en bij uitvoeren gelden      |

Opgeslagen sets zijn **gedeeld binnen je tenant**: iedereen met toegang ziet ze in de bibliotheek. Het resultaat volgt altijd je eigen regiobereik en de filterbalk.

!!! info
De sets zijn tenant-eigen en worden door de Ledenadministratie-module zelf opgeslagen. Het live filter van de Analyse-pagina wordt nooit mee opgeslagen in een set — een set bevat alleen zijn eigen definitie en eventuele vaste filters.

## Exporteren en mailen

Als je over het exportrecht beschikt, verschijnen onder een resultaat extra knoppen:

- **Exporteren naar CSV** — downloadt het resultaat als CSV-bestand (`member-analytics.csv`). Werkt zowel voor tellingen als voor lijsten.
- **Mailen** — opent een e-mailvenster (via de ingebouwde mailservice) om het resultaat te versturen. Je kunt het CSV-bestand meesturen, en — als je tenant adresvelden heeft gekoppeld — **PDF-adresetiketten** als bijlage toevoegen.

!!! info
Export en mail werken op de rijen die je op dat moment in de resultaattabel **ziet**. Filter of sorteer je het resultaat, dan exporteer/mail je exact die subset.

!!! tip
De PDF-adresetiketten zijn alleen beschikbaar als je tenant de adresvelden heeft gekoppeld (naam, straat, postcode, plaats, land). Ontbreekt die koppeling, dan werkt de CSV-export nog gewoon.

## Rechten

| Recht                               | Wat de gebruiker kan                                               |
| ----------------------------------- | ------------------------------------------------------------------ |
| `Members_Read` (of `Members_CRUD`)  | De Analyse-pagina openen, filteren en weergaven uitvoeren          |
| `Members_Export` (of `Members_CRUD`) | Resultaten exporteren naar CSV, mailen en PDF-etiketten genereren  |
| `Members_Export` of `Members_CRUD`  | Sets aanmaken, opslaan als, bijwerken en je voorkeurslijst beheren |

!!! info
Een opgeslagen set **verwijderen** uit de gedeelde bibliotheek is extra beperkt: dat mag alleen een **Tenant Admin**, of een gebruiker met volledige (tenant-brede) toegang én beheerrechten. Een regio-gebonden beheerder kan sets wel aanmaken en bijwerken, maar niet verwijderen.

## Config-afhankelijkheden

Wat je op de Analyse-pagina ziet, hangt mee af van de analyseconfiguratie van je tenant:

- **Jubileumregel** — bepaalt welke jaren als jubileum tellen (standaard elk veelvoud van 5 jaar). Dit stuurt de jubileumjaar-keuzelijst en de Jubilea-weergave.
- **Veldkoppelingen (rollen)** — bepalen welke rolgebonden weergaven beschikbaar zijn (zie boven) en op welk echt veld ze groeperen/lijsten.
- **Adreskoppeling** — maakt de PDF-adresetiketten mogelijk.

Deze koppelingen worden beheerd in de ledenconfiguratie van je tenant.

## Problemen oplossen

| Probleem                                 | Oorzaak                                            | Oplossing                                                     |
| ---------------------------------------- | -------------------------------------------------- | ------------------------------------------------------------- |
| Een gemiddelde (leeftijd/jaren) ontbreekt in Overzicht | Je tenant heeft dat berekende veld niet, of geen enkel lid heeft een geldige waarde | Dit is correct — er wordt geen onzinwaarde getoond            |
| Een verdeling toont "te weinig gegevens" | Te weinig leden met een geldige waarde            | Verruim de filterbalk; onder het minimum wordt geen diagram getoond |
| Geen keuzelijst **Groeperen op**         | Je tenant heeft geen van de dimensievelden (regio/type/geslacht) | Dit is normaal; zonder dimensievelden is er één verdeling per metriek |
| Keuzelijst toont weinig sets             | De keuzelijst toont alleen je voorkeurslijst       | Open **Alle sets** om de volledige bibliotheek te zien        |
| Een rolgebonden weergave ontbreekt       | Het bijbehorende veld is niet gekoppeld            | Laat de koppeling toevoegen in Ledenconfiguratie → Analyse    |
| Geen export-/mailknoppen                 | Je hebt geen exportrecht                           | Vraag je Tenant Admin om `Members_Export`                     |
| Geen PDF-etiketten in het mailvenster    | Je tenant heeft geen adresvelden gekoppeld         | Laat de adreskoppeling toevoegen; CSV werkt ondertussen wel   |
| "Dataset te groot"                       | De ledenset overschrijdt de analyselimiet          | Perk eerst in met de filterbalk en voer daarna uit            |
| Je kunt een opgeslagen set niet verwijderen | Verwijderen is voorbehouden aan beheerders      | Vraag een Tenant Admin om de set te verwijderen               |
