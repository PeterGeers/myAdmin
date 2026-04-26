# Requirements Document — ING Bank CSV Processor

## Introductie

Het systeem ondersteunt momenteel alleen Rabobank CSV-bestanden voor het importeren van banktransacties. Deze feature voegt ondersteuning toe voor het verwerken van ING Bank CSV-bestanden, zodat gebruikers met een ING-rekening hun transacties kunnen importeren via hetzelfde Banking Processor-systeem. De ING-processor wordt in een apart bestand geïmplementeerd en volgt dezelfde patronen als de bestaande Rabobank-processor, maar verwerkt het ING-specifieke CSV-formaat (puntkomma-gescheiden, dubbele aanhalingstekens, YYYYMMDD-datumformaat, komma als decimaalteken, apart "Af Bij"-veld voor debet/credit).

## Glossary

- **ING_CSV_Parser**: De backend Python-module die ING Bank CSV-bestanden inleest en omzet naar het standaard transactieformaat
- **Banking_Processor**: Het bestaande systeem (`banking_processor.py`) dat CSV-bestanden verwerkt en transacties beheert
- **Banking_Service**: De service-laag (`banking_service.py`) die de business logic voor bankverwerking afhandelt
- **Frontend_Processor**: De React-component (`BankingProcessor.tsx`) die CSV-bestanden client-side verwerkt en weergeeft
- **Mutaties_Tabel**: De MySQL-databasetabel `mutaties` waarin alle financiële transacties worden opgeslagen
- **Transaction_Record**: Het standaard dataformaat met velden: TransactionNumber, TransactionDate, TransactionDescription, TransactionAmount, Debet, Credit, ReferenceNumber, Ref1, Ref2, Ref3, Ref4, Administration
- **IBAN**: International Bank Account Number, gebruikt als primaire identificatie van bankrekeningen (Ref1-veld)
- **Af_Bij**: ING-specifiek veld dat aangeeft of een transactie een afschrijving ("Af") of bijschrijving ("Bij") is
- **Mutatiesoort**: ING-specifiek veld met een beschrijvende transactietype zoals "Betaalautomaat", "Overschrijving", "Incasso"
- **Code**: ING-specifiek veld met een korte transactiecode zoals BA, OV, GT, IC, DV
- **Pattern_Matcher**: Het bestaande systeem voor automatische toewijzing van grootboekrekeningen op basis van transactiepatronen

## Requirements

### Requirement 1: ING CSV-bestandsherkenning

**User Story:** Als gebruiker wil ik dat het systeem automatisch ING CSV-bestanden herkent, zodat ik niet handmatig het banktype hoef te selecteren.

#### Acceptance Criteria

1. WHEN een CSV-bestand wordt geladen, THE Frontend_Processor SHALL het bestand als ING-formaat herkennen wanneer de header-regel de kolom "Af Bij" bevat
2. WHEN een CSV-bestand wordt geladen, THE ING_CSV_Parser SHALL het bestand als ING-formaat herkennen wanneer de header-regel puntkomma-gescheiden kolommen bevat met de verwachte ING-kolomnamen ("Datum", "Naam / Omschrijving", "Rekening", "Tegenrekening", "Code", "Af Bij", "Bedrag (EUR)", "Mutatiesoort", "Mededelingen")
3. IF een CSV-bestand niet het verwachte ING-headerformaat heeft, THEN THE ING_CSV_Parser SHALL het bestand afwijzen met een beschrijvende foutmelding

### Requirement 2: ING CSV-parsing

**User Story:** Als gebruiker wil ik dat ING CSV-bestanden correct worden geparsed, zodat alle transactiegegevens nauwkeurig worden ingelezen.

#### Acceptance Criteria

1. THE ING_CSV_Parser SHALL CSV-bestanden lezen met puntkomma (`;`) als scheidingsteken
2. THE ING_CSV_Parser SHALL dubbele aanhalingstekens rond veldwaarden correct verwijderen
3. WHEN een datumveld in YYYYMMDD-formaat wordt gelezen, THE ING_CSV_Parser SHALL de datum omzetten naar YYYY-MM-DD formaat voor opslag in de Mutaties_Tabel
4. WHEN een bedragveld met komma als decimaalteken wordt gelezen (bijv. "45,67"), THE ING_CSV_Parser SHALL het bedrag omzetten naar een numerieke waarde met punt als decimaalteken (bijv. 45.67)
5. THE ING_CSV_Parser SHALL bestanden in ISO-8859-1 (Latin-1) encoding correct lezen
6. FOR ALL geldige ING CSV-regels, het parsen en vervolgens formatteren naar CSV en opnieuw parsen SHALL een equivalent Transaction_Record opleveren (round-trip eigenschap)

