# Prediction Improvement Plan

Verbetervoorstel voor de banking prediction, gebaseerd op de huidige implementatie.
Phase1 already implemented
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