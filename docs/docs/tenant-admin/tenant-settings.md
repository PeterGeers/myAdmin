# Instellingen

> Tenant configuratie, sjablonen en rekeningschema beheren.

## Overzicht

Als Tenant Admin kun je de instellingen van je organisatie beheren. Dit omvat configuratiesleutels, rapportagesjablonen en het rekeningschema (grootboekrekeningen).

## Configuratie

### Configuratie bekijken

1. Ga naar **Tenant Beheer** → **Instellingen**
2. Je ziet twee secties:
   - **Configuratie** — Niet-geheime instellingen met hun waarden
   - **Geheimen** — Geheime sleutels (alleen de sleutelnaam is zichtbaar, niet de waarde)

### Configuratie toevoegen of wijzigen

1. Klik op **Instelling toevoegen**
2. Vul in:

| Veld    | Beschrijving                                            |
| ------- | ------------------------------------------------------- |
| Sleutel | Naam van de instelling (bijv. `google_drive_folder_id`) |
| Waarde  | De waarde van de instelling                             |
| Geheim  | Vink aan als de waarde verborgen moet blijven           |

3. Klik op **Opslaan**

### Configuratie verwijderen

1. Klik op het verwijdericoon naast de instelling
2. Bevestig de actie

!!! warning
Geheime configuraties (zoals API-sleutels en wachtwoorden) tonen alleen de sleutelnaam. De waarde is versleuteld opgeslagen en niet zichtbaar in de interface.

## Sjablonen

Sjablonen bepalen hoe factuurverwerking en rapportages werken voor je organisatie. Je kunt sjablonen bekijken, aanpassen en goedkeuren.

### Sjabloon bekijken

1. Ga naar **Tenant Beheer** → **Sjablonen**
2. Selecteer het sjabloontype (bijv. `financial_report_xlsx`)
3. Je ziet het huidige sjabloon met de veldmappings

### Sjabloon aanpassen

1. Pas de velden aan in het bewerkingsformulier
2. Klik op **Preview** om het resultaat te bekijken
3. Klik op **Valideren** om te controleren op fouten
4. Klik op **Goedkeuren** om het sjabloon te activeren

Als er validatiefouten zijn, kun je **AI Help** gebruiken om suggesties te krijgen voor het oplossen van de fouten.

### Sjabloon afwijzen

Als een sjabloonwijziging niet correct is, klik je op **Afwijzen** om terug te keren naar de vorige versie.

## Rekeningschema

Het rekeningschema bevat alle grootboekrekeningen die beschikbaar zijn voor je administratie. Deze worden gebruikt bij het boeken van transacties.

!!! info
Rekeningen die al in transacties worden gebruikt, kunnen niet worden verwijderd. Het systeem controleert dit automatisch.

## Problemen oplossen

| Probleem                            | Oorzaak                                | Oplossing                                               |
| ----------------------------------- | -------------------------------------- | ------------------------------------------------------- |
| "Tenant admin access required"      | Je hebt niet de Tenant_Admin rol       | Neem contact op met je SysAdmin                         |
| Configuratie niet opgeslagen        | Verplichte velden ontbreken            | Controleer of sleutel en waarde zijn ingevuld           |
| Sjabloon validatie mislukt          | Ontbrekende verplichte velden          | Gebruik AI Help voor suggesties                         |
| Rekening kan niet verwijderd worden | Rekening wordt gebruikt in transacties | De rekening is in gebruik en kan niet worden verwijderd |