### Requirement 3: Debet/Credit-bepaling vanuit "Af Bij"-veld

**User Story:** Als gebruiker wil ik dat afschrijvingen en bijschrijvingen correct worden verwerkt, zodat mijn boekhouding klopt.

#### Acceptance Criteria

1. WHEN het "Af Bij"-veld de waarde "Af" bevat, THE ING_CSV_Parser SHALL de transactie als afschrijving verwerken door het Credit-veld te vullen met de bankrekening-code
2. WHEN het "Af Bij"-veld de waarde "Bij" bevat, THE ING_CSV_Parser SHALL de transactie als bijschrijving verwerken door het Debet-veld te vullen met de bankrekening-code
3. IF het "Af Bij"-veld een onverwachte waarde bevat (niet "Af" en niet "Bij"), THEN THE ING_CSV_Parser SHALL een waarschuwing loggen en de transactie overslaan
4. THE ING_CSV_Parser SHALL het TransactionAmount-veld altijd als positieve waarde opslaan, ongeacht de richting

### Requirement 4: Mapping naar standaard Transaction_Record

**User Story:** Als gebruiker wil ik dat ING-transacties in hetzelfde formaat worden opgeslagen als Rabobank-transacties, zodat alle bestaande functionaliteit (patronen, filters, overzichten) werkt.

#### Acceptance Criteria

1. THE ING_CSV_Parser SHALL het "Rekening"-veld (IBAN) mappen naar het Ref1-veld van het Transaction_Record
2. THE ING_CSV_Parser SHALL een samengestelde unieke sleutel opbouwen in het Ref2-veld, bestaande uit "Naam / Omschrijving", "Mededelingen" en "Bedrag (EUR)" gescheiden door underscores (vergelijkbaar met de Revolut-aanpak), zodat duplicaatdetectie betrouwbaar werkt ondanks het ontbreken van een volgnummer in het ING CSV-formaat
3. THE ING_CSV_Parser SHALL het "Tegenrekening"-veld mappen naar het Ref3-veld van het Transaction_Record
4. THE ING_CSV_Parser SHALL een beschrijving samenstellen uit "Naam / Omschrijving" en "Mededelingen" en deze mappen naar het TransactionDescription-veld
5. THE ING_CSV_Parser SHALL het TransactionNumber-veld vullen met "ING" gevolgd door de huidige datum in YYYY-MM-DD formaat
6. THE ING_CSV_Parser SHALL het Ref4-veld vullen met de bestandsnaam van het bronbestand
7. THE ING_CSV_Parser SHALL het Administration-veld bepalen op basis van de IBAN via de bank_accounts lookup-tabel

### Requirement 5: Integratie met bestaand Banking Processor-systeem

**User Story:** Als gebruiker wil ik ING-bestanden op dezelfde manier verwerken als Rabobank-bestanden, zodat ik één workflow heb voor alle bankimports.

#### Acceptance Criteria

1. THE Banking_Processor SHALL ING CSV-bestanden kunnen verwerken via de bestaande `process_csv_files`-methode
2. THE Banking_Service SHALL IBAN-validatie uitvoeren op ING-transacties om te controleren of de rekening bij de huidige tenant hoort
3. WHEN ING-transacties zijn verwerkt, THE Pattern_Matcher SHALL automatische grootboekrekening-toewijzing toepassen op ING-transacties
4. WHEN ING-transacties worden opgeslagen, THE Banking_Processor SHALL een gelaagde duplicaatdetectie-strategie toepassen:
   - **Laag 1 (primair)**: Match op de samengestelde Ref2-sleutel + TransactionDate + administration. Dit is betrouwbaar wanneer het "Mededelingen"-veld unieke informatie bevat (pasvolgnummer, tijdstip, transactiereferentie)
   - **Laag 2 (fallback)**: Wanneer het "Mededelingen"-veld leeg is, gebruik een telvergelijking per dag: tel het aantal transacties in het CSV-bestand met dezelfde combinatie van datum + bedrag + richting + beschrijving, en vergelijk met het aantal reeds opgeslagen transacties in de database. Alleen het verschil wordt als nieuw beschouwd
   - NB: ING CSV bevat geen uniek transactie-ID of volgnummer — deze strategie is gebaseerd op best practices voor duplicaatdetectie zonder unieke identifiers (ref: Enable Banking, AI Accountant). Dit onderdeel is nog niet definitief en wordt verder uitgewerkt in het technisch ontwerp

### Requirement 6: Frontend ING CSV-verwerking

**User Story:** Als gebruiker wil ik ING CSV-bestanden kunnen uploaden via de bestaande Banking Processor-interface, zodat ik geen apart scherm nodig heb.

#### Acceptance Criteria

1. THE Frontend_Processor SHALL een `processINGTransaction`-functie bevatten in een apart bestand die ING CSV-regels verwerkt naar Transaction_Record-objecten
2. WHEN een ING CSV-bestand wordt geselecteerd, THE Frontend_Processor SHALL automatisch de ING-verwerkingsfunctie aanroepen op basis van bestandsherkenning
3. THE Frontend_Processor SHALL de ING-transacties weergeven in dezelfde review-tabel als Rabobank-transacties
4. WHEN een ING-transactie een bedrag van 0,00 heeft, THE Frontend_Processor SHALL deze transactie overslaan

### Requirement 7: ING-specifieke metadata bewaren

**User Story:** Als gebruiker wil ik dat ING-specifieke informatie zoals transactiecode en mutatiesoort beschikbaar blijft, zodat ik transacties later kan analyseren.

#### Acceptance Criteria

1. THE ING_CSV_Parser SHALL het "Code"-veld (BA, OV, GT, IC, DV) en "Mutatiesoort"-veld opnemen in de TransactionDescription
2. THE ING_CSV_Parser SHALL de transactiebeschrijving formatteren als: "[Code] Naam / Omschrijving - Mededelingen" wanneer alle velden beschikbaar zijn
3. WHEN het "Mededelingen"-veld leeg is, THE ING_CSV_Parser SHALL alleen "Naam / Omschrijving" gebruiken als beschrijving

### Requirement 8: Saldocontrole na ING-import

**User Story:** Als gebruiker wil ik na het importeren van ING-transacties kunnen controleren of het berekende saldo klopt met het werkelijke banksaldo, zodat ik zeker weet dat er geen transacties ontbreken of dubbel zijn geïmporteerd.

#### Acceptance Criteria

1. THE Banking_Processor SHALL na import van ING-transacties het intern berekende saldo (som van alle debet- en creditmutaties) voor de ING-rekening kunnen tonen via de bestaande `check_banking_accounts`-functie
2. THE Frontend_Processor SHALL de gebruiker de mogelijkheid bieden om het actuele ING-banksaldo handmatig in te voeren ter vergelijking met het intern berekende saldo
3. WHEN het intern berekende saldo afwijkt van het door de gebruiker ingevoerde banksaldo, THE Frontend_Processor SHALL het verschil duidelijk tonen met een waarschuwing
4. NB: Het ING CSV-formaat bevat geen saldo-kolom (in tegenstelling tot Rabobank Ref3 en Revolut). De saldocontrole is daarom afhankelijk van handmatige invoer door de gebruiker. Dit is een essentiële controle om ontbrekende of dubbele transacties te detecteren

### Requirement 9: Foutafhandeling bij ING CSV-verwerking

**User Story:** Als gebruiker wil ik duidelijke foutmeldingen krijgen bij problemen met ING-bestanden, zodat ik weet wat er mis is.

#### Acceptance Criteria

1. IF een ING CSV-bestand geen geldige transactieregels bevat, THEN THE ING_CSV_Parser SHALL een foutmelding retourneren met de tekst "Geen geldige transacties gevonden in ING-bestand"
2. IF een datumveld een ongeldig formaat heeft (niet YYYYMMDD of niet-numeriek), THEN THE ING_CSV_Parser SHALL de betreffende regel overslaan en een waarschuwing loggen
3. IF een bedragveld niet naar een numerieke waarde kan worden geconverteerd, THEN THE ING_CSV_Parser SHALL de betreffende regel overslaan en een waarschuwing loggen
4. IF het bestand niet in ISO-8859-1 encoding kan worden gelezen, THEN THE ING_CSV_Parser SHALL een fallback naar UTF-8 encoding proberen
