#!/usr/bin/env python3
"""
Validate Prediction Engine — Baseline Measurement Script (Task 3.0)

This script measures prediction accuracy by:
1. Connecting to the local database
2. Finding an administration with existing patterns
3. Loading patterns via PatternAnalyzer
4. Fetching transactions from `mutaties` that already have ReferenceNumber
   and/or counter-accounts filled in (ground truth)
5. Stripping those values and re-running prediction
6. Comparing predicted values vs actual values
7. Reporting statistics: hit rate, miss rate, wrong predictions,
   confidence distribution, and prediction method breakdown

This provides a baseline measurement BEFORE the sequential prediction flow
is wired up (task 3.1). Run again after to compare.

Requirements validated: 3.4 (prediction success rate ≥ 92%)
"""

import sys
import os
from datetime import datetime, timedelta
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from database import DatabaseManager
from pattern_analyzer import PatternAnalyzer
from pattern_scoring import (
    build_reference_account_index,
    predict_account_from_reference,
    predict_debet,
    predict_credit,
    predict_reference,
    CONFIDENCE_THRESHOLD_CONFIDENT,
)


def get_administration_with_patterns(db: DatabaseManager) -> str | None:
    """Find an administration that has existing patterns in the database."""
    result = db.execute_query(
        """
        SELECT administration, COUNT(*) as pattern_count
        FROM pattern_verb_patterns
        GROUP BY administration
        ORDER BY pattern_count DESC
        LIMIT 1
        """
    )
    if result:
        return result[0]["administration"]
    return None


def get_ground_truth_transactions(
    db: DatabaseManager, administration: str, limit: int = 500
) -> list[dict]:
    """
    Fetch recent transactions that have both ReferenceNumber and a counter-account.
    These serve as ground truth for measuring prediction accuracy.
    """
    one_year_ago = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")

    transactions = db.execute_query(
        """
        SELECT ID, TransactionDescription, TransactionAmount, TransactionDate,
               Debet, Credit, ReferenceNumber, Ref1, administration
        FROM mutaties
        WHERE administration = %s
          AND TransactionDate >= %s
          AND ReferenceNumber IS NOT NULL
          AND ReferenceNumber != ''
          AND (
              (Debet IS NOT NULL AND Debet != '' AND Credit IS NOT NULL AND Credit != '')
          )
        ORDER BY TransactionDate DESC
        LIMIT %s
        """,
        (administration, one_year_ago, limit),
    )

    return transactions


