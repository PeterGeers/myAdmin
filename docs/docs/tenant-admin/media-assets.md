# Media Asset Beheer

> Beheer van alle bestanden (afbeeldingen, PDF's, video's) die in S3 opslag zijn opgeslagen voor je organisatie.

## Overzicht

De Media Asset functie geeft je volledig inzicht en controle over alle bestanden die in de cloud (S3) zijn opgeslagen voor je tenant. Je kunt:

- Een overzicht zien van alle opgeslagen assets
- Een reconciliatie-scan uitvoeren om inconsistenties te detecteren
- Verweesde bestanden goedkeuren voor verwijdering
- Niet-geregistreerde S3 objecten importeren of verwijderen
- Bewaartermijnen per categorie instellen
- Duplicaten detecteren en samenvoegen

## Wat je nodig hebt

- `Tenant_Admin` rol
- Een geselecteerde tenant/administratie

## De tabs

Media Asset Beheer is bereikbaar via **Tenant Beheer** → **Media Assets** en bevat de volgende tabs:

| Tab                | Functie                                                      |
| ------------------ | ------------------------------------------------------------ |
| Dashboard          | Overzicht van aantallen, opslag per categorie                |
| Scan               | Reconciliatie-scan starten en resultaten bekijken            |
| Verwijdering       | Verwijderbare assets goedkeuren voor permanente verwijdering |
| Niet-geregistreerd | S3 objecten die niet in het register staan                   |
| Bewaartermijn      | Configuratie van bewaartermijnen per categorie               |
| Duplicaten         | Dubbele bestanden detecteren en samenvoegen                  |
| Opslag             | Opslagoverzicht per categorie en verweesde assets            |

## Stap voor stap

### Een scan uitvoeren

1. Ga naar **Media Assets** → **Scan**
2. Klik op **Start Scan**
3. De scan doorloopt automatisch de volgende fasen:
   - S3 buckets scannen
   - Vergelijken met het register
   - Referenties verifiëren
   - Verweesde assets overzetten
4. Na afloop zie je de resultaten:

| Resultaat            | Betekenis                                         |
| -------------------- | ------------------------------------------------- |
| Consistent           | Assets die correct geregistreerd zijn             |
| Niet-geregistreerd   | S3 objecten zonder registratie                    |
| Ontbrekend           | Registraties waarvoor het S3 bestand ontbreekt    |
| Verlopen referenties | Referenties naar entiteiten die niet meer bestaan |
| Nieuw verwijderbaar  | Assets die net de bewaartermijn zijn gepasseerd   |

### Niet-geregistreerde objecten importeren

1. Ga naar **Media Assets** → **Niet-geregistreerd**
2. Je ziet een lijst van S3 objecten die niet in het register staan
3. Selecteer de objecten die je wilt importeren (vinkjes)
4. Klik op **Importeren in register**
5. De objecten worden opgenomen in het asset register met status ACTIVE

!!! tip "Tip"
Na het importeren kun je een scan uitvoeren om te verifiëren dat alles consistent is.

### Niet-geregistreerde objecten verwijderen

1. Selecteer de objecten die je wilt verwijderen
2. Klik op **Verwijderen uit S3**
3. Bevestig in het dialoogvenster

!!! warning "Let op"
Verwijderen uit S3 is permanent en kan niet ongedaan worden gemaakt.

### Verwijderbare assets goedkeuren

1. Ga naar **Media Assets** → **Verwijdering**
2. Je ziet assets die verweesd zijn en waarvan de bewaartermijn is verlopen
3. Selecteer de assets die je wilt verwijderen
4. Klik op **Verwijdering goedkeuren**
5. Bevestig in het dialoogvenster

!!! warning "Compliance"
Bij factuur-gerelateerde assets wordt een extra waarschuwing getoond. Controleer of de wettelijke bewaartermijn (7 jaar) is verstreken.

### Bewaartermijnen aanpassen

1. Ga naar **Media Assets** → **Bewaartermijn**
2. Je ziet per categorie de huidige instelling en de bron (systeemstandaard of tenant aanpassing)
3. Pas de waarde aan in het invoerveld
4. Klik op **Wijzigingen opslaan**

Standaard bewaartermijnen:

| Categorie        | Standaard (dagen) | Toelichting                  |
| ---------------- | ----------------- | ---------------------------- |
| Facturen         | 2555 (7 jaar)     | Wettelijke bewaarplicht      |
| Branding         | 30                | Logo's en huisstijl          |
| Templates        | 90                | Factuur- en rapporttemplates |
| Landingspagina's | 7                 | Gepubliceerde webpagina's    |

### Duplicaten samenvoegen

1. Ga naar **Media Assets** → **Duplicaten**
2. Je ziet groepen van bestanden met dezelfde inhoud (hash)
3. Selecteer per groep welk bestand je wilt behouden (standaard het bestand met de meeste referenties)
4. Klik op **Samenvoegen**
5. Referenties worden overgezet naar het behouden bestand, duplicaten worden verwijderd

## Veelgestelde vragen

**Wat is een "verweesd" asset?**
Een asset dat niet meer wordt gerefereerd door een factuur, landingspagina, of ander onderdeel. Het staat wel in S3 maar wordt nergens meer gebruikt.

**Wordt er automatisch verwijderd?**
Nee. Het systeem detecteert en markeert assets als verwijderbaar, maar de tenant admin moet elke verwijdering expliciet goedkeuren.

**Wat als ik per ongeluk iets verwijder?**
Verwijdering uit S3 is permanent. Zorg ervoor dat je de juiste assets selecteert. Bij twijfel: importeer ze eerst in het register en koppel ze aan de juiste entiteit.

## Problemen oplossen

| Probleem                        | Oplossing                                                                  |
| ------------------------------- | -------------------------------------------------------------------------- |
| Scan toont geen resultaten      | Controleer of er assets in S3 staan voor je tenant                         |
| "Verbinding verbroken" bij scan | Herlaad de pagina en probeer opnieuw                                       |
| Import mislukt                  | Controleer of het bestand een ondersteund type is (afbeelding, PDF, video) |
| Bewaartermijn opslaan mislukt   | Waarde moet een positief getal zijn                                        |
