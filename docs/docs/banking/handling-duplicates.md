# Duplicaten afhandelen

> Dubbele transacties herkennen en voorkomen dat ze twee keer worden opgeslagen.

## Overzicht

Bij het importeren en opslaan van bankafschriften controleert myAdmin automatisch op duplicaten. Dit voorkomt dat dezelfde transactie twee keer in je administratie terechtkomt.

## Wat je nodig hebt

- Geïmporteerde transacties klaar om op te slaan
- Toegang tot de module Bankzaken

## Hoe werkt duplicaatdetectie?

Het systeem gebruikt twee methoden om duplicaten te herkennen:

### Methode 1: Volgnummercontrole (bij opslaan)

Bij het opslaan controleert het systeem of het **volgnummer** (Ref2) al bestaat voor dezelfde **IBAN** (Ref1). Transacties met een bestaand volgnummer worden automatisch overgeslagen.

### Methode 2: Transactiecontrole (handmatig)

Je kunt ook handmatig op duplicaten controleren. Het systeem zoekt dan naar transacties met dezelfde:

- **Referentienummer** (exact)
- **Transactiedatum** (exact)
- **Transactiebedrag** (exact)

Alle drie moeten overeenkomen om als duplicaat te worden aangemerkt. De controle zoekt in de transacties van de afgelopen 2 jaar.

## Stap voor stap

### 1. Automatische controle bij opslaan

Wanneer je op **Opslaan** klikt:

1. Het systeem controleert elk volgnummer tegen de database
2. Transacties met bestaande volgnummers worden overgeslagen
3. Je ziet een samenvatting:
   - Aantal opgeslagen transacties
   - Totaal aantal transacties
   - Aantal overgeslagen duplicaten

### 2. Handmatige duplicaatcontrole

Als het systeem een mogelijke duplicaat vindt, verschijnt een waarschuwingsdialoog met:

- Aantal gevonden overeenkomsten
- Details van de bestaande transactie(s): ID, datum, omschrijving, bedrag, debet, credit en referenties

Je hebt twee opties:

| Actie         | Wat het doet                                            |
| ------------- | ------------------------------------------------------- |
| **Doorgaan**  | De transactie toch importeren (maakt een duplicaat aan) |
| **Annuleren** | De transactie overslaan (voorkomt duplicaat)            |

!!! warning
Als je kiest voor **Doorgaan**, wordt de transactie opgeslagen ondanks de duplicaatwaarschuwing. Doe dit alleen als je zeker weet dat het geen echte duplicaat is.

## Wanneer zijn duplicaten geen echte duplicaten?

Soms markeert het systeem transacties als duplicaat terwijl ze dat niet zijn:

- **Terugkerende betalingen** met hetzelfde bedrag op dezelfde dag (bijv. twee losse pintransacties)
- **Correctieboekingen** die op dezelfde dag plaatsvinden
- **Gesplitste betalingen** met identieke bedragen

In deze gevallen kun je veilig op **Doorgaan** klikken.

## Tips

!!! tip
Importeer bankafschriften altijd in chronologische volgorde en vermijd het opnieuw importeren van dezelfde periode. Dit minimaliseert het aantal duplicaatwaarschuwingen.

- Alle duplicaatbeslissingen worden vastgelegd in het auditlogboek
- Bij een databasefout tijdens de duplicaatcontrole gaat de import gewoon door met een waarschuwing
- Het Ref3-veld in de duplicaatweergave is klikbaar — als het een Google Drive-URL bevat, kun je de bijbehorende PDF openen

## Problemen oplossen

| Probleem                                         | Oorzaak                                             | Oplossing                                                                                         |
| ------------------------------------------------ | --------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| Alle transacties worden als duplicaat gemarkeerd | Je importeert een bestand dat al eerder is verwerkt | Controleer of je het juiste (nieuwe) bestand hebt geselecteerd                                    |
| Geen duplicaatcontrole                           | Volgnummers ontbreken in het bestand                | De automatische controle werkt op basis van volgnummers — zonder Ref2 wordt er niet gecontroleerd |
| Duplicaat gemist                                 | Transactie heeft ander referentienummer             | De controle is exact — kleine verschillen in referentienummers worden niet herkend                |
