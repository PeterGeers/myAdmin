#!/usr/bin/env python3
import requests
import sys

def test_backend():
    """Test if backend is running and responding"""
    try:
        # Test basic connection
        response = requests.get('http://localhost:5000/api/test', timeout=5)
        if response.status_code == 200:
            print("[OK] Backend is running and responding")
            print(f"Response: {response.json()}")
        else:
            print(f"[ERROR] Backend responded with status {response.status_code}")
            
        # Test folders endpoint
        response = requests.get('http://localhost:5000/api/folders', timeout=5)
        if response.status_code == 200:
            print("[OK] Folders endpoint working")
            folders = response.json()
            print(f"Found {len(folders)} folders: {folders}")
        else:
            print(f"[ERROR] Folders endpoint failed with status {response.status_code}")
            
    except requests.exceptions.ConnectionError:
        print("[ERROR] Cannot connect to backend - is it running on port 5000?")
    except requests.exceptions.Timeout:
        print("[ERROR] Backend connection timed out")
    except Exception as e:
        print(f"[ERROR] Error: {e}")

def test_frontend():
    """Test if frontend is accessible"""
    try:
        response = requests.get('http://localhost:3000', timeout=5)
        if response.status_code == 200:
            print("[OK] Frontend is accessible")
        else:
            print(f"[ERROR] Frontend responded with status {response.status_code}")
    except requests.exceptions.ConnectionError:
        print("[ERROR] Cannot connect to frontend - is it running on port 3000?")
    except Exception as e:
        print(f"[ERROR] Frontend error: {e}")

if __name__ == "__main__":
    print("Testing myAdmin application...")
    print("\n--- Backend Tests ---")
    test_backend()
    print("\n--- Frontend Tests ---")
    test_frontend()