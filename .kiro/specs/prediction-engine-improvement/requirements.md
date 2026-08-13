# Requirements Document

## Introduction

This specification covers improvements to the banking transaction prediction engine. The system currently predicts ReferenceNumber (referentiecode) and counter-account (tegenrekening) when importing bank transactions, using verb extraction from transaction descriptions as the sole lookup key.

The primary improvement (Phase 1) introduces a sequential prediction flow: first predict the reference code via existing verb-matching, then use that predicted reference code as a lookup key to find the counter-account. This exploits the more stable relationship between reference codes and counter-accounts compared to the verb-to-counter-account relationship.

Phases 2–4 are documented as future requirements and will be implemented after Phase 1 is validated.

## Glossary

- **Prediction_Engine**: The subsystem responsible for predicting missing field values (ReferenceNumber, Debet, Credit) when importing bank transactions
- **Verb**: A company or vendor name extracted from the transaction description, used as a lookup key
- **Reference_Code**: The ReferenceNumber field value — a free label that gains meaning in context (e.g., "KPN", "Picnic", "ASR|Zorgverzekering")
- **Counter_Account**: The ledger account (Debet or Credit) opposite the bank account in a transaction
- **Bank_Account**: The Debet or Credit account identified as the bank account (e.g., 1300)
- **Verb_Matching**: The existing mechanism that extracts a company name from the transaction description and uses it as a lookup key
- **Reference_Lookup**: The new mechanism that uses a predicted reference code as a key to find the counter-account
- **Majority_Voting**: The conflict resolution strategy that selects the most frequent value when multiple historical values exist for a key
- **Confidence_Score**: A numeric value (0.0–1.0) representing the reliability of a prediction
- **Administration**: The tenant context — all patterns and predictions are scoped to a single administration
- **Pattern_Table**: The database table `pattern_verb_patterns` storing discovered verb patterns
- **IBAN**: International Bank Account Number, present in some transaction records as an additional identifier
- **Compound_Verb**: A verb containing both company and reference parts separated by a pipe character (e.g., "ASR|Zorgverzekering")
- **Correction_Tracking**: The mechanism that records when a user modifies a predicted value after import
- **Consistency_Check**: A post-prediction validation that verifies whether the combination of predicted reference code and counter-account historically co-occurs

## Requirements

### Requirement 0: Pattern Data Hygiene (Prerequisite)

**User Story:** As the Prediction_Engine, I want the pattern_verb_patterns table to contain accurate and current data, so that confidence scores and occurrence counts are reliable for all prediction methods.

#### Acceptance Criteria

1. WHEN a full pattern analysis runs, THE Prediction_Engine SHALL replace occurrence counts with the freshly calculated values (`occurrences = VALUES(occurrences)`) instead of accumulating them (`occurrences = occurrences + VALUES(occurrences)`)
2. AFTER a full pattern analysis completes, THE Prediction_Engine SHALL delete patterns from pattern_verb_patterns where `last_seen` is older than the analysis window start date (one year ago), removing stale patterns that no longer appear in recent transactions
3. THE Prediction_Engine SHALL not delete patterns during incremental analysis — only during full analysis
4. WHEN stale patterns are deleted, THE Prediction_Engine SHALL log the count of removed patterns for observability

### Requirement 1: Build Reference-to-Account Lookup Structure

**User Story:** As the Prediction_Engine, I want to maintain a lookup structure mapping reference codes to counter-accounts, so that predicted reference codes can serve as keys for counter-account prediction.

#### Acceptance Criteria

1. WHEN the Prediction_Engine analyzes historical transactions, THE Prediction_Engine SHALL build a lookup structure keyed by Administration + Bank_Account + Reference_Code that maps to a list of counter-account values with occurrence counts, skipping transactions where Reference_Code is empty or blank
2. THE Prediction_Engine SHALL scope the reference-to-account lookup to the same data window as existing verb pattern analysis (one year of historical transactions)
3. WHEN multiple counter-accounts exist for the same Reference_Code, THE Prediction_Engine SHALL select the most frequent counter-account as the dominant mapping with a Confidence_Score equal to the ratio of its occurrences to total occurrences (majority ratio)
4. THE Prediction_Engine SHALL store the occurrence count, last-seen date, Confidence_Score, and minority occurrence count for each reference-to-account mapping, preserving information about alternative counter-accounts without discarding them
5. WHEN fewer than 2 historical transactions exist for a Reference_Code, THE Prediction_Engine SHALL still include the mapping in the lookup structure but SHALL cap its Confidence_Score at 0.50, reflecting the limited evidence base

