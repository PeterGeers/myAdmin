# Finance Prediction Engine

## Doel

De Finance Prediction Engine bepaalt voor iedere ingelezen banktransactie:

1. De **referentiecode**
2. De **tegenrekening / ledger account**

De bankrekening waarop de transactie plaatsvindt en de richting van de transactie zijn al bekend.

Het doel is om zoveel mogelijk transacties automatisch en betrouwbaar te classificeren, waarbij AI alleen wordt ingezet wanneer regels en historische gegevens onvoldoende zekerheid geven.

---

## 1. Bekende informatie

Bij het inladen van een banktransactie zijn minimaal bekend:

- Bankrekening / bank ledger account
- Bedrag
- Positief of negatief bedrag
- Datum
- Omschrijving
- Tegenpartij / IBAN indien beschikbaar
- Eventuele bankreferentie

De richting bepaalt al welke zijde van de boeking de bankrekening krijgt:

```text
Positief bedrag
    Bankrekening = Debet
    Tegenrekening = Credit

Negatief bedrag
    Bankrekening = Credit
    Tegenrekening = Debet
```

De Prediction Engine hoeft dus alleen de ontbrekende classificatie te bepalen.

---

# 2. Wat moet worden voorspeld?

```text
Banktransactie
      │
      ├── Bank ledger account     ← bekend
      ├── Debit / Credit         ← bekend
      │
      ▼
Prediction Engine
      │
      ├── Referentiecode          ← voorspellen
      │
      └── Tegenrekening           ← voorspellen
```

Voorbeeld:

```text
Omschrijving:  KPN factuur 839201
Bedrag:        -72,50

Voorspelling:
    Referentiecode:    KPN
    Tegenrekening:     4600 Telecom
```

---

# 3. Voorgestelde classificatie-flow

De engine werkt in verschillende stappen.

```text
                    Banktransactie
                          │
                          ▼
                 Exacte herkenning
                          │
                    gevonden?
                    /          \
                  ja            nee
                  │              │
                  ▼              ▼
             classificatie   Historische
                              matching
                                  │
                            voldoende zeker?
                            /            \
                          ja              nee
                          │                │
                          ▼                ▼
                    classificatie       AI
                                           │
                                           ▼
                                  classificatievoorstel
                                           │
                                           ▼
                                  Confidence bepalen
                                           │
                                           ▼
                                  Boeken / review
```

---

# 4. Herkenningskenmerken

Gebruik zoveel mogelijk beschikbare informatie:

- Referentiecode
- IBAN
- Tegenpartij
- Tegenpartijnaam
- Omschrijving
- Bankreferentie
- Bedrag
- Transactierichting
- Frequentie
- Historische boekingen
- Eerder gecorrigeerde transacties

Niet ieder kenmerk heeft dezelfde waarde.

Een bekende IBAN in combinatie met een bekende referentiecode is bijvoorbeeld veel sterker dan alleen een overeenkomstig woord in de omschrijving.

---

# 5. Referentiecode als belangrijke sleutel

De referentiecode kan zowel een **voorspeld resultaat** als een **voorspellend kenmerk** zijn.

Bijvoorbeeld:

```text
Nieuwe transactie
      │
      ▼
Herkenning: KPN
      │
      ▼
Historische transacties
      │
      ▼
4600 Telecom
```

Historische gegevens:

| Referentiecode | Tegenrekening | Aantal |
|---|---:|---:|
| KPN | 4600 | 87 |
| KPN | 4650 | 3 |
| KPN | 4000 | 1 |

Daaruit kan bijvoorbeeld volgen:

```text
Referentiecode = KPN
Confidence      = 98,9%

Tegenrekening   = 4600
Confidence      = 95,6%
```

---

# 6. Historische matching

Voordat AI wordt gebruikt, zoekt de engine naar vergelijkbare transacties.

Voorbeeld:

```text
Nieuwe transactie:
"Payment IDEAL Bol.com bestelling 847293"
- €124,95
```

Historie:

```text
"Payment IDEAL Bol.com bestelling 721234"
- €89,95   → 4400

"Payment IDEAL Bol.com bestelling 731283"
- €142,50  → 4400

"Payment IDEAL Bol.com bestelling 812983"
- €79,95   → 4400
```

De engine kan hieruit afleiden:

```text
Referentiecode:    BOL
Tegenrekening:     4400
Confidence:        hoog
```

---

# 7. Prediction Result

De engine levert een volledig classificatieresultaat op.

```json
{
  "transaction_id": "TX12345",
  "predicted_reference_code": "KPN",
  "reference_confidence": 0.994,
  "predicted_ledger_account": "4600",
  "ledger_confidence": 0.988,
  "overall_confidence": 0.982,
  "prediction_method": "historical_match",
  "requires_review": false
}
```

Het resultaat bevat dus expliciet beide voorspellingen.

---

# 8. Confidence

De confidence moet niet alleen op één match worden gebaseerd.

Mogelijke factoren:

```text
IBAN match
+ tegenpartij match
+ referentie match
+ omschrijving match
+ historische frequentie
+ eerdere gebruikerscorrecties
+ consistentie tussen referentiecode en ledger account
```

Voorbeeld:

```text
IBAN match                  +++
Referentiecode match        +++
Tegenpartij match           +++
Historische frequentie      +++
Omschrijving match         ++
```

Daaruit wordt een confidence score berekend.

---

# 9. Beslissingsregels

Een mogelijke eerste versie:

| Confidence | Actie |
|---|---|
| > 98% | Automatisch boeken |
| 90–98% | Voorstel tonen |
| 70–90% | Gebruiker laten kiezen |
| < 70% | Handmatige classificatie |

Deze grenzen moeten configureerbaar zijn.

Voor financiële administratie is **uitlegbaarheid belangrijker dan maximale automatisering**.

---

# 10. Regels vóór AI

De volgorde moet bij voorkeur zijn:

```text
1. Exacte regels
2. Referentiecode
3. IBAN / tegenpartij
4. Historische matching
5. Fuzzy matching
6. Confidence berekening
7. AI
8. Handmatige keuze
```

AI is daarmee een **vangnet**, niet de fundering van het boekhoudsysteem.

---

# 11. AI-classificatie

AI wordt gebruikt wanneer de traditionele classificatie onvoldoende zekerheid geeft.

Input aan AI kan zijn:

```text
Nieuwe transactie
+
Historische vergelijkbare transacties
+
Bestaande referentiecodes
+
Beschikbare ledger accounts
+
Rekeningbeschrijvingen
```

AI retourneert bijvoorbeeld:

```json
{
  "reference_code": "MICROSOFT",
  "ledger_account": "4610",
  "confidence": 0.91,
  "reason": "Vergelijkbare transacties zijn eerder als softwarekosten geboekt."
}
```

AI mag hierbij **een voorstel doen**, maar niet zelfstandig buiten de ingestelde regels boeken.

---

# 12. Zelflerend systeem

Iedere gebruikersactie is waardevolle feedback.

```text
Prediction
    │
    ▼
Gebruiker accepteert
    │
    └──► Historische bevestiging

of

Prediction
    │
    ▼
Gebruiker corrigeert
    │
    └──► Nieuwe classificatie / regel
```

Een correctie moet dus niet alleen de huidige transactie wijzigen.

De correctie moet invloed hebben op toekomstige voorspellingen.

---

# 13. ReferenceRule

Een aparte structuur kan de geleerde relaties bewaren.

```text
ReferenceRule
-------------
reference_code
ledger_account
confidence
match_count
corrected_count
last_used
source
```

Bijvoorbeeld:

```text
KPN
    4600 → 97%
    4650 → 3%
```

Het systeem kan daardoor rekening houden met het feit dat een referentiecode niet altijd naar exact één rekening hoeft te leiden.

---

# 14. TransactionClassification

Naast de regels wordt het classificatieresultaat per transactie opgeslagen.

```text
TransactionClassification
-------------------------
transaction_id
predicted_reference_code
reference_confidence
predicted_ledger_account
ledger_confidence
overall_confidence
prediction_method
requires_review
user_confirmed
user_corrected
```

Hiermee blijft achteraf zichtbaar:

- Wat het systeem voorspelde
- Waarom het werd voorspeld
- Hoe betrouwbaar de voorspelling was
- Of AI werd gebruikt
- Of de gebruiker de voorspelling heeft gecorrigeerd

---

# 15. Belangrijk ontwerpprincipe

De **referentiecode en tegenrekening moeten als twee afzonderlijke voorspellingen worden behandeld**, maar wel met een sterke relatie ertussen.

```text
                    Transactie
                         │
              ┌──────────┴──────────┐
              ▼                     ▼
        Referentiecode         Tegenrekening
              │                     │
              └──────────┬──────────┘
                         │
                  Consistency check
                         │
                         ▼
                  Overall confidence
```

Dit voorkomt bijvoorbeeld:

```text
Referentiecode = KPN
Tegenrekening = 4300 Voeding
```

wanneer historische gegevens duidelijk aantonen dat KPN normaal gesproken naar 4600 Telecom gaat.

---

# 16. Aanbevolen architectuur voor MyAdmin

```text
Bank Import
     │
     ▼
BankTransaction
     │
     ▼
TransactionClassifier
     │
     ├── RuleMatcher
     ├── ReferenceMatcher
     ├── HistoricalMatcher
     ├── FuzzyMatcher
     ├── ConfidenceEngine
     └── AIClassifier
              │
              ▼
     ClassificationResult
              │
       ┌──────┴──────┐
       ▼             ▼
   Auto book       Review
                       │
                       ▼
                 User feedback
                       │
                       ▼
                 Learning data
```

De classifier moet als een afzonderlijke component worden gebouwd, zodat de boekhoudkundige verwerking zelf eenvoudig, deterministisch en auditbaar blijft.

---

# 17. Gefaseerde implementatie

### Fase 1: Geen AI

Implementeren:

- Referentiecode
- IBAN / tegenpartij matching
- Historische matching
- Frequentieanalyse
- Confidence score
- Gebruikerscorrecties

### Fase 2: Slimmere matching

Toevoegen:

- Fuzzy matching
- Meerdere kenmerken combineren
- Consistency check tussen referentiecode en tegenrekening
- Betere confidence berekening

### Fase 3: AI

AI toevoegen voor:

- Onbekende transacties
- Ambigue omschrijvingen
- Nieuwe leveranciers
- Complexe historische patronen

### Fase 4: Automatisering

Bij voldoende vertrouwen:

```text
Hoge confidence
      ↓
Automatisch boeken

Lage confidence
      ↓
Review queue
```

---

# Conclusie

De Finance Prediction Engine moet niet alleen de tegenrekening voorspellen.

De kern is:

> **Voorspel de referentiecode én de tegenrekening, controleer of deze twee voorspellingen logisch bij elkaar passen en bereken vervolgens één overall confidence.**

De beste aanpak is een hybride model:

```text
Deterministische regels
        +
Historische transacties
        +
Pattern matching
        +
Confidence scoring
        +
AI voor uitzonderingen
        +
Gebruikersfeedback
```

Dit levert een systeem op dat steeds slimmer wordt, maar waarvan de financiële beslissingen **controleerbaar, uitlegbaar en auditbaar** blijven.
