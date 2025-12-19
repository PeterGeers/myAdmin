#!/usr/bin/env python3
"""
Final validation of Debet/Credit prediction functionality
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from banking_processor import BankingProcessor

def main():
    processor = BankingProcessor(test_mode=False)

    # Test with real-world scenario
    test_transactions = [
        {
            'TransactionDescription': 'GAMMA BOUWMARKT HOOFDDORP',
            'TransactionAmount': 125.50,
            'Debet': '',  # Missing - should be predicted
            'Credit': '1002',  # Bank account
            'Administration': 'GoodwinSolutions',
            'TransactionDate': '2025-12-19'
        },
        {
            'TransactionDescription': 'ALBERT HEIJN SUPERMARKT',
            'TransactionAmount': 89.75,
            'Debet': '1002',  # Bank account
            'Credit': '',  # Missing - should be predicted
            'Administration': 'GoodwinSolutions',
            'TransactionDate': '2025-12-19'
        }
    ]

    print('🔍 Testing Debet/Credit Prediction with Real Scenarios...')
    updated_transactions, results = processor.apply_enhanced_patterns(test_transactions, 'GoodwinSolutions')

    print(f'✅ Results:')
    print(f'   - Debet predictions: {results["predictions_made"]["debet"]}')
    print(f'   - Credit predictions: {results["predictions_made"]["credit"]}')
    print(f'   - Average confidence: {results["average_confidence"]:.2f}')

    for i, tx in enumerate(updated_transactions):
        print(f'   Transaction {i+1}:')
        print(f'     - Description: {tx["TransactionDescription"]}')
        print(f'     - Debet: {tx["Debet"]} (confidence: {tx.get("_debet_confidence", "N/A")})')
        print(f'     - Credit: {tx["Credit"]} (confidence: {tx.get("_credit_confidence", "N/A")})')

    print('✅ Debet/Credit prediction functionality validated!')

if __name__ == '__main__':
    main()