# PDF Validatie

> Controleer en repareer Google Drive-links in je transacties.

## Overzicht

De module PDF Validatie controleert of de Google Drive-links in je transacties nog werken. Elke factuur die je uploadt wordt opgeslagen in Google Drive, en de link wordt bewaard in het Ref3-veld van de transactie. Na verloop van tijd kunnen links verbroken raken door verplaatste of verwijderde bestanden.

## Wat kun je hier doen?

| Taak                                                       | Beschrijving                                                    |
| ---------------------------------------------------------- | --------------------------------------------------------------- |
| [Links controleren en repareren](checking-fixing-links.md) | Alle Google Drive-links valideren en verbroken links herstellen |

## Hoe werkt het?

Het systeem doorzoekt alle transacties met een Google Drive-URL in het Ref3-veld en controleert voor elk record:

| URL-type     | Controle                                  | Automatische actie                                    |
| ------------ | ----------------------------------------- | ----------------------------------------------------- |
| Bestands-URL | Bestaat het bestand nog in Google Drive?  | Geen — meldt alleen de status                         |
| Map-URL      | Staat het document in de map?             | Ja — vervangt de map-URL door de directe bestands-URL |
| Gmail-URL    | Kan niet automatisch gecontroleerd worden | Geen — markeert voor handmatige controle              |

## Mogelijke statussen

| Status                | Kleur    | Betekenis                                       |
| --------------------- | -------- | ----------------------------------------------- |
| OK                    | 🟢 Groen | Link werkt, bestand is bereikbaar               |
| Bijgewerkt            | 🔵 Blauw | Map-URL automatisch vervangen door bestands-URL |
| Bestand niet gevonden | 🔴 Rood  | Bestand bestaat niet meer in Google Drive       |
| Niet in map           | 🔴 Rood  | Document niet gevonden in de opgegeven map      |
| Gmail (handmatig)     | 🟡 Geel  | Gmail-link vereist handmatige controle          |
| Fout                  | 🔴 Rood  | Er is een fout opgetreden bij de validatie      |

## Wanneer gebruiken?

- Na een grote import van transacties
- Periodiek (maandelijks of per kwartaal) als onderhoudstaak
- Wanneer je merkt dat links in transacties niet meer werken
- Vóór het genereren van de Aangifte IB XLSX-export (die Google Drive-links bevat)

!!! tip
Voer de validatie uit per jaar en per administratie om het overzichtelijk te houden. Het controleren van alle jaren tegelijk kan lang duren.