def run_validation(
    analyzer: PatternAnalyzer,
    transactions: list[dict],
    administration: str,
) -> dict:
    """
    For each transaction, strip the predicted fields and re-predict.
    Compare predicted values vs actual (ground truth).

    Returns detailed statistics.
    """
    patterns = analyzer.get_filtered_patterns(administration)
    reference_patterns = patterns.get("reference_patterns", {})

    # Build reference account index (Phase 2 functionality)
    ref_account_index = build_reference_account_index(reference_patterns)

    stats = {
        "total_transactions": len(transactions),
        "reference": {
            "hit": 0,
            "miss": 0,
            "wrong": 0,
            "not_applicable": 0,
        },
        "counter_account": {
            "hit": 0,
            "miss": 0,
            "wrong": 0,
            "not_applicable": 0,
        },
        "confidence_buckets": {
            "0.00-0.50": 0,
            "0.50-0.80": 0,
            "0.80-0.95": 0,
            "0.95-1.00": 0,
        },
        "prediction_methods": {
            "reference_lookup": 0,
            "verb_matching": 0,
            "none": 0,
        },
        "wrong_predictions": [],
    }

    for tx in transactions:
        actual_ref = tx.get("ReferenceNumber", "").strip()
        actual_debet = tx.get("Debet", "").strip()
        actual_credit = tx.get("Credit", "").strip()

        # Determine bank account and counter-account from the ground truth
        bank_account = None
        actual_counter_account = None

        if analyzer.is_bank_account(actual_debet, administration):
            bank_account = actual_debet
            actual_counter_account = actual_credit
        elif analyzer.is_bank_account(actual_credit, administration):
            bank_account = actual_credit
            actual_counter_account = actual_debet

        # --- Reference Prediction ---
        # Create a stripped transaction (no ReferenceNumber)
        stripped_tx = tx.copy()
        stripped_tx["ReferenceNumber"] = ""

        ref_prediction = predict_reference(
            stripped_tx,
            reference_patterns,
            analyzer.is_bank_account,
            analyzer._extract_verb_from_description,
        )

        if ref_prediction:
            predicted_ref = ref_prediction.get("value", "").strip()
            if predicted_ref == actual_ref:
                stats["reference"]["hit"] += 1
            elif predicted_ref:
                stats["reference"]["wrong"] += 1
            else:
                stats["reference"]["miss"] += 1
        else:
            stats["reference"]["miss"] += 1

        # --- Counter-Account Prediction ---
        # Strip counter-account (keep bank account side)
        stripped_tx2 = tx.copy()
        if bank_account == actual_debet:
            # Bank is debet, strip credit (the counter-account side)
            stripped_tx2["Credit"] = ""
        elif bank_account == actual_credit:
            # Bank is credit, strip debet (the counter-account side)
            stripped_tx2["Debet"] = ""
        else:
            # Cannot determine bank account — skip counter-account test
            stats["counter_account"]["not_applicable"] += 1
            stats["prediction_methods"]["none"] += 1
            continue

        # Try reference lookup first (simulating Phase 3 sequential flow)
        counter_predicted = False
        predicted_counter = None
        prediction_method = "none"
        confidence = 0.0

        # Step 2: Reference lookup (using actual reference as key with confidence 1.0)
        if actual_ref and bank_account:
            ref_lookup = predict_account_from_reference(
                reference_code=actual_ref,
                reference_confidence=1.0,
                bank_account=bank_account,
                administration=administration,
                reference_account_index=ref_account_index,
            )
            if ref_lookup:
                predicted_counter = ref_lookup["value"]
                confidence = ref_lookup["confidence"]
                prediction_method = "reference_lookup"
                counter_predicted = True

        # Step 3: Verb-matching fallback
        if not counter_predicted:
            if bank_account == actual_credit and not stripped_tx2.get("Debet"):
                debet_prediction = predict_debet(
                    stripped_tx2,
                    reference_patterns,
                    administration,
                    analyzer.is_bank_account,
                    analyzer._extract_verb_from_description,
                    analyzer.get_filtered_patterns,
                )
                if debet_prediction:
                    predicted_counter = debet_prediction["value"]
                    confidence = debet_prediction["confidence"]
                    prediction_method = "verb_matching"
                    counter_predicted = True
            elif bank_account == actual_debet and not stripped_tx2.get("Credit"):
                credit_prediction = predict_credit(
                    stripped_tx2,
                    reference_patterns,
                    administration,
                    analyzer.is_bank_account,
                    analyzer._extract_verb_from_description,
                    analyzer.get_filtered_patterns,
                )
                if credit_prediction:
                    predicted_counter = credit_prediction["value"]
                    confidence = credit_prediction["confidence"]
                    prediction_method = "verb_matching"
                    counter_predicted = True

        # Record prediction method
        stats["prediction_methods"][prediction_method] += 1

        # Record confidence bucket
        if counter_predicted and confidence > 0:
            if confidence < 0.50:
                stats["confidence_buckets"]["0.00-0.50"] += 1
            elif confidence < 0.80:
                stats["confidence_buckets"]["0.50-0.80"] += 1
            elif confidence < 0.95:
                stats["confidence_buckets"]["0.80-0.95"] += 1
            else:
                stats["confidence_buckets"]["0.95-1.00"] += 1

        # Compare counter-account prediction vs ground truth
        if counter_predicted and predicted_counter:
            if predicted_counter == actual_counter_account:
                stats["counter_account"]["hit"] += 1
            else:
                stats["counter_account"]["wrong"] += 1
                # Track wrong predictions for analysis (limit to first 10)
                if len(stats["wrong_predictions"]) < 10:
                    stats["wrong_predictions"].append(
                        {
                            "id": tx.get("ID"),
                            "description": tx.get("TransactionDescription", "")[:60],
                            "actual": actual_counter_account,
                            "predicted": predicted_counter,
                            "confidence": confidence,
                            "method": prediction_method,
                            "reference": actual_ref,
                        }
                    )
        else:
            stats["counter_account"]["miss"] += 1

    return stats


