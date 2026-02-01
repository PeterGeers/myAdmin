#!/usr/bin/env python3
"""Simple test to check if Flask server is running and routes work"""

import requests
import json

def test_server():
    base_url = "http://127.0.0.1:5000"
    
    # Test basic server
    try:
        response = requests.get(f"{base_url}/api/test", timeout=5)
        print(f"Test endpoint: {response.status_code}")
        if response.status_code == 200:
            print(f"Response: {response.json()}")
        else:
            print(f"Error response: {response.text}")
    except Exception as e:
        print(f"Server not responding: {e}")
        return False
    
    # Test available years
    try:
        response = requests.get(f"{base_url}/api/reports/available-years", timeout=5)
        print(f"Available years: {response.status_code}")
        if response.status_code == 200:
            print(f"Years: {response.json()}")
        else:
            print(f"Error: {response.text[:200]}")
    except Exception as e:
        print(f"Available years error: {e}")
    
    return True

if __name__ == "__main__":
    test_server()