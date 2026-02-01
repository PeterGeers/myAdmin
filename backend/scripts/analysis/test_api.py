#!/usr/bin/env python3
"""
Test the API endpoint directly
"""

import requests

def test_api():
    try:
        # Test without date
        print("=== Testing API without date ===")
        response = requests.get('http://localhost:5000/api/banking/check-accounts?test_mode=false')
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
        
        # Test with date
        print("\n=== Testing API with date ===")
        response = requests.get('http://localhost:5000/api/banking/check-accounts?test_mode=false&end_date=2025-05-01')
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_api()