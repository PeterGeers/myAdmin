"""
Test script to verify Cognito authentication is working.
This script helps you test the authentication flow without needing a full frontend.
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def print_cognito_config():
    """Print current Cognito configuration"""
    print("\n" + "="*60)
    print("COGNITO CONFIGURATION")
    print("="*60)
    
    user_pool_id = os.getenv('COGNITO_USER_POOL_ID')
    client_id = os.getenv('COGNITO_CLIENT_ID')
    region = os.getenv('AWS_REGION', 'eu-west-1')
    
    print(f"User Pool ID: {user_pool_id}")
    print(f"Client ID: {client_id}")
    print(f"Region: {region}")
    
    # Get the actual Cognito domain from AWS
    import subprocess
    try:
        result = subprocess.run(
            ['aws', 'cognito-idp', 'describe-user-pool', 
             '--user-pool-id', user_pool_id, 
             '--region', region,
             '--query', 'UserPool.Domain',
             '--output', 'text'],
            capture_output=True,
            text=True
        )
        domain = result.stdout.strip()
    except:
        domain = "myadmin-6x2848jl"  # Fallback to known domain
    
    hosted_ui_url = f"https://{domain}.auth.{region}.amazoncognito.com/login"
    
    print(f"\nHosted UI URL: {hosted_ui_url}")
    print(f"Full Login URL: {hosted_ui_url}?client_id={client_id}&response_type=token&redirect_uri=http://localhost:3000/callback")
    
    print("\n" + "="*60)
    print("HOW TO GET A JWT TOKEN FOR TESTING")
    print("="*60)
    print("\n1. Open the Full Login URL above in your browser")
    print("2. Login with your Cognito credentials")
    print("3. After successful login, you'll be redirected to the callback URL")
    print("4. The URL will contain: #id_token=<LONG_JWT_TOKEN>&access_token=...")
    print("5. Copy the id_token value (everything between id_token= and &access_token)")
    print("6. Use that token to test API endpoints")
    
    print("\n" + "="*60)
    print("TESTING API ENDPOINTS")
    print("="*60)
    print("\nOnce you have the token, test with PowerShell:")
    print('\n$token = "YOUR_ID_TOKEN_HERE"')
    print('curl -H "Authorization: Bearer $token" http://localhost:5000/api/reports/available-years')
    
    print("\n" + "="*60)

def test_endpoint_without_auth():
    """Test that endpoints require authentication"""
    import requests
    
    print("\n" + "="*60)
    print("TESTING ENDPOINT WITHOUT AUTHENTICATION")
    print("="*60)
    
    try:
        response = requests.get('http://localhost:5000/api/reports/available-years')
        print(f"\nStatus Code: {response.status_code}")
        print(f"Response: {response.json()}")
        
        if response.status_code == 401 or 'error' in response.json():
            print("\n✅ Authentication is properly enforced!")
        else:
            print("\n⚠️ Warning: Endpoint accessible without authentication!")
    except requests.exceptions.ConnectionError:
        print("\n❌ Error: Backend server is not running on http://localhost:5000")
        print("Start the backend with: python backend/src/app.py")
    except Exception as e:
        print(f"\n❌ Error: {e}")

if __name__ == '__main__':
    print_cognito_config()
    
    # Check if requests library is available
    try:
        import requests
        test_endpoint_without_auth()
    except ImportError:
        print("\n⚠️ 'requests' library not installed. Skipping endpoint test.")
        print("Install with: pip install requests")
