# Requirements Document — Credit Card Verwerking

## Introductie

De huidige credit card verwerking in de Banking Processor (`processCreditCardTransaction`) bevat hardcoded waarden voor rekeningcodes (`'4002'`, `'2001'`), IBAN-naar-tenant mapping (`NL71RABO0148034454` → `PeterPrive`), en mist ondersteuning voor koersverschillen bij buitenlandse betalingen. Deze feature vervangt de hardcoded logica door een parameter-gedreven aanpak (vergelijkbaar met `$.bank_account` voor bankrekeningen), voegt koersverschillenverwerking toe, en integreert credit card transacties in het bestaande pattern matching systeem.

Het CSV-formaat is Rabo BusinessCard Visa met 13 kolommen, waarvan kolommen 10–12 (Oorspr bedrag, Oorspr munt, Koers) gevuld zijn bij buitenlandse transacties.

## Woordenlijst

- **Banking_Processor**: De frontend-component (`BankingProcessor.tsx`) die CSV-bankafschriften verwerkt en transacties aanmaakt
- **Credit_Card_Processor**: De nieuwe module die credit card CSV-bestanden (`CSV_CC_*`) verwerkt — wordt geëxtraheerd uit de Banking_Processor
- **Rekeningschema**: De database-tabel die het rekeningplan bevat, met een `parameters` JSON-kolom voor configuratievlaggen
- **LookupData**: Het frontend dataobject dat rekeninggegevens bevat, opgehaald via de backend API (`get_lookups`)
- **Pattern_Matcher**: Het bestaande systeem dat transacties automatisch aan grootboekrekeningen koppelt op basis van omschrijvingspatronen
- **Koersverschil**: Het verschil tussen het oorspronkelijke bedrag in vreemde valuta (omgerekend naar EUR op transactiedatum) en het afgerekende EUR-bedrag op het credit card overzicht
- **Tegenrekening_IBAN**: Het IBAN van de bankrekening waaraan de credit card is gekoppeld (kolom 0 in het CSV-bestand)
- **Transactiereferentie**: Het unieke transactie-ID in het credit card CSV-bestand (kolom 6), gebruikt voor duplicaatdetectie
- **Afrekenbedrag**: Het bedrag in EUR zoals afgerekend op het credit card overzicht (kolom 8)
- **Oorspronkelijk_Bedrag**: Het bedrag in de oorspronkelijke vreemde valuta (kolom 10), leeg bij EUR-transacties
- **DatabaseManager**: De backend abstractielaag voor database-operaties, met methoden als `get_bank_account_lookups()`

## Requirements

### Requirement 1: Credit Card Rekening Identificatie via Parameters

**User Story:** Als boekhouder wil ik dat credit card rekeningen automatisch worden herkend via een `$.credit_card` vlag in het rekeningschema, zodat ik geen hardcoded waarden nodig heb en meerdere credit cards per tenant kan configureren.

#### Acceptance Criteria

1. THE Rekeningschema SHALL ondersteunen dat een rekening wordt gemarkeerd met `$.credit_card = true` in de `parameters` JSON-kolom
2. WHEN een rekening de vlag `$.credit_card = true` heeft, THE Rekeningschema SHALL ook een `$.iban` parameter bevatten met het gekoppelde Tegenrekening_IBAN
3. WHEN een rekening de vlag `$.credit_card = true` heeft, THE Rekeningschema SHALL ook een `$.card_number` parameter bevatten met de laatste 4 cijfers van het creditcardnummer (bijv. `"6416"`)
4. THE DatabaseManager SHALL een methode `get_credit_card_lookups(administration)` bieden die alle rekeningen ophaalt waar `JSON_EXTRACT(parameters, '$.credit_card') = true`, gefilterd op administratie
5. WHEN `get_credit_card_lookups` wordt aangeroepen, THE DatabaseManager SHALL per rekening het IBAN (`$.iban`), het rekeningnummer (`Account`), het kaartnummer (`$.card_number`) en de administratienaam retourneren
6. THE LookupData SHALL een nieuw veld `credit_card_accounts` bevatten, gevuld met de resultaten van `get_credit_card_lookups`

### Requirement 2: Dynamische Credit Card Rekeningresolutie