def print_report(stats: dict) -> None:
    """Print a formatted validation report."""
    total = stats["total_transactions"]

    print()
    print("=" * 70)
    print("📊 PREDICTION ENGINE VALIDATION REPORT")
    print("=" * 70)
    print(f"\nTotal transactions evaluated: {total}")

    # --- Reference Prediction ---
    print("\n" + "-" * 70)
    print("📌 REFERENCE NUMBER PREDICTION")
    print("-" * 70)
    ref = stats["reference"]
    ref_total = ref["hit"] + ref["miss"] + ref["wrong"]
    if ref_total > 0:
        hit_rate = ref["hit"] / ref_total * 100
        miss_rate = ref["miss"] / ref_total * 100
        wrong_rate = ref["wrong"] / ref_total * 100
        print(f"  Hit (correct):      {ref['hit']:>5} ({hit_rate:.1f}%)")
        print(f"  Miss (no prediction): {ref['miss']:>5} ({miss_rate:.1f}%)")
        print(f"  Wrong (incorrect):  {ref['wrong']:>5} ({wrong_rate:.1f}%)")
        # Success rate = hits / (hits + wrongs) — misses are not failures
        if ref["hit"] + ref["wrong"] > 0:
            precision = ref["hit"] / (ref["hit"] + ref["wrong"]) * 100
            print(f"  Precision:          {precision:.1f}%")
    else:
        print("  No reference predictions evaluated")

    # --- Counter-Account Prediction ---
    print("\n" + "-" * 70)
    print("📌 COUNTER-ACCOUNT PREDICTION")
    print("-" * 70)
    ca = stats["counter_account"]
    ca_total = ca["hit"] + ca["miss"] + ca["wrong"]
    if ca_total > 0:
        hit_rate = ca["hit"] / ca_total * 100
        miss_rate = ca["miss"] / ca_total * 100
        wrong_rate = ca["wrong"] / ca_total * 100
        print(f"  Hit (correct):        {ca['hit']:>5} ({hit_rate:.1f}%)")
        print(f"  Miss (no prediction): {ca['miss']:>5} ({miss_rate:.1f}%)")
        print(f"  Wrong (incorrect):    {ca['wrong']:>5} ({wrong_rate:.1f}%)")
        if ca["not_applicable"] > 0:
            print(f"  Not applicable:       {ca['not_applicable']:>5}")
        # Success rate = hits / (hits + wrongs)
        if ca["hit"] + ca["wrong"] > 0:
            precision = ca["hit"] / (ca["hit"] + ca["wrong"]) * 100
            print(f"  Precision:            {precision:.1f}%")
        # Coverage = (hits + wrongs) / total
        coverage = (ca["hit"] + ca["wrong"]) / ca_total * 100
        print(f"  Coverage:             {coverage:.1f}%")
    else:
        print("  No counter-account predictions evaluated")

    # --- Confidence Distribution ---
    print("\n" + "-" * 70)
    print("📌 CONFIDENCE DISTRIBUTION (counter-account predictions)")
    print("-" * 70)
    buckets = stats["confidence_buckets"]
    total_with_conf = sum(buckets.values())
    for bucket, count in buckets.items():
        pct = count / total_with_conf * 100 if total_with_conf > 0 else 0
        bar = "█" * int(pct / 2)
        print(f"  {bucket}: {count:>5} ({pct:>5.1f}%) {bar}")

    # --- Prediction Method Breakdown ---
    print("\n" + "-" * 70)
    print("📌 PREDICTION METHOD BREAKDOWN")
    print("-" * 70)
    methods = stats["prediction_methods"]
    total_methods = sum(methods.values())
    for method, count in methods.items():
        pct = count / total_methods * 100 if total_methods > 0 else 0
        print(f"  {method:20s}: {count:>5} ({pct:.1f}%)")

    # --- Wrong Predictions Detail ---
    if stats["wrong_predictions"]:
        print("\n" + "-" * 70)
        print("📌 SAMPLE WRONG PREDICTIONS (first 10)")
        print("-" * 70)
        for wp in stats["wrong_predictions"]:
            print(f"  ID {wp['id']}: {wp['description']}")
            print(
                f"    Ref: {wp['reference']} | "
                f"Actual: {wp['actual']} → Predicted: {wp['predicted']} "
                f"(conf: {wp['confidence']:.2f}, method: {wp['method']})"
            )

    # --- Overall Assessment ---
    print("\n" + "=" * 70)
    print("📌 OVERALL ASSESSMENT")
    print("=" * 70)

    # Requirement 3.4: prediction success rate ≥ 92%
    if ca_total > 0:
        # Success rate among predictions made (excluding misses)
        predictions_made = ca["hit"] + ca["wrong"]
        if predictions_made > 0:
            success_rate = ca["hit"] / predictions_made * 100
            threshold = 92.0
            status = "✅ PASS" if success_rate >= threshold else "❌ BELOW TARGET"
            print(
                f"  Counter-account precision: {success_rate:.1f}% "
                f"(target: ≥{threshold}%) {status}"
            )
        else:
            print("  No counter-account predictions were made")

    ref_total = ref["hit"] + ref["miss"] + ref["wrong"]
    if ref_total > 0:
        ref_predictions_made = ref["hit"] + ref["wrong"]
        if ref_predictions_made > 0:
            ref_precision = ref["hit"] / ref_predictions_made * 100
            print(f"  Reference precision: {ref_precision:.1f}%")

    print("=" * 70)


