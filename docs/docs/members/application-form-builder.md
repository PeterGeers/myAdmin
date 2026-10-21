# Aanmeldformulier instellen

> Als Tenant Admin bepalen welke velden op het openbare aanmeldformulier verschijnen en hoe het formulier wordt gedeeld.

## Overzicht

Met de **formulierbouwer** stel je in hoe het openbare [aanmeldformulier](application-form.md) van je vereniging eruitziet: welke velden een aanvrager invult, welke verplicht zijn, hoe het formulier wordt gedeeld (adres en insluiten) en welke toestemmingsverklaring geldt. Je bouwt hier dus de kant die de aanvrager ziet; voor de medewerkerskant die aanmeldingen afhandelt, zie [Aanmeldingen beoordelen](reviewing-applications.md).

De bouwer is één werkblad met vier panelen. Je werkt in een **werkkopie** en legt je wijzigingen vast met **Opslaan** — losse velden worden niet apart verstuurd.

!!! info
De bouwer vind je in **Tenant Beheer** → **Ledenadministratie** → sub-tab **Aanmeldformulier**. De sub-tab verschijnt alleen als de module Ledenadministratie voor je tenant is ingeschakeld.

## Waar de bouwer leeft

1. Ga naar **Tenant Beheer** → **Ledenadministratie**.
2. Open de sub-tab **Aanmeldformulier** (naast *Veldconfiguratie*, *Lidmaatschapstypen* en *Mail*).
3. De bouwer laadt je huidige veldconfiguratie en je mailinstellingen in één werkkopie.

!!! info
De bouwer en de andere sub-tabs schrijven naar dezelfde onderliggende configuratie. Een veld zet je op één plek aan; de bouwer toont alleen de *aanmeld*-kant ervan.

## Velden kiezen (het veldenlijst-paneel)

Het eerste paneel toont alle beschikbare velden van je tenant, **gegroepeerd** per functionele sectie (bijvoorbeeld *Persoonsgegevens*, *Adres*, *Financieel*) en in een vaste volgorde.

- Per veld staat een schakelaar **Op het formulier**. Zet die aan om het veld aan het openbare aanmeldformulier toe te voegen.
- **Beheervelden** (bedoeld voor de ledenadministratie, niet voor een aanvrager) staan standaard **uit**, maar je kunt ze desgewenst aanzetten.
- **Berekende of niet-bewerkbare velden** kun je niet op het formulier zetten — die verschijnen niet als keuze.

!!! tip
Houd het formulier kort. Zet alleen de velden aan die je echt nodig hebt bij een aanmelding; de rest vul je later aan vanuit de ledenadministratie.

## Veldeigenschappen (per gekozen veld)

Zodra een veld **op het formulier** staat, kun je er per veld eigenschappen bij instellen. Deze gelden alleen voor het openbare formulier:

| Eigenschap             | Wat het doet                                                                                      |
| ---------------------- | ------------------------------------------------------------------------------------------------- |
| **Verplicht op formulier** | Maakt het veld verplicht voor de aanvrager. Een veld dat het platform al verplicht stelt, staat vast aan — je kunt dat niet versoepelen. |
| **Keuzebeperking (subset)** | Bij een keuzelijst-veld kies je welke opties de aanvrager te zien krijgt — een **deelverzameling** van de eigen opties van het veld. Laat je dit leeg, dan zijn alle opties zichtbaar. |
| **Formaat (controle)** | Koppelt een geldigheidscontrole aan het veld (bijvoorbeeld e-mail of IBAN). Je kiest uit de formaten die het platform kent; de keuzelijst blijft zo altijd gelijk aan wat de controle daadwerkelijk ondersteunt. |

!!! info
Zet je het **lidmaatschapstype** op het formulier, dan bied je het verplicht aan met een niet-lege keuzebeperking uit je eigen [lidmaatschapstypen-catalogus](membership-types.md). Een lege keuze op een zichtbaar-verplicht lidmaatschapstype wordt tegengehouden.

!!! tip
De eigenschappen verschijnen pas als het veld op het formulier staat. Staat een veld uit, dan zijn de eigenschappen niet van toepassing.

## Het formulier delen (het formulier-paneel)

Het formulier-paneel bepaalt hoe het openbare formulier bereikbaar is:

- **Openbaar adres (URL)** — het adres van het formulier wordt afgeleid van de **slug** van je landingspagina. Heb je nog geen slug, dan zie je "nog geen adres" met een verwijzing naar de [Landing Page editor](../landing-page/index.md), waar je de slug instelt. De slug beheer je dáár, niet in de bouwer.
- **Insluiten (embed)** — kies **standalone** (een losse pagina) of **iframe** (ingesloten op je eigen website). Bij iframe krijg je een kant-en-klaar fragment om te kopiëren.
- **Toegestane herkomsten (origins)** — bij insluiten geef je op welke websites het formulier in een iframe mogen tonen. Zonder opgegeven herkomsten blijft het formulier standalone (niemand mag het insluiten).
- **Toestemmingsverklaring (consent)** — de bilinguale (NL/EN) tekst waarmee een aanvrager akkoord moet gaan. Elke wijziging **verhoogt het versienummer**, zodat bij elke aanmelding precies wordt vastgelegd waarmee de aanvrager akkoord ging.

!!! info
De slug beheer je in de [Landing Page editor](../landing-page/index.md). De **afzender**, **Antwoord-naar (Reply-To)** en de **kopie-instelling (scope-copy)** stel je in op de sub-tab **Mail** — die worden niet in de bouwer ingevoerd; de bouwer verwijst er alleen naar.

## Gereedheid (het gereedheids-paneel)

Het gereedheids-paneel vat samen of het formulier klaar is om aanmeldingen te ontvangen. Het toont drie voorwaarden:

| Voorwaarde                 | Betekenis                                                                 |
| -------------------------- | ------------------------------------------------------------------------- |
| **Geverifieerde afzender** | Je tenant heeft een geverifieerde/gecertificeerde afzender voor mail      |
| **Slug (adres)**           | Er is een slug ingesteld, dus het formulier heeft een bereikbaar adres    |
| **Minstens één veld**      | Er staat ten minste één veld op het formulier                             |

Is een voorwaarde niet vervuld, dan geeft het paneel een neutrale aanwijzing (zonder mailinstellingen prijs te geven) en een verwijzing naar [Afzender verifiëren](../tenant-admin/sender-verification.md). Zolang er geen geverifieerde afzender is, toont het openbare formulier aan de aanvrager een nette "aanmeldingen niet beschikbaar"-melding in plaats van een half formulier.

!!! info
De gereedheid gebruikt hetzelfde "klaar om te verzenden"-signaal als het openbare formulier zelf. Pas als alle drie de voorwaarden kloppen, opent het formulier voor aanvragers.

## Live voorbeeld (het voorbeeld-paneel)

Het voorbeeld-paneel toont het **echte** openbare formulier in een ingesloten venster, precies zoals een aanvrager het ziet. Het voorbeeld weerspiegelt de **laatst opgeslagen** stand.

- Wijzig je iets, klik dan **Opslaan** en gebruik de knop **Voorbeeld bijwerken** om het venster opnieuw te laden.
- Omdat het voorbeeld het echte formulier is, is wat je hier ziet exact wat een aanvrager krijgt — geen aparte weergave die kan afwijken.

!!! tip
Werk in kleine stappen: zet een veld aan, sla op, ververs het voorbeeld en controleer het resultaat voordat je verder gaat.

## Rechten

| Recht          | Wat de gebruiker kan                                            |
| -------------- | --------------------------------------------------------------- |
| `Tenant_Admin` | Het aanmeldformulier instellen (velden, eigenschappen, delen, toestemming) |

!!! info
Het instellen van het aanmeldformulier is voorbehouden aan de **Tenant Admin**. De configuratie geldt voor de hele tenant, niet voor een los lid.

## Problemen oplossen

| Probleem                                       | Oorzaak                                                       | Oplossing                                                                 |
| ---------------------------------------------- | ------------------------------------------------------------- | ------------------------------------------------------------------------- |
| "Nog geen adres" bij het openbare adres        | Er is nog geen slug ingesteld                                 | Stel een slug in via de [Landing Page editor](../landing-page/index.md)   |
| Het formulier opent niet voor aanvragers       | Geen geverifieerde afzender (gereedheid niet vervuld)         | Verifieer een afzender via [Afzender verifiëren](../tenant-admin/sender-verification.md) |
| Verplicht-schakelaar staat vast aan            | Het platform stelt dit veld al verplicht                      | Dit is bewust — een platform-verplicht veld kun je niet versoepelen       |
| Keuzebeperking niet beschikbaar bij een veld   | Het veld is geen keuzelijst-veld                              | Een keuzebeperking geldt alleen voor velden met opties                    |
| Voorbeeld toont oude stand                     | Het voorbeeld weerspiegelt de laatst opgeslagen stand         | Klik **Opslaan** en daarna **Voorbeeld bijwerken**                        |
| Sub-tab Aanmeldformulier ontbreekt             | De module Ledenadministratie is niet ingeschakeld             | Vraag je SysAdmin de module in te schakelen voor je tenant                |
