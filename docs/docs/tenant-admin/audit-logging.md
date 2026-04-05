# Audit logging

> Activiteiten bijhouden en compliance rapporten genereren.

## Overzicht

myAdmin houdt automatisch een auditlogboek bij van alle belangrijke acties. Als Tenant Admin kun je deze logs bekijken om te controleren wie wat heeft gedaan en wanneer.

## Wat wordt er gelogd?

| Actie                   | Wat er wordt vastgelegd                       |
| ----------------------- | --------------------------------------------- |
| Transacties opslaan     | Gebruiker, tijdstip, aantal records, tenant   |
| Duplicaatbeslissingen   | Keuze (doorgaan/annuleren), transactiedetails |
| Facturen uploaden       | Bestandsnaam, leverancier, gebruiker          |
| Boekingen importeren    | Platform, aantal boekingen, gebruiker         |
| Configuratiewijzigingen | Sleutel, oude/nieuwe waarde, gebruiker        |
| Gebruikersbeheer        | Aanmaken, rollen wijzigen, verwijderen        |
| Belastingrapporten      | Genereren, opslaan, exporteren                |

## Wat wordt er per logentry opgeslagen?

| Veld      | Beschrijving                                                 |
| --------- | ------------------------------------------------------------ |
| Tijdstip  | Datum en tijd van de actie                                   |
| Gebruiker | E-mailadres van de gebruiker                                 |
| Sessie-ID | Unieke sessie-identificatie                                  |
| Actie     | Type actie (bijv. "save_transactions", "duplicate_decision") |
| Details   | Specifieke informatie over de actie                          |
| Tenant    | Administratie waarbinnen de actie plaatsvond                 |

## Beschikbare rapporten

### Activiteitenrapport per gebruiker

Toont alle acties van een specifieke gebruiker over een bepaalde periode. Handig om te controleren wat een medewerker heeft gedaan.

### Compliance rapport

Een uitgebreid rapport met:

- Totaal aantal acties per type
- Acties per gebruiker
- Tijdlijn van activiteiten
- Ongebruikelijke patronen (veel acties in korte tijd)

### Transactie-audittrail

Voor een specifieke transactie kun je de volledige geschiedenis bekijken:

- Wanneer aangemaakt
- Door wie
- Welke wijzigingen zijn gemaakt
- Duplicaatbeslissingen

## Logbeheer

### Logs exporteren

Auditlogs kunnen worden geëxporteerd als CSV voor externe analyse of archivering.

### Oude logs opschonen

Logs ouder dan een ingestelde periode kunnen worden opgeschoond om de database compact te houden.

!!! warning
Bewaar auditlogs minimaal 7 jaar voor belastingdoeleinden. Schoon alleen logs op die buiten de wettelijke bewaartermijn vallen.

## Tips

!!! tip
Controleer het auditlogboek regelmatig, vooral na het importeren van grote hoeveelheden data. Zo kun je snel fouten opsporen.

- Alle duplicaatbeslissingen worden gelogd — handig als je later wilt controleren waarom een transactie wel of niet is geïmporteerd
- Het auditlogboek is alleen-lezen — logs kunnen niet worden gewijzigd of verwijderd via de interface

## Problemen oplossen

| Probleem               | Oorzaak                                            | Oplossing                                     |
| ---------------------- | -------------------------------------------------- | --------------------------------------------- |
| Geen logs zichtbaar    | Geen acties uitgevoerd in de geselecteerde periode | Pas de datumfilters aan                       |
| Logs laden langzaam    | Grote hoeveelheid logs                             | Beperk de periode of filter op gebruiker      |
| Gebruiker niet in logs | Gebruiker heeft geen acties uitgevoerd             | Normaal als de gebruiker alleen heeft gelezen |