**User Story:** Als boekhouder wil ik dat de credit card processor het Tegenrekening_IBAN uit het CSV-bestand gebruikt om de juiste tenant en grootboekrekening op te zoeken, zodat hardcoded mappings worden geëlimineerd.

#### Acceptance Criteria

1. WHEN een CSV_CC-bestand wordt verwerkt, THE Credit_Card_Processor SHALL het Tegenrekening_IBAN (kolom 0) opzoeken in `lookupData.credit_card_accounts` om de bijbehorende tenant en rekeningcode te bepalen
2. WHEN het Tegenrekening_IBAN niet wordt gevonden in `lookupData.credit_card_accounts`, THE Credit_Card_Processor SHALL een foutmelding tonen: "Credit card rekening [IBAN] is niet geconfigureerd voor deze tenant. Voeg deze toe in het Rekeningschema met de credit_card vlag."
3. WHEN het Tegenrekening_IBAN wordt gevonden, THE Credit_Card_Processor SHALL de `Administration` van de transactie instellen op de administratienaam uit de lookup
4. WHEN het Tegenrekening_IBAN wordt gevonden, THE Credit_Card_Processor SHALL de credit-zijde van de boeking instellen op de rekeningcode uit de lookup (in plaats van hardcoded `'2001'`)
5. THE Credit_Card_Processor SHALL geen hardcoded IBAN-waarden, rekeningcodes of tenantnamen bevatten

### Requirement 3: Koersverschillen bij Buitenlandse Betalingen

**User Story:** Als boekhouder wil ik dat koersverschillen bij buitenlandse credit card betalingen automatisch worden berekend en geboekt op een aparte grootboekrekening, zodat mijn administratie de werkelijke valutaresultaten weerspiegelt.

#### Acceptance Criteria

1. WHEN kolommen 10 (Oorspronkelijk_Bedrag), 11 (Oorspr munt) en 12 (Koers) gevuld zijn in een CSV_CC-regel, THE Credit_Card_Processor SHALL de transactie herkennen als een buitenlandse betaling
2. WHEN een buitenlandse betaling wordt verwerkt, THE Credit_Card_Processor SHALL het koersverschil berekenen als: `Afrekenbedrag (kolom 8) - (Oorspronkelijk_Bedrag (kolom 10) / Koers (kolom 12))`
3. WHEN het berekende koersverschil niet nul is, THE Credit_Card_Processor SHALL een aparte koersverschiltransactie aanmaken naast de hoofdtransactie
4. THE Rekeningschema SHALL ondersteunen dat een rekening wordt gemarkeerd met `$.exchange_rate_account = true` in de `parameters` JSON-kolom voor de koersverschillenrekening (bijv. "4910 Koersverschillen")
5. WHEN een koersverschiltransactie wordt aangemaakt, THE Credit_Card_Processor SHALL het koersverschilbedrag boeken op de rekening met `$.exchange_rate_account = true`
6. WHEN het koersverschil positief is (koerswinst), THE Credit_Card_Processor SHALL het bedrag als credit boeken op de koersverschillenrekening
7. WHEN het koersverschil negatief is (koersverlies), THE Credit_Card_Processor SHALL het bedrag als debet boeken op de koersverschillenrekening
8. WHEN een buitenlandse betaling wordt verwerkt, THE Credit_Card_Processor SHALL de oorspronkelijke valuta, het oorspronkelijke bedrag en de koers opslaan in de transactiebeschrijving of referentievelden
9. IF de koersverschillenrekening (`$.exchange_rate_account = true`) niet is geconfigureerd in het rekeningschema, THEN THE Credit_Card_Processor SHALL een waarschuwing tonen en de transactie verwerken zonder koersverschilboeking

### Requirement 4: Duplicaatdetectie op Transactiereferentie

**User Story:** Als boekhouder wil ik dat credit card transacties worden gecontroleerd op duplicaten via de unieke Transactiereferentie, zodat ik niet per ongeluk dezelfde transactie twee keer importeer.

#### Acceptance Criteria