def main():
    print("=" * 70)
    print("🔍 Prediction Engine Validation Script (Task 3.0)")
    print(f"   Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    print()

    # Step 1: Connect to database
    print("Step 1: Connecting to database...")
    try:
        db = DatabaseManager(test_mode=False)
        print("  ✅ Connected to database")
    except Exception as e:
        print(f"  ❌ Failed to connect: {e}")
        sys.exit(1)

    # Step 2: Find an administration with patterns
    print("\nStep 2: Finding administration with existing patterns...")
    administration = get_administration_with_patterns(db)
    if not administration:
        print("  ❌ No administrations found with patterns. Nothing to validate.")
        sys.exit(0)
    print(f"  ✅ Using administration: '{administration}'")

    # Step 3: Initialize PatternAnalyzer
    print("\nStep 3: Initializing PatternAnalyzer...")
    analyzer = PatternAnalyzer(test_mode=False)
    print("  ✅ PatternAnalyzer initialized")

    # Step 4: Load patterns (triggers analysis or cache load)
    print("\nStep 4: Loading patterns...")
    patterns = analyzer.get_filtered_patterns(administration)
    ref_patterns = patterns.get("reference_patterns", {})
    print(f"  ✅ Loaded {len(ref_patterns)} reference patterns")

    # Build reference account index
    ref_index = build_reference_account_index(ref_patterns)
    print(f"  ✅ Built reference account index with {len(ref_index)} entries")

    # Step 5: Fetch ground truth transactions
    print("\nStep 5: Fetching ground truth transactions...")
    transactions = get_ground_truth_transactions(db, administration, limit=500)
    print(f"  ✅ Found {len(transactions)} transactions with ground truth data")

    if not transactions:
        print("  ❌ No transactions found with both ReferenceNumber and counter-account")
        sys.exit(0)

    # Step 6: Run validation
    print("\nStep 6: Running prediction validation...")
    print(f"  Processing {len(transactions)} transactions...")
    stats = run_validation(analyzer, transactions, administration)

    # Step 7: Print report
    print_report(stats)

    return 0


if __name__ == "__main__":
    sys.exit(main())
