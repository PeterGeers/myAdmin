# Sjabloonbeheer

> Upload, bewerk, download en verwijder rapportagesjablonen voor je organisatie.

## Overzicht

Met sjabloonbeheer bepaal je hoe facturen en rapportages eruitzien. Elk sjabloontype heeft een **standaardsjabloon** (ingebouwd in het systeem) en kan optioneel een **tenant-specifiek sjabloon** hebben dat je zelf uploadt.

Wanneer je geen eigen sjabloon hebt geüpload, gebruikt het systeem automatisch het standaardsjabloon.

!!! info
Sjabloonbeheer is beschikbaar op het **Sjablonen** tabblad in Tenant Beheer.

## Beschikbare sjabloontypen

| Sjabloontype          | Beschrijving                       |
| --------------------- | ---------------------------------- |
| STR Invoice (Dutch)   | Korte-termijn verhuur factuur (NL) |
| STR Invoice (English) | Korte-termijn verhuur factuur (EN) |
| BTW Aangifte          | BTW-aangifte rapport               |
| Aangifte IB           | Inkomstenbelasting rapport         |
| Toeristenbelasting    | Toeristenbelasting rapport         |
| Financial Report      | Algemeen financieel rapport        |
| ZZP Invoice           | ZZP-factuur voor freelancers       |

## Sjabloon uploaden

1. **Selecteer het sjabloontype** in het dropdown-menu
2. Het systeem toont of er al een actief sjabloon bestaat
3. **Kies een HTML-bestand** (max 5 MB)
4. Optioneel: configureer veldkoppelingen (JSON) via **Advanced: Field Mappings**
5. Klik op **Upload & Preview Template** om te valideren

!!! tip
Gebruik de knop **Format JSON** om je veldkoppelingen netjes op te maken.

## Standaardsjabloon downloaden

Wanneer er geen tenant-specifiek sjabloon bestaat voor het geselecteerde type, verschijnt er een gele melding met de knop **Download Default Template**.

1. **Selecteer het sjabloontype** in het dropdown-menu
2. Je ziet de melding: _"No active template found for this type"_
3. Klik op **Download Default Template**
4. Het standaardsjabloon wordt gedownload als `{type}_default.html`

!!! tip
Gebruik het standaardsjabloon als startpunt voor je eigen aanpassingen. Download het, bewerk het in een HTML-editor, en upload het vervolgens als tenant-specifiek sjabloon.

## Bestaand sjabloon beheren

Wanneer er een actief tenant-specifiek sjabloon bestaat, toont het systeem een blauw informatieblok met:

- **Versienummer** en goedkeuringsinformatie
- **Download** — Download het huidige sjabloon
- **Load & Modify** — Laad het sjabloon in het uploadformulier om het te bewerken en opnieuw te uploaden
- **Delete Template** — Verwijder het tenant-specifieke sjabloon

### Sjabloon downloaden

Klik op **Download** om het huidige actieve sjabloon te downloaden als HTML-bestand.

### Sjabloon bewerken

1. Klik op **Load & Modify**
2. Het huidige sjabloon wordt geladen in het uploadformulier
3. Bewerk het bestand in een externe HTML-editor
4. Upload het aangepaste bestand via **Upload & Preview Template**

### Sjabloon verwijderen

!!! warning
Na het verwijderen van een tenant-specifiek sjabloon valt het systeem terug op het standaardsjabloon.

1. Klik op **Delete Template** (rode knop)
2. Er verschijnt een bevestigingsdialoog
3. Klik op **Delete** om te bevestigen, of **Cancel** om te annuleren
4. Na succesvolle verwijdering toont het systeem de melding dat er geen actief sjabloon meer is

Het sjabloon wordt niet permanent verwijderd maar gedeactiveerd. De sjabloongeschiedenis blijft bewaard.

## Validatie en goedkeuring

Na het uploaden van een sjabloon doorloopt het de volgende stappen:

1. **Preview** — Bekijk hoe het sjabloon eruitziet
2. **Valideren** — Controleer op fouten in de HTML-structuur
3. **Goedkeuren** — Activeer het sjabloon voor gebruik

Bij validatiefouten kun je **AI Help** gebruiken voor automatische suggesties.

## Problemen oplossen

| Probleem                                      | Oorzaak                                      | Oplossing                                        |
| --------------------------------------------- | -------------------------------------------- | ------------------------------------------------ |
| "Tenant admin access required"                | Je hebt niet de Tenant_Admin rol             | Neem contact op met je SysAdmin                  |
| "Invalid template type"                       | Ongeldig sjabloontype opgegeven              | Selecteer een geldig type uit het dropdown-menu  |
| "No default template available"               | Geen standaardsjabloon beschikbaar           | Neem contact op met de beheerder                 |
| "No active tenant template found"             | Er is geen actief sjabloon om te verwijderen | Selecteer een type waarvoor een sjabloon bestaat |
| Bestand wordt geweigerd                       | Bestand is geen HTML of groter dan 5 MB      | Gebruik een .html of .htm bestand, max 5 MB      |
| Download Default Template knop niet zichtbaar | Er bestaat al een tenant-specifiek sjabloon  | Verwijder eerst het bestaande sjabloon           |