1. THE Credit_Card_Processor SHALL de Transactiereferentie (kolom 6) opslaan in het `Ref2`-veld van de transactie
2. WHEN een credit card transactie wordt verwerkt, THE Credit_Card_Processor SHALL controleren of een transactie met dezelfde Transactiereferentie al bestaat in de database
3. WHEN een duplicaat wordt gedetecteerd op basis van Transactiereferentie, THE Credit_Card_Processor SHALL de transactie overslaan en deze meetellen in het duplicaatoverzicht
4. THE Credit_Card_Processor SHALL het Tegenrekening_IBAN opslaan in `Ref3` en de productnaam (kolom 3, bijv. "Rabo BusinessCard Visa") in `Ref1`

### Requirement 5: Pattern Matching Integratie

**User Story:** Als boekhouder wil ik dat credit card transacties door hetzelfde pattern matching systeem gaan als banktransacties, zodat terugkerende uitgaven (AWS, Google Workspace, etc.) automatisch aan de juiste grootboekrekening worden gekoppeld.

#### Acceptance Criteria

1. WHEN credit card transacties zijn geladen, THE Pattern_Matcher SHALL dezelfde patronen toepassen op credit card transacties als op reguliere banktransacties
2. WHEN een patroon matcht op een credit card transactie, THE Pattern_Matcher SHALL de debet-rekeningcode toewijzen volgens het patroon (in plaats van hardcoded `'4002'`)
3. WHEN geen patroon matcht op een credit card transactie, THE Credit_Card_Processor SHALL de debet-zijde leeg laten zodat de gebruiker handmatig kan toewijzen
4. THE Credit_Card_Processor SHALL het `ReferenceNumber`-veld leeg laten zodat de Pattern_Matcher dit kan invullen (consistent met het Rabobank-patroon)

### Requirement 6: Module-extractie uit Banking Processor

**User Story:** Als ontwikkelaar wil ik dat de credit card verwerkingslogica in een apart module wordt geplaatst, zodat de Banking Processor beheersbaar blijft (momenteel 2247 regels) en de credit card logica onafhankelijk kan worden getest.

#### Acceptance Criteria

1. THE Credit_Card_Processor SHALL worden geïmplementeerd als een apart TypeScript-module (bijv. `CreditCardProcessor.ts`) buiten `BankingProcessor.tsx`
2. THE Credit_Card_Processor SHALL dezelfde `Transaction`-interface en `LookupData`-interface gebruiken als de Banking_Processor
3. WHEN een CSV_CC-bestand wordt gedetecteerd, THE Banking_Processor SHALL de verwerking delegeren aan de Credit_Card_Processor module
4. THE Credit_Card_Processor module SHALL onafhankelijk testbaar zijn met Vitest en fast-check

### Requirement 7: CSV Parsing en Validatie

**User Story:** Als boekhouder wil ik dat het credit card CSV-bestand correct wordt geparsed en gevalideerd, zodat ongeldige bestanden worden afgewezen met een duidelijke foutmelding.

#### Acceptance Criteria

1. WHEN een CSV_CC-bestand wordt geopend, THE Credit_Card_Processor SHALL de headerregel overslaan (kolom 0 = "Tegenrekening IBAN")
2. WHEN een CSV_CC-regel minder dan 13 kolommen bevat, THE Credit_Card_Processor SHALL de regel overslaan en `null` retourneren
3. WHEN het bedrag (kolom 8) nul is, THE Credit_Card_Processor SHALL de regel overslaan
4. THE Credit_Card_Processor SHALL bedragen correct parsen met komma als decimaalteken (bijv. "-20,58" → -20.58)
5. WHEN het bedrag negatief is (uitgave), THE Credit_Card_Processor SHALL het absolute bedrag gebruiken als `TransactionAmount` en de debet-zijde vullen (kostenrekening)
6. WHEN het bedrag positief is (creditering/verrekening), THE Credit_Card_Processor SHALL het bedrag gebruiken als `TransactionAmount` en de credit-zijde vullen
7. THE Credit_Card_Processor SHALL de transactiedatum uit kolom 7 gebruiken (formaat: YYYY-MM-DD)
8. THE Credit_Card_Processor SHALL de omschrijving samenstellen uit kolom 9 (Omschrijving), met optioneel de oorspronkelijke valuta-informatie bij buitenlandse transacties

## Correctheidseigenschappen voor Property-Based Testing

### P1: Round-trip — CSV Parsing en Transactie-aanmaak (Requirement 7)

