#!/usr/bin/env python3
"""
Manual test script for duplicate detection API endpoints.
This script can be used to manually test the API endpoints.
"""

import requests
import json
import sys
import os

# Add src to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

def test_check_duplicate_endpoint():
    """Test the /api/check-duplicate endpoint"""
    url = "http://localhost:5000/api/check-duplicate"
    
    # Test data
    test_data = {
        'referenceNumber': 'TestVendor',
        'transactionDate': '2024-01-01',
        'transactionAmount': 100.00,
        'newFileUrl': 'http://example.com/test.pdf',
        'newFileId': 'file123'
    }
    
    try:
        response = requests.post(url, json=test_data)
        print(f"Check Duplicate Response Status: {response.status_code}")
        print(f"Check Duplicate Response: {json.dumps(response.json(), indent=2)}")
        return response.json()
    except requests.exceptions.ConnectionError:
        print("Error: Could not connect to server. Make sure Flask app is running on localhost:5000")
        return None
    except Exception as e:
        print(f"Error testing check duplicate endpoint: {e}")
        return None

def test_log_decision_endpoint():
    """Test the /api/log-duplicate-decision endpoint"""
    url = "http://localhost:5000/api/log-duplicate-decision"
    
    # Test data
    test_data = {
        'decision': 'continue',
        'duplicateInfo': {
            'existing_transactions': [{'id': 1}],
            'duplicate_count': 1
        },
        'newTransactionData': {
            'ReferenceNumber': 'TestVendor',
            'TransactionDate': '2024-01-01',
            'TransactionAmount': 100.00,
            'Ref3': 'http://example.com/new.pdf'
        },
        'userId': 'test_user',
        'sessionId': 'test_session'
    }
    
    try:
        response = requests.post(url, json=test_data)
        print(f"Log Decision Response Status: {response.status_code}")
        print(f"Log Decision Response: {json.dumps(response.json(), indent=2)}")
        return response.json()
    except requests.exceptions.ConnectionError:
        print("Error: Could not connect to server. Make sure Flask app is running on localhost:5000")
        return None
    except Exception as e:
        print(f"Error testing log decision endpoint: {e}")
        return None

def main():
    """Run manual tests for duplicate detection API"""
    print("=== Manual API Test for Duplicate Detection ===")
    print("Note: This requires the Flask server to be running on localhost:5000")
    print()
    
    print("1. Testing /api/check-duplicate endpoint...")
    check_result = test_check_duplicate_endpoint()
    print()
    
    print("2. Testing /api/log-duplicate-decision endpoint...")
    log_result = test_log_decision_endpoint()
    print()
    
    if check_result and log_result:
        print("✅ Both API endpoints responded successfully!")
    else:
        print("❌ One or more API endpoints failed to respond")
    
    print("\n=== Test Complete ===")

if __name__ == '__main__':
    main()