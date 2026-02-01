#!/usr/bin/env python3
"""
API Alignment Test - Validates frontend API calls match backend routes
Prevents "<!doctype" errors by ensuring all API endpoints exist
"""

import requests
import re
import os
import json
from pathlib import Path

class APIAlignmentTester:
    def __init__(self):
        self.base_url = "http://127.0.0.1:5000"
        self.frontend_dir = Path(__file__).parent.parent.parent / "frontend" / "src"
        self.missing_routes = []
        self.working_routes = []
        
    def extract_api_calls_from_frontend(self):
        """Extract all API calls from React components"""
        api_calls = set()
        
        # Search for fetch calls in TypeScript/JavaScript files
        for file_path in self.frontend_dir.rglob("*.tsx"):
            try:
                content = file_path.read_text(encoding='utf-8')
                
                # Find fetch calls with /api/ URLs
                fetch_patterns = [
                    r'fetch\s*\(\s*[`\'"]([^`\'"]*\/api\/[^`\'"]*)[`\'"]',
                    r'fetch\s*\(\s*`([^`]*\/api\/[^`]*)`',
                    r'await\s+fetch\s*\(\s*[`\'"]([^`\'"]*\/api\/[^`\'"]*)[`\'"]'
                ]
                
                for pattern in fetch_patterns:
                    matches = re.findall(pattern, content)
                    for match in matches:
                        # Clean up the URL (remove query params and localhost prefix)
                        clean_url = match.split('?')[0]
                        if 'localhost:' in clean_url:
                            clean_url = clean_url.split('localhost:5000')[1] if 'localhost:5000' in clean_url else clean_url
                        if '/api/' in clean_url:
                            api_calls.add(clean_url)
                            
            except Exception as e:
                print(f"Error reading {file_path}: {e}")
                
        return sorted(api_calls)
    
    def test_api_endpoint(self, endpoint):
        """Test if an API endpoint exists and returns JSON (not HTML)"""
        try:
            url = f"{self.base_url}{endpoint}"
            
            # Try GET first, then POST for routes that require it
            for method in ['GET', 'POST']:
                try:
                    if method == 'GET':
                        response = requests.get(url, timeout=5)
                    else:
                        response = requests.post(url, json={}, timeout=5)
                    
                    # Check if response is HTML (indicates 404 serving React app)
                    content_type = response.headers.get('content-type', '')
                    is_html = 'text/html' in content_type or response.text.strip().startswith('<!doctype')
                    
                    if is_html:
                        continue  # Try next method
                    
                    # If we get here, it's not HTML - endpoint exists
                    return True, f"OK ({method}, status: {response.status_code})"
                    
                except requests.exceptions.RequestException:
                    continue
            
            return False, f"Returns HTML instead of JSON (all methods tried)"
                
        except Exception as e:
            return False, f"Connection error: {e}"
    
    def run_alignment_test(self):
        """Run the complete API alignment test"""
        print("API Alignment Test - Frontend vs Backend")
        print("=" * 50)
        
        # Extract API calls from frontend
        print("Extracting API calls from React components...")
        api_calls = self.extract_api_calls_from_frontend()
        print(f"Found {len(api_calls)} unique API endpoints in frontend")
        
        if not api_calls:
            print("ERROR: No API calls found in frontend code!")
            return False
        
        print("\nTesting each API endpoint...")
        print("-" * 50)
        
        # Test each endpoint
        for endpoint in api_calls:
            is_working, message = self.test_api_endpoint(endpoint)
            
            if is_working:
                print(f"OK {endpoint} - {message}")
                self.working_routes.append(endpoint)
            else:
                print(f"FAIL {endpoint} - {message}")
                self.missing_routes.append(endpoint)
        
        # Summary
        print("\nTest Summary")
        print("=" * 50)
        print(f"Working endpoints: {len(self.working_routes)}")
        print(f"Missing endpoints: {len(self.missing_routes)}")
        
        if self.missing_routes:
            print("\nMISSING ROUTES (will cause '<!doctype' errors):")
            for route in self.missing_routes:
                print(f"   - {route}")
            
            print("\nFix by adding these routes to Flask backend:")
            for route in self.missing_routes:
                route_name = route.replace('/api/', '').replace('/', '_').replace('-', '_')
                print(f"   @app.route('{route}', methods=['GET'])")
                print(f"   def {route_name}():")
                print(f"       return jsonify({{'success': True, 'data': []}})")
                print()
        
        return len(self.missing_routes) == 0

def main():
    """Main test execution"""
    tester = APIAlignmentTester()
    
    # Check if Flask server is running
    try:
        response = requests.get(f"{tester.base_url}/api/test", timeout=5)
        if response.status_code != 200:
            print("ERROR: Flask server not responding correctly")
            return False
    except:
        print("ERROR: Flask server not running on http://127.0.0.1:5000")
        print("   Start it with: python backend/src/app.py")
        return False
    
    print("OK: Flask server is running")
    
    # Run the alignment test
    success = tester.run_alignment_test()
    
    if success:
        print("\nSUCCESS: All API endpoints are properly aligned!")
        print("   No '<!doctype' errors should occur.")
    else:
        print("\nWARNING: API alignment issues found!")
        print("   Fix missing routes to prevent errors.")
    
    return success

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)