import requests
import json
import os
from datetime import datetime
from dotenv import load_dotenv

from services.ai_sanitizer import AISanitizer

# Load environment variables
load_dotenv()


class AIExtractor:
    def __init__(self):
        self.api_key = os.getenv('OPENROUTER_API_KEY')
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"
        self.sanitizer = AISanitizer()

        if not self.api_key:
            print("Warning: OPENROUTER_API_KEY not found in environment variables")
        else:
            print("AI Extractor initialized successfully")

    def extract_invoice_data(self, text_content, vendor_hint=None, previous_transactions=None):
        """Extract invoice data using AI with fallback models.

        Sanitizes text content through AISanitizer before prompt construction
        to prevent prompt injection attacks. Uses system+user role separation
        for secure AI communication.

        Returns:
            dict with extraction fields and _usage metadata, or
            dict with 'error' key if content is rejected or validation fails.
        """
        # Sanitize the PDF text content before prompt construction
        sanitize_result = self.sanitizer.sanitize(text_content)

        # Handle rejection (>50% stripped)
        if sanitize_result.rejected:
            print("AI extraction rejected: document content could not be safely processed")
            return {"error": "Document content could not be safely processed"}

        # Build prompt with system+user role separation
        messages = self.sanitizer.build_extraction_prompt(
            sanitized_text=sanitize_result.text,
            vendor_hint=vendor_hint,
            previous_transactions=previous_transactions,
        )

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
                print(f"Trying model: {model}...")
                response = requests.post(
                    self.base_url,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": model,
                        "messages": messages,
                        "temperature": 0.1,
                        "max_tokens": 500
                    },
                    timeout=10
                )

                if response.status_code == 200:
                    result = response.json()
                    content = result['choices'][0]['message']['content'].strip()

                    # Capture actual token usage from API response
                    usage = result.get('usage', {})

                    # Extract JSON from response
                    if content.startswith('```json'):
                        content = content.replace('```json', '').replace('```', '').strip()

                    try:
                        data = json.loads(content)

                        # Validate AI response structure and types
                        if not self.sanitizer.validate_response(data):
                            print(f"{model} returned invalid response format, discarding")
                            continue  # Try next model

                        # Validate and clean data
                        print(f"Successfully extracted data using {model}")
                        return {
                            'date': self._validate_date(data.get('date')),
                            'total_amount': round(float(data.get('total_amount', 0)), 2),
                            'vat_amount': round(float(data.get('vat_amount', 0)), 2),
                            'description': str(data.get('description', '')),
                            'vendor': str(data.get('vendor', vendor_hint or 'Unknown')),
                            '_usage': {
                                'prompt_tokens': usage.get('prompt_tokens', 0),
                                'completion_tokens': usage.get('completion_tokens', 0),
                                'total_tokens': usage.get('total_tokens', 0),
                                'model': model
                            }
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

        # All models failed — return validation failure error
        print("All AI models failed to produce valid response")
        return {"error": "AI extraction failed: invalid response format"}
    
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
            'vendor': vendor_hint or 'Unknown',
            '_usage': {
                'prompt_tokens': 0,
                'completion_tokens': 0,
                'total_tokens': 0,
                'model': ''
            }
        }