### Requirement 2: Sequential Prediction Flow

**User Story:** As the Prediction_Engine, I want to use the predicted reference code as input for counter-account prediction, so that the more stable reference-to-account relationship improves prediction accuracy.

#### Acceptance Criteria

1. WHEN a transaction is imported with both Reference_Code and Counter_Account fields empty, THE Prediction_Engine SHALL first predict the Reference_Code using existing Verb_Matching before attempting Counter_Account prediction
2. WHEN a Reference_Code prediction succeeds, THE Prediction_Engine SHALL use the predicted Reference_Code as a lookup key to predict the Counter_Account via Reference_Lookup
3. WHEN Reference_Lookup produces a result with Confidence_Score at or above 0.80, THE Prediction_Engine SHALL mark the Counter_Account prediction as confident (blue indicator)
4. WHEN Reference_Lookup produces a result with Confidence_Score below 0.80, THE Prediction_Engine SHALL still use the result but SHALL mark the Counter_Account prediction as uncertain (orange indicator)
5. WHEN Reference_Lookup produces no result, THE Prediction_Engine SHALL fall back to existing Verb_Matching for Counter_Account prediction
6. THE Prediction_Engine SHALL record which prediction method produced the final Counter_Account value (reference_lookup or verb_matching) in the prediction metadata as a method indicator alongside the confidence fields
7. WHEN a transaction is imported with Reference_Code already populated but Counter_Account empty, THE Prediction_Engine SHALL use the existing Reference_Code directly as a lookup key for Reference_Lookup (bypassing Verb_Matching for the reference prediction step)

### Requirement 3: Preserve Existing Verb-Matching as Fallback

**User Story:** As the Prediction_Engine, I want to retain the existing verb-matching mechanism for counter-account prediction as a fallback, so that prediction coverage does not decrease when Reference_Lookup has no match.

#### Acceptance Criteria

1. WHEN Reference_Lookup is not applicable (no Reference_Code was predicted and none was pre-filled), THE Prediction_Engine SHALL use existing Verb_Matching to predict the Counter_Account
2. WHEN Reference_Lookup produces no result, THE Prediction_Engine SHALL use existing Verb_Matching to predict the Counter_Account
3. IF either Reference_Lookup or Verb_Matching produces a Counter_Account prediction, THEN THE Prediction_Engine SHALL output that prediction as the Counter_Account value with appropriate confidence indicator (blue for ≥ 0.80, orange for < 0.80)
4. THE Prediction_Engine SHALL maintain a prediction success rate of at least 92% measured on transactions whose verb appears in the Pattern_Table for the same Administration and Bank_Account, as a minimum baseline after the change
5. IF both Reference_Lookup and Verb_Matching fail to produce any Counter_Account prediction, THEN THE Prediction_Engine SHALL leave the Counter_Account field empty and record no prediction in the metadata

### Requirement 4: Confidence Scoring for Reference Lookup

**User Story:** As the Prediction_Engine, I want to calculate confidence scores for reference-to-account predictions using majority voting, so that unreliable predictions are suppressed.

#### Acceptance Criteria

1. THE Prediction_Engine SHALL calculate Reference_Lookup Confidence_Score as the occurrence count of the most frequent counter-account divided by the total occurrence count for that Reference_Code, producing a value in the range 0.0 to 1.0
2. IF the Reference_Lookup Confidence_Score is below 0.80, THEN THE Prediction_Engine SHALL still return the Reference_Lookup result but SHALL mark it as uncertain by setting a `_uncertain` metadata flag to true on the transaction
3. IF the Reference_Code itself was predicted with a Confidence_Score below 1.0, THEN THE Prediction_Engine SHALL multiply the Reference_Lookup confidence by the Reference_Code confidence to produce a combined Confidence_Score
4. THE Prediction_Engine SHALL expose the Confidence_Score (0.0–1.0) and prediction method (one of: "reference_lookup", "verb_matching") in the transaction metadata fields (\_debet_confidence, \_credit_confidence, \_reference_confidence)
5. IF no prediction was produced for a field, THEN THE Prediction_Engine SHALL set the corresponding confidence metadata field to null

### Requirement 5: Reference-to-Account Index from Existing Data

**User Story:** As the Prediction_Engine, I want to derive reference-to-account mappings from the existing verb pattern data, so that no additional database table or storage step is needed.

#### Acceptance Criteria

1. THE Prediction_Engine SHALL build the reference-account index from the existing `pattern_verb_patterns` data that is already loaded into memory during pattern application
2. THE Prediction_Engine SHALL re-index patterns by `reference_number` field to enable O(1) lookup by reference code
3. THE Prediction_Engine SHALL benefit from the existing multi-level cache automatically, since the source data (verb patterns) is already cached
4. WHEN the cache is invalidated for an Administration, THE Prediction_Engine SHALL rebuild the reference-account index from the refreshed verb patterns on the next apply-patterns call
5. THE Prediction_Engine SHALL not require any new database tables, migration scripts, or separate storage functions for reference-to-account lookups

### Requirement 6: Compound Verb Handling in Reference Lookup

**User Story:** As the Prediction_Engine, I want the reference-to-account lookup to handle compound verbs correctly, so that multi-product vendors (e.g., ASR with multiple insurance products) resolve to the correct counter-account per product.

#### Acceptance Criteria

1. WHEN the predicted Reference_Code contains a pipe character (Company|Reference format), THE Prediction_Engine SHALL classify it as a Compound_Verb and attempt Reference_Lookup using the full compound reference code as the lookup key
2. IF Reference_Lookup using the full compound reference code produces no result, THEN THE Prediction_Engine SHALL not fall back to the company-only part for Reference_Lookup and SHALL instead proceed to Verb_Matching fallback as defined in Requirement 3
3. WHEN the predicted Reference_Code is a simple reference code (contains no pipe character), THE Prediction_Engine SHALL use the simple reference code directly for Reference_Lookup
4. WHEN Reference_Lookup using the full compound reference code produces a result with Confidence_Score above the minimum threshold (0.80), THE Prediction_Engine SHALL use that result as the Counter_Account prediction without attempting company-only lookup

### Requirement 7: Prevent Duplicate and Dead Code

**User Story:** As a developer, I want the sequential prediction flow to reuse existing prediction functions without duplicating logic, so that the codebase remains maintainable and free of dead code.

#### Acceptance Criteria

1. THE Prediction_Engine SHALL implement Reference_Lookup as a new function that is invoked within the existing `apply_patterns_to_transactions` orchestration loop, at the same level as `predict_debet`, `predict_credit`, and `predict_reference` — not as a separate orchestration function that iterates over transactions independently
2. IF Reference_Lookup returns no predicted account (returns None or an empty result), THEN THE Prediction_Engine SHALL invoke the existing `predict_debet` and `predict_credit` functions with their current signatures and logic unmodified
3. THE Prediction_Engine SHALL not introduce separate pattern analysis or storage logic for reference-to-account mappings — it SHALL derive the reference-account index from the existing verb patterns that are already analyzed and stored by `analyze_reference_patterns`
4. THE Prediction_Engine SHALL not contain any function or code path that predicts the counter-account independently from the reference code when both predictions apply to the same transaction — only the single sequential pipeline (predict reference → reference lookup → verb fallback) SHALL produce counter-account predictions
5. THE Prediction_Engine SHALL expose the prediction strategy within `apply_patterns_to_transactions` as a single ordered sequence: first attempt Reference_Lookup, then fall back to verb-matching — with no conditional branching that selects between independent strategy implementations
6. THE Prediction_Engine SHALL use a single confidence calculation function (or formula) invoked by both Reference_Lookup and Verb_Matching predictions, such that any change to confidence scoring is made in exactly one location

---

## Future Phases (Not In Scope for Phase 1)

### Requirement 8: IBAN as Fallback Prediction Signal (Phase 2A)

**User Story:** As the Prediction_Engine, I want to use IBAN as an additional prediction signal when verb-matching and reference-lookup both fail, so that more transactions receive predictions.

#### Acceptance Criteria

1. WHEN both Verb_Matching and Reference_Lookup fail to produce a prediction, THE Prediction_Engine SHALL attempt IBAN-based lookup using the transaction IBAN field
2. WHEN an IBAN match is found, THE Prediction_Engine SHALL predict both Reference_Code and Counter_Account from the IBAN historical data
3. THE Prediction_Engine SHALL build the IBAN lookup from historical transactions where the IBAN field (Ref1) is populated

### Requirement 9: Correction Tracking (Phase 2B)

**User Story:** As the Prediction_Engine, I want to track when users correct predicted values, so that prediction quality can be measured and improved over time.

#### Acceptance Criteria

1. WHEN a transaction is saved with values different from the predicted values, THE Prediction_Engine SHALL record the prediction method, predicted value, final value, and correction flag
2. THE Prediction_Engine SHALL store correction data in a prediction_log structure scoped by Administration
3. THE Prediction_Engine SHALL make correction data available for quality reporting

### Requirement 10: Consistency Check (Phase 3A)

**User Story:** As the Prediction_Engine, I want to validate that the predicted combination of reference code and counter-account historically co-occurs, so that conflicting predictions are suppressed.

#### Acceptance Criteria

1. WHEN both Reference_Code and Counter_Account are predicted, THE Prediction_Engine SHALL check whether this combination exists in historical data
2. IF the predicted combination has never occurred historically while alternative combinations are frequent, THEN THE Prediction_Engine SHALL retract the Counter_Account prediction
3. WHEN the consistency check passes, THE Prediction_Engine SHALL increase the combined Confidence_Score

### Requirement 11: Multi-Factor Confidence (Phase 3B)

**User Story:** As the Prediction_Engine, I want to combine multiple prediction signals into a weighted confidence score, so that predictions supported by multiple factors receive higher confidence.

#### Acceptance Criteria

1. THE Prediction_Engine SHALL combine signals from reference match, IBAN match, verb match, frequency, amount range, and consistency check into a composite Confidence_Score
2. THE Prediction_Engine SHALL weight each signal according to its historical reliability
3. WHEN multiple independent signals agree on the same prediction, THE Prediction_Engine SHALL produce a higher Confidence_Score than any single signal alone

### Requirement 12: Configurable Thresholds (Phase 3C)

**User Story:** As an administrator, I want to configure prediction confidence thresholds per administration, so that different businesses can tune prediction behavior to their needs.

#### Acceptance Criteria

1. WHERE configurable thresholds are set for an Administration, THE Prediction_Engine SHALL use those thresholds instead of the default 0.80 minimum
2. THE Prediction_Engine SHALL support three threshold levels: auto_accept (default 0.98), suggest (default 0.80), and minimum (default 0.60)
3. WHEN no custom thresholds are configured, THE Prediction_Engine SHALL use the default threshold values

### Requirement 13: Auto-Booking (Phase 4A)

**User Story:** As a user, I want transactions with proven high-confidence predictions to be booked automatically, so that manual review effort decreases over time.

#### Acceptance Criteria

1. WHEN Confidence_Score exceeds the auto_accept threshold AND Correction_Tracking data confirms accuracy over 3 months, THE Prediction_Engine SHALL mark the transaction for automatic booking
2. WHEN auto-booking is not explicitly activated for an Administration, THE Prediction_Engine SHALL not auto-book regardless of confidence
3. WHEN the correction ratio for a specific Reference_Code exceeds 2%, THE Prediction_Engine SHALL exclude that Reference_Code from auto-booking

### Requirement 14: Quality Dashboard (Phase 4B)

**User Story:** As an administrator, I want to view prediction accuracy metrics over time, so that I can identify weak patterns and track system improvement.

#### Acceptance Criteria

1. THE Prediction_Engine SHALL provide prediction accuracy statistics grouped by prediction method
2. THE Prediction_Engine SHALL identify the most-corrected patterns for review
3. THE Prediction_Engine SHALL show accuracy trends over time periods (weekly, monthly)

### Requirement 15: AI Fallback (Phase 4C)

**User Story:** As the Prediction_Engine, I want to use AI as a last-resort fallback for transactions where no deterministic method finds a match, so that coverage extends beyond pattern-based prediction.

#### Acceptance Criteria

1. WHEN all deterministic prediction methods fail, THE Prediction_Engine SHALL optionally invoke an AI model to suggest a prediction
2. THE Prediction_Engine SHALL present AI predictions for user review only, never for auto-booking
3. THE Prediction_Engine SHALL provide the AI model with transaction description, historical similar transactions, available reference codes, and the chart of accounts as context
