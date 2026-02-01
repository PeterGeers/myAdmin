import requests
import json
import os
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class AIExtractor:
    def __init__(self):
        self.api_key = os.getenv('OPENROUTER_API_KEY')
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"
        
        if not self.api_key:
            print("Warning: OPENROUTER_API_KEY not found in environment variables")
        else:
            print(f"AI Extractor initialized with API key: {self.api_key[:20]}...")
        
    def extract_invoice_data(self, text_content, vendor_hint=None, previous_transactions=None):
        """Extract invoice data using AI with fallback models"""
        
        # Build context from previous transactions
        context_info = ""
        if previous_transactions and len(previous_transactions) > 0:
            context_info = "\n\nPrevious transactions from this vendor for reference:\n"
            for i, tx in enumerate(previous_transactions[:3]):  # Use last 3 transactions
                context_info += f"- Date: {tx.get('Datum', 'N/A')}, Description: {tx.get('Omschrijving', 'N/A')}, Amount: €{tx.get('Bedrag', 'N/A')}\n"
            context_info += "\nUse these patterns to help identify similar fields in the current invoice.\n"
        
        prompt = f"""Extract these 5 fields from this invoice/receipt text:

1. Date (convert to YYYY-MM-DD format)
2. Total amount (final amount to pay, as number only)
3. VAT amount (total VAT/BTW, as number only)
4. Description (order number, invoice number, or main identifier)
5. Vendor name

Text content:
{text_content}{context_info}

Return ONLY valid JSON in this exact format:
{{"date": "YYYY-MM-DD", "total_amount": 0.00, "vat_amount": 0.00, "description": "text", "vendor": "name"}}

Rules:
- Date must be YYYY-MM-DD format
- Amounts must be numbers (no currency symbols)
- If VAT not found, use 0.00
- Description should include ALL identifiers: invoice numbers (Factuurnummer), customer numbers (Klantnummer), order numbers, etc.
- Extract vendor name from header/footer
- Look for patterns similar to previous transactions from this vendor
- Invoice/customer numbers may appear before or after their labels
- Combine multiple identifiers in description (e.g., "Factuurnummer: 123456, Klantnummer: 789012")"""

        if not self.api_key:
            print("No API key available, skipping AI extraction")
            return self._fallback_data(vendor_hint)
        
        # Try DeepSeek first (very cheap, excellent for structured extraction), then free models as fallback
        models = [
            "deepseek/deepseek-chat",  # Primary: Very cheap ($0.27/$1.10 per 1M tokens), excellent for invoice extraction
            "meta-llama/llama-3.2-3b-instruct:free",  # Free fallback
            "moonshotai/kimi-k2:free",  # Free fallback
            "google/gemini-flash-1.5",  # Free, very fast
            "microsoft/phi-3-mini-128k-instruct:free",  # Free fallback
            "openai/gpt-3.5-turbo"  # Paid fallback (last resort)
        ]
        
        for model in models:
            try:
                print(f"Trying {model} with key: {self.api_key[:10]}...")
                response = requests.post(
                    self.base_url,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": model,
                        "messages": [
                            {"role": "user", "content": prompt}
                        ],
                        "temperature": 0.1,
                        "max_tokens": 500
                    },
                    timeout=10
                )
                
                if response.status_code == 200:
                    result = response.json()
                    content = result['choices'][0]['message']['content'].strip()
                    
                    # Extract JSON from response
                    if content.startswith('```json'):
                        content = content.replace('```json', '').replace('```', '').strip()
                    
                    try:
                        data = json.loads(content)
                        
                        # Validate and clean data
                        print(f"Successfully extracted data using {model}")
                        return {
                            'date': self._validate_date(data.get('date')),
                            'total_amount': round(float(data.get('total_amount', 0)), 2),
                            'vat_amount': round(float(data.get('vat_amount', 0)), 2),
                            'description': str(data.get('description', '')),
                            'vendor': str(data.get('vendor', vendor_hint or 'Unknown'))
                        }
                    except json.JSONDecodeError:
                        print(f"{model} returned invalid JSON: {content}")
                        continue  # Try next model
                else:
                    print(f"{model} API error: {response.status_code} - {response.text}")
                    continue  # Try next model
                    
            except requests.exceptions.Timeout:
                print(f"{model} timeout after 10 seconds, trying next model")
                continue
            except Exception as e:
                print(f"{model} error: {e}, trying next model")
                continue
        
        # All models failed
        print("All AI models failed, using fallback data")
        return self._fallback_data(vendor_hint)
    
    def _validate_date(self, date_str):
        """Validate and format date"""
        if not date_str:
            return datetime.now().strftime('%Y-%m-%d')
        
        try:
            # Try to parse various date formats
            for fmt in ['%Y-%m-%d', '%d-%m-%Y', '%d/%m/%Y', '%Y/%m/%d']:
                try:
                    parsed = datetime.strptime(date_str, fmt)
                    return parsed.strftime('%Y-%m-%d')
                except ValueError:
                    continue
            
            # If no format matches, return current date
            return datetime.now().strftime('%Y-%m-%d')
        except:
            return datetime.now().strftime('%Y-%m-%d')
    
    def _fallback_data(self, vendor_hint):
        """Return fallback data when AI fails"""
        return {
            'date': datetime.now().strftime('%Y-%m-%d'),
            'total_amount': 0.0,
            'vat_amount': 0.0,
            'description': f'{vendor_hint or "Unknown"} invoice',
            'vendor': vendor_hint or 'Unknown'
        }