# Aanmeldformulier (openbaar)

> Het openbare formulier waarmee een belangstellende zich zelf aanmeldt als lid, zonder in te loggen.

## Overzicht

Het **aanmeldformulier** is een openbare webpagina waarmee een belangstellende zich zelf kan aanmelden bij jouw vereniging — zonder account en zonder in te loggen. Na het verzenden landt de aanmelding als een lid met status *Aangevraagd* ("Aanmelding") en krijgen de beoordelaars binnen de tenant een e-mail.

Deze pagina beschrijft wat de **aanvrager** ziet en doet. Voor de kant van de medewerker die aanmeldingen beoordeelt, zie [Aanmeldingen beoordelen](reviewing-applications.md).

!!! info
Het formulier is per tenant: elke vereniging heeft een eigen adres (een slug, bijvoorbeeld `jouwvereniging`). De aanmelding komt altijd bij de juiste vereniging terecht — de aanvrager kan dat niet zelf kiezen of vervalsen.

## Wat de aanvrager ziet

### De velden

Het formulier is **niet vast**: het toont precies de velden die de Tenant Admin heeft aangemerkt als zichtbaar op het aanmeldformulier. De velden staan gegroepeerd in secties (bijvoorbeeld *Persoonsgegevens*, *Adres*, *Financieel*). Veelvoorkomende velden zijn:

- **E-mailadres** — altijd verplicht en gecontroleerd op geldigheid
- **Naam** en **geboortedatum** — altijd verplicht
- Eventueel een **lidmaatschapstype**, als de vereniging dat op het formulier heeft gezet (de aanvrager kiest dan uit een beperkte, publiek-veilige lijst)
- Adres-, regio- of andere velden, afhankelijk van de instelling

Sommige velden verschijnen pas als je een bepaalde keuze maakt (voorwaardelijke velden). Verplichte velden zijn gemarkeerd; verzenden lukt pas als die compleet en geldig zijn. Fouten worden per veld bij het betreffende veld getoond.

!!! info
Kies je een **incasso-/betaaloptie**, dan verschijnt een IBAN-veld dat op geldigheid (mod-97) wordt gecontroleerd.

### Taal

Bovenaan kies je de **taal** van het formulier (Nederlands of Engels). Standaard is Nederlands. De gekozen taal bepaalt ook de taal van de bevestigingsmail.

### Toestemming (consent)

Voor je kunt verzenden, moet je de **toestemmingsverklaring** (privacy/verwerking) van de vereniging aanvinken. Dit is verplicht — zonder akkoord wordt de aanmelding niet verzonden. De tekst is per vereniging en wordt met een versienummer vastgelegd bij je aanmelding, zodat precies bekend is waarmee je akkoord ging.

### Verzenden en de bevestigingsmail

Na **Verzenden** verschijnt een neutrale bevestiging op het scherm. Je ontvangt daarnaast een **bevestigingsmail** op het opgegeven e-mailadres, met een kopie van wat je hebt ingevuld, in de door jou gekozen taal.

!!! tip
Pas je je aanmelding aan en verstuur je binnen dezelfde sessie opnieuw, dan wordt je bestaande aanmelding **bijgewerkt** — er ontstaat geen dubbele aanmelding. Ook een dubbelklik op *Verzenden* levert één aanmelding op.

## "Aanmeldingen niet beschikbaar"

Soms opent het formulier niet en zie je de melding dat de vereniging op dit moment **geen aanmeldingen accepteert**. Dat betekent dat de vereniging nog geen geverifieerde afzender voor e-mail heeft ingesteld — zonder die afzender zou een aanvrager niet betrouwbaar bevestigd kunnen worden, dus staat het formulier bewust dicht.

Dit is een instelling aan de kant van de vereniging. De beheerder lost dit op door een afzender te verifiëren — zie [Afzender verifiëren](../tenant-admin/sender-verification.md). Daarna opent het formulier vanzelf.

## Problemen oplossen

| Probleem                              | Oorzaak                                                     | Oplossing                                                           |
| ------------------------------------- | ---------------------------------------------------------- | ------------------------------------------------------------------- |
| Formulier opent niet / "niet beschikbaar" | De vereniging heeft nog geen geverifieerde afzender         | De beheerder verifieert een afzender ([Afzender verifiëren](../tenant-admin/sender-verification.md)) |
| Pagina niet gevonden (404)            | De link/slug klopt niet of de vereniging bestaat niet       | Controleer de link die je van de vereniging kreeg                   |
| **Verzenden** lukt niet               | Een verplicht veld is leeg of ongeldig, of de toestemming is niet aangevinkt | Vul de gemarkeerde velden aan en vink de toestemming aan            |
| Geen bevestigingsmail ontvangen       | Verkeerd e-mailadres, of de mail staat in spam              | Controleer je spam-map; neem anders contact op met de vereniging    |
