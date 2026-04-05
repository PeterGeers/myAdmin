# Links controleren en repareren

> Google Drive-links valideren en verbroken koppelingen herstellen.

## Overzicht

De validatiefunctie doorzoekt je transacties op Google Drive-links en controleert of elk bestand nog bereikbaar is. Verbroken links kun je handmatig bijwerken of het systeem repareert ze automatisch waar mogelijk.

## Wat je nodig hebt

- Transacties met Google Drive-links (Ref3-veld)
- Toegang tot de PDF Validatie module (`invoices_read` rechten)
- Een geselecteerde tenant/administratie

## Stap voor stap

### 1. Open PDF Validatie

Ga in myAdmin naar **PDF Validatie**.

### 2. Selecteer het jaar

Kies het jaar dat je wilt controleren uit de dropdown. Je kunt ook "All Years" kiezen, maar dit duurt langer.

### 3. Start de validatie

Klik op **Validate PDF URLs**. Het systeem:

1. Doorzoekt alle transacties met Google Drive-URLs voor het geselecteerde jaar en administratie
2. Controleert elke URL tegen Google Drive
3. Toont real-time voortgang via een voortgangsbalk
4. Rapporteert elke 10 records de tussenstand

Tijdens de validatie zie je:

- **Voortgangsbalk** — Percentage afgerond
- **Teller** — "Verwerkt X/Y records"
- **Tussenstand** — "X OK, Y problemen"

### 4. Bekijk de resultaten

Na afloop zie je een samenvatting:

| Statistiek         | Beschrijving                               |
| ------------------ | ------------------------------------------ |
| Totaal records     | Aantal transacties met Google Drive-links  |
| Geldige URLs       | Aantal werkende links (groen)              |
| Problemen gevonden | Aantal verbroken of onbekende links (rood) |

Daaronder verschijnt een tabel met alleen de problematische records:

| Kolom            | Beschrijving                                             |
| ---------------- | -------------------------------------------------------- |
| Status           | Type probleem (bestand niet gevonden, niet in map, etc.) |
| Transactienummer | Identificatie van de transactie                          |
| Datum            | Transactiedatum                                          |
| Omschrijving     | Transactieomschrijving                                   |
| Bedrag           | Transactiebedrag                                         |
| Referentie       | Referentienummer (leveranciersnaam)                      |
| URL (Ref3)       | De huidige Google Drive-link                             |
| Document (Ref4)  | Bestandsnaam                                             |
| Administratie    | Tenant                                                   |

### 5. Repareer verbroken links

Voor elk problematisch record kun je op **Update** klikken. Er verschijnt een formulier waar je kunt aanpassen:

| Veld                | Beschrijving                   |
| ------------------- | ------------------------------ |
| Referentienummer    | De leveranciersnaam/referentie |
| Document URL (Ref3) | De nieuwe Google Drive-link    |
| Documentnaam (Ref4) | De bestandsnaam                |

Na het invullen:

1. Het systeem valideert automatisch de nieuwe URL
2. Als de URL geldig is, worden alle transacties met dezelfde oude URL bijgewerkt
3. Je ziet een bevestiging van het aantal bijgewerkte records

!!! info
De update werkt op alle transacties met dezelfde originele Ref3-URL. Als een leverancier meerdere transacties heeft met dezelfde verbroken link, worden ze allemaal tegelijk gerepareerd.

## Automatische reparatie

Het systeem repareert sommige links automatisch:

- **Map-URLs** → Als het document in de map wordt gevonden, wordt de map-URL automatisch vervangen door de directe bestands-URL
- Deze records verschijnen als "Bijgewerkt" (blauw) in de resultaten

## Tips

!!! tip
Begin met het meest recente jaar en werk terug. Recente links zijn het belangrijkst voor je lopende administratie.

- Valideer per jaar om de wachttijd te beperken
- Gmail-links (geel) kun je alleen handmatig controleren door de link te openen
- Na het repareren kun je op **Refresh Results** klikken om opnieuw te valideren
- Verbroken links worden vaak veroorzaakt door het verplaatsen van bestanden in Google Drive

## Problemen oplossen

| Probleem                     | Oorzaak                                                           | Oplossing                                                                               |
| ---------------------------- | ----------------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| Geen records gevonden        | Geen transacties met Google Drive-links in het geselecteerde jaar | Selecteer een ander jaar of controleer of facturen zijn geüpload                        |
| Validatie duurt lang         | Veel records om te controleren                                    | Selecteer een specifiek jaar in plaats van "All Years"                                  |
| "No tenant selected"         | Geen administratie geselecteerd                                   | Selecteer een tenant in de navigatiebalk                                                |
| Update mislukt               | Ongeldige nieuwe URL                                              | Controleer of de nieuwe URL een geldige Google Drive-link is                            |
| Veel "Bestand niet gevonden" | Bestanden verwijderd uit Google Drive                             | Controleer de prullenbak in Google Drive — verwijderde bestanden kunnen worden hersteld |