**Eigenschap:** Voor elke geldige credit card CSV-regel met een geconfigureerd IBAN, geldt dat het parsen van de regel naar een `Transaction`-object altijd een transactie oplevert waarvan `TransactionAmount > 0`, `TransactionDate` overeenkomt met kolom 7, en `Ref2` overeenkomt met kolom 6 (Transactiereferentie).

**Generator:** Genereer willekeurige CSV-regels met 13 kolommen, geldige datums, bedragen met komma-decimalen (positief en negatief, niet nul), en willekeurige strings voor omschrijvingen.

### P2: Invariant — Geen Hardcoded Waarden (Requirement 2, 5)

**Eigenschap:** Voor elke combinatie van IBAN en lookupData, geldt dat de `Administration` van het resultaat altijd gelijk is aan de administratienaam uit de lookup, en nooit een van de bekende hardcoded waarden (`'PeterPrive'`, `'GoodwinSolutions'`).

**Generator:** Genereer willekeurige IBAN-strings en lookupData met willekeurige administratienamen en rekeningcodes.

### P3: Metamorfische Eigenschap — Koersverschilberekening (Requirement 3)

**Eigenschap:** Voor elke buitenlandse transactie geldt dat de som van het hoofdtransactiebedrag en het koersverschilbedrag gelijk is aan het afgerekende EUR-bedrag (kolom 8). Met andere woorden: `hoofdbedrag + koersverschil = afrekenbedrag`.

**Generator:** Genereer willekeurige bedragen in vreemde valuta, wisselkoersen (> 0), en EUR-afrekenbedragen.

### P4: Idempotentie — Duplicaatdetectie (Requirement 4)

**Eigenschap:** Het twee keer verwerken van hetzelfde CSV-bestand levert bij de tweede keer nul nieuwe transacties op — alle transacties worden als duplicaat gemarkeerd op basis van Transactiereferentie.

### P5: Invariant — Credit Card Lookup Resolutie (Requirement 1, 2)

**Eigenschap:** Voor elke credit card transactie die succesvol wordt verwerkt, geldt dat de `Administration` en credit-rekeningcode altijd afkomstig zijn uit `lookupData.credit_card_accounts` en nooit uit hardcoded waarden.

**Generator:** Genereer willekeurige credit_card_accounts lookups met diverse IBAN's, rekeningcodes en administratienamen.

### P6: Foutconditie — Ontbrekende Configuratie (Requirement 2, 3)

**Eigenschap:** Voor elk IBAN dat niet voorkomt in `lookupData.credit_card_accounts`, gooit de Credit_Card_Processor altijd een fout met een beschrijvende melding die het ontbrekende IBAN bevat.

**Generator:** Genereer willekeurige IBAN-strings die niet voorkomen in de meegegeven lookupData.

## Buiten Scope

- **Nieuwe UI-schermen**: Geen nieuwe pagina's, tabs of knoppen — credit card bestanden worden verwerkt via het bestaande upload-mechanisme in de Banking Processor. De koersverschilberekening vindt plaats als onderdeel van het CSV-parseerproces in de frontend en genereert extra transactieregels; hiervoor is geen apart scherm nodig.
- **Backend API-wijzigingen voor koersverschillen**: De koersverschilberekening vindt plaats in de frontend bij het parsen van het CSV-bestand. Er zijn geen nieuwe backend endpoints nodig — de gegenereerde koersverschiltransacties worden opgeslagen via het bestaande `save_transactions` endpoint.
- **Historische data-migratie**: Bestaande credit card transacties met hardcoded waarden worden niet automatisch gecorrigeerd (kan handmatig via SQL)
- **Meerdere valuta's per bestand**: Het CSV-formaat heeft altijd EUR als afrekenvaluta (kolom 1); ondersteuning voor niet-EUR afrekening is buiten scope
- **Credit card limietbeheer**: Geen tracking van credit card limieten of beschikbaar saldo
- **Automatische koersopvraging**: Wisselkoersen komen uit het CSV-bestand; er wordt geen externe koers-API aangeroepen
- **Reconciliatie met bankafschriften**: De verrekening van het credit card saldo met de bankrekening (de maandelijkse afschrijving) wordt verwerkt als reguliere banktransactie, niet als onderdeel van deze feature
