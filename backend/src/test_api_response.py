#!/usr/bin/env python3
"""Test API response directly"""

import requests
import json

def test_api_endpoint():
    """Test a specific API endpoint"""
    url = "http://127.0.0.1:5000/api/status"
    
    try:
        response = requests.get(url, timeout=5)
        print(f"Status Code: {response.status_code}")
        print(f"Content-Type: {response.headers.get('Content-Type', 'Not set')}")
        print(f"Response Length: {len(response.text)}")
        print(f"First 200 chars: {response.text[:200]}")
        
        if response.text.startswith('<!DOCTYPE') or response.text.startswith('<!doctype'):
            print("ERROR: Received HTML instead of JSON!")
        else:
            try:
                data = response.json()
                print(f"JSON Response: {json.dumps(data, indent=2)}")
            except json.JSONDecodeError:
                print("ERROR: Response is not valid JSON")
                
    except requests.exceptions.RequestException as e:
        print(f"Request failed: {e}")

if __name__ == "__main__":
    test_api_endpoint()