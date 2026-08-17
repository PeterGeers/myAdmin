# Boekingen importeren

> Omzetbestanden van Airbnb, Booking.com, VRBO of directe boekingen uploaden en verwerken.

## Overzicht

Je importeert boekingen door een bestand te uploaden van je verhuurplatform. Het systeem herkent het formaat, berekent belastingen en kosten, en scheidt de boekingen in gerealiseerd en gepland.

## Wat je nodig hebt

- Een omzetbestand van je verhuurplatform
- Toegang tot de STR-module (`str_create` rechten)

## Stap voor stap

### 1. Open de STR-module

Ga in myAdmin naar **STR**. Je ziet het uploadformulier.

### 2. Selecteer het platform

Kies het juiste platform uit de dropdown:

| Platform        | Wanneer kiezen                                           |
| --------------- | -------------------------------------------------------- |
| **Airbnb**      | Voor Airbnb reserveringsexports (CSV)                    |
| **Booking.com** | Voor Booking.com boekingsoverzichten (Excel)             |
| **VRBO**        | Voor VRBO reserveringen + uitbetalingen (meerdere CSV's) |
| **Direct**      | Voor Guesty directe boekingen (CSV)                      |
| **Payout**      | Voor Booking.com maandelijkse afrekeningen (CSV)         |

### 3. Selecteer het bestand

Klik op **Bestand kiezen** en selecteer het gedownloade bestand.

**Per platform:**

**Airbnb:**

- Download je reserveringsoverzicht als CSV vanuit Airbnb
- Het bestand bevat kolommen als "Begindatum", "Einddatum", "Inkomsten", "Bevestigingscode"
- Geannuleerde boekingen zonder inkomsten worden automatisch overgeslagen

**Booking.com:**

- Download het boekingsoverzicht als Excel (.xlsx) vanuit het Extranet
- Bevat check-in/check-out datums, gastnamen en prijsinformatie

**VRBO:**

- Selecteer meerdere bestanden: Reserveringen CSV + Uitbetalingen CSV
- Het systeem detecteert automatisch welk bestand wat is op basis van de kolomkoppen

**Direct (Guesty):**

- Alleen CSV-bestanden worden geaccepteerd — Excel (.xls/.xlsx) wordt geweigerd
- Exporteer vanuit Guesty: klik op de link in het Import Links popup
- Pas de filter toe: "Checkin is between 2 months ago and 1 year into the future for Platform Manual"
- Het systeem verwerkt alleen boekingen met status "confirmed"
- Geannuleerde of niet-bevestigde boekingen worden overgeslagen
- Kanaalkosten worden berekend als 4% van het bruto bedrag (TOTAL PAYOUT)
- Bij herimport worden bestaande boekingen bijgewerkt in plaats van gedupliceerd (op basis van reserveringscode)
- Na opslaan wordt optioneel Stripe-verrijking uitgevoerd (e-mail, telefoon, land)

**Payout (Booking.com afrekening):**

- Bestandsnaam moet beginnen met `Payout_from_` en eindigen op `.csv`
- Dit bestand werkt bestaande boekingen bij met definitieve uitbetalingsbedragen

### 4. Verwerk het bestand

Klik op **Bestand verwerken**. Het systeem:

1. Leest het bestand en herkent het formaat
2. Berekent BTW, toeristenbelasting en kanaalkosten per boeking
3. Bepaalt of elke boeking gerealiseerd of gepland is (op basis van incheckdatum)
4. Controleert op duplicaten (reserveringscode + kanaal)
5. Toont een preview in drie tabbladen

!!! info "Direct (Guesty) — Duplicaatafhandeling"
Bij het platform **Direct** worden bestaande boekingen automatisch bijgewerkt wanneer dezelfde reserveringscode opnieuw wordt geïmporteerd. Dit betekent dat je veilig hetzelfde Guesty-export meerdere keren kunt importeren — gewijzigde velden worden bijgewerkt, geen duplicaten worden aangemaakt.

### 5. Bekijk de preview

Na verwerking zie je:

**Samenvattingskaart:**

- Totaal aantal boekingen
- Totaal aantal nachten
- Totale bruto omzet
- Verdeling per kanaal

**Drie tabbladen:**

| Tabblad          | Inhoud                                                       |
| ---------------- | ------------------------------------------------------------ |
| **Gerealiseerd** | Afgeronde boekingen (inchecken in het verleden)              |
| **Gepland**      | Toekomstige boekingen (inchecken in de toekomst)             |
| **Al geladen**   | Duplicaten die al in de database staan (worden overgeslagen) |

Elke boeking toont: kanaal, gast, accommodatie, datums, nachten, gasten, bruto/kosten/netto bedragen, status en reserveringscode.

### 6. Sla op

Klik op **Approve and Save** om de boekingen op te slaan:

- Gerealiseerde boekingen → `bnb` tabel (permanent archief)
- Geplande boekingen → `bnbplanned` tabel (wordt bijgewerkt bij elke import)
- Duplicaten worden automatisch overgeslagen

## Tips

!!! tip
Importeer Airbnb en Booking.com bestanden apart — elk platform heeft een eigen bestandsformaat.

- Bij VRBO kun je meerdere bestanden tegelijk selecteren
- Payout-imports werken bestaande boekingen bij met definitieve bedragen
- Het systeem detecteert automatisch het land van herkomst van gasten
- Geannuleerde boekingen met €0 inkomsten worden overgeslagen
- **Direct (Guesty):** Je kunt hetzelfde bestand meerdere keren veilig importeren — duplicaten worden bijgewerkt
- **Direct (Guesty):** Na opslaan haalt het systeem automatisch contactgegevens op uit Stripe (indien geconfigureerd)

## Problemen oplossen

| Probleem                                               | Oorzaak                                | Oplossing                                                                |
| ------------------------------------------------------ | -------------------------------------- | ------------------------------------------------------------------------ |
| "No file provided"                                     | Geen bestand geselecteerd              | Selecteer eerst een bestand                                              |
| "Unsupported platform"                                 | Verkeerd platform geselecteerd         | Controleer of je het juiste platform hebt gekozen                        |
| Geen boekingen gevonden                                | Leeg bestand of verkeerd formaat       | Controleer of het bestand boekingen bevat                                |
| Alle boekingen als "Al geladen"                        | Bestand al eerder geïmporteerd         | Dit is normaal — alleen nieuwe boekingen worden toegevoegd               |
| Payout-bestand geweigerd                               | Verkeerde bestandsnaam                 | Bestandsnaam moet beginnen met `Payout_from_`                            |
| "Only CSV files are supported for the direct platform" | Excel-bestand geselecteerd voor Direct | Exporteer vanuit Guesty als CSV, niet als Excel                          |
| "Missing required columns: ..."                        | Verkeerd CSV-formaat voor Direct       | Zorg dat het een Guesty-export is met alle 13 vereiste kolommen          |
| Alle rijen overgeslagen bij Direct                     | Geen boekingen met status "confirmed"  | Controleer de Guesty-filter: alleen bevestigde boekingen worden verwerkt |
