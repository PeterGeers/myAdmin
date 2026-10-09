# Mailstatus

> Zien wat er met een verzending is gebeurd — in de wachtrij, verzonden of mislukt — met per run de details en de mislukte adressen.

## Overzicht

Een verzending uit de [Ledenadministratie](delivery.md) gebeurt op de **achtergrond**: je venster blijft niet hangen op een lange run. Op het scherm **Mailstatus** zie je daarna wat er met elke verzending is gebeurd. Zo is de achtergrondverwerking geen zwarte doos — je kunt terugkijken en, als er iets misging, zien welk adres en waarom.

!!! info
Mailstatus is een **pull-scherm**: je opent het zelf wanneer je wilt kijken. Je krijgt dus geen mail "je verzending is mislukt" — de uitkomst staat klaar op dit scherm.

## Het scherm openen

Je opent **Mailstatus** op de [Analyse](analytics.md)-pagina, naast de ingang voor je opgeslagen sets (**Alle sets**). Het scherm toont een **lijst met runs**: elke verzending die jij (of, als je Tenant Admin bent, iemand in je tenant) hebt gestart.

!!! info
De mailacties en dus ook de runs verschijnen pas als je tenant is vrijgegeven om te mailen. Zie [Afzender verifiëren](../tenant-admin/sender-verification.md).

## De lijst met runs

Per run zie je een samenvatting met de belangrijkste tellingen:

| Kolom          | Betekenis                                                                 |
| -------------- | ------------------------------------------------------------------------- |
| Omschrijving   | Waar de run bij hoort (bijvoorbeeld de naam van de set of het sjabloon)   |
| Wanneer        | Het tijdstip waarop de run is gestart                                     |
| Modus          | **Per ontvanger** of **Naar vast adres** (zie [Verzenden & bezorging](delivery.md)) |
| Aantal         | Het aantal ontvangers in de run                                           |
| Verzonden      | Hoeveel berichten door de mailservice zijn **geaccepteerd**               |
| Mislukt        | Hoeveel er niet verstuurd konden worden                                   |
| Status         | **In wachtrij** → **Bezig** → **Afgerond**                                |

Een afgeronde run leest bijvoorbeeld als: *Nieuwsbrief — 198 verzonden, 2 mislukt*.

!!! warning
**"Verzonden" betekent: geaccepteerd door de mailservice — niet "bezorgd in het postvak".** Dat de mailservice een bericht heeft aangenomen, is nog geen bewijs dat het in de inbox van de ontvanger is beland. Een bericht kan daarna alsnog **terugkomen** (een bounce) of als **klacht** worden gemarkeerd. Zulke late uitkomsten verschijnen pas ná de run bij de mislukte adressen (zie hieronder) en passen de tellingen aan.

## Inzoomen op een run

Klik op een run om de details te openen. De samenvatting telt de geslaagde ontvangers alleen; de **mislukte adressen** worden per stuk getoond:

| Veld      | Wat je ziet                                                              |
| --------- | ------------------------------------------------------------------------ |
| Adres     | Het e-mailadres dat niet (goed) is afgeleverd                            |
| Status    | **Mislukt**, **Teruggekomen** (bounce) of **Klacht**                     |
| Reden     | Waarom het misging (bijvoorbeeld een onbekend adres, een geweigerd bericht, of een te vol postvak) |

!!! info
Alleen **mislukte** adressen worden per stuk bewaard; de geslaagde ontvangers worden alleen geteld. Zo blijft het scherm overzichtelijk en bevat het geen onnodige ledengegevens.

!!! info
Een adres zonder bruikbaar e-mailadres (bij **Per ontvanger**) wordt **overgeslagen** en als mislukt gemeld — zo'n enkele ontbrekende rij laat de rest van de run gewoon doorlopen.

## Een run verwijderen

Je kunt een run uit de lijst **verwijderen** met de verwijderactie. Er volgt eerst een **bevestiging**, zodat je niet per ongeluk iets weggooit.

!!! info
Runs worden ook **vanzelf opgeruimd** na verloop van tijd (standaard na 90 dagen). Dat dekt een paar maandelijkse nieuwsbriefrondes om op terug te kijken; daarna verdwijnen de kleine metagegevens vanzelf. De handmatige verwijderactie is er voor als je er eerder vanaf wilt.

## Wie ziet welke runs

De runs zijn **per tenant** afgeschermd, en daarbinnen afhankelijk van je rol:

| Rol            | Wat je in Mailstatus ziet                                   |
| -------------- | ----------------------------------------------------------- |
| Gewone gebruiker | **Je eigen** verzendingen                                 |
| `Tenant_Admin` | **Alle** verzendingen van de tenant (overzicht)             |

!!! info
Het gaat om dezelfde gegevens, alleen anders afgeschermd: een gewone gebruiker ziet zijn eigen runs, een Tenant Admin ziet die van de hele tenant voor het overzicht. Niemand ziet ooit runs van een andere tenant.

## Config-afhankelijkheden

- **Afzender verifiëren (vrijgave om te mailen)** — zonder vrijgave zijn er geen mailacties en dus geen runs. Zie [Afzender verifiëren](../tenant-admin/sender-verification.md).

## Problemen oplossen

| Probleem                                   | Oorzaak                                               | Oplossing                                                        |
| ------------------------------------------ | ----------------------------------------------------- | ---------------------------------------------------------------- |
| Ik zie het scherm Mailstatus niet          | Je tenant is nog niet vrijgegeven om te mailen        | Laat je Tenant Admin een afzender verifiëren                     |
| Een run blijft op **In wachtrij** staan    | De achtergrondverwerking is nog bezig                 | Wacht even en ververs; grote runs worden op tempo verstuurd      |
| Een adres staat op **Mislukt**             | Onbekend/ongeldig adres, of het bericht is geweigerd  | Controleer het adres bij de reden; corrigeer het en verstuur opnieuw |
| Een adres kwam later alsnog **terug**      | De mailservice accepteerde het, maar het bouncete daarna | Dit is normaal: "verzonden" = geaccepteerd, niet bezorgd      |
| Ik zie alleen mijn eigen runs              | Je bent geen Tenant Admin                             | Alleen een Tenant Admin ziet alle runs van de tenant             |
