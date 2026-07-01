import requests
import json
import os
import base64
from datetime import datetime
from dotenv import load_dotenv
from PIL import Image

from services.ai_model_registry import resolver, RegistryError
from services.ai_usage_tracker import AIUsageTracker

load_dotenv()


class ImageAIProcessor:
    def __init__(self, db=None, tenant=None):
        self.api_key = os.getenv("OPENROUTER_API_KEY")
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"
        self.usage_tracker = AIUsageTracker(db) if db else None
        self.tenant = tenant

    def process_image(self, image_path, vendor_hint=None, previous_transactions=None):
        """Process image using AI vision models, fallback to Tesseract"""

        # Try AI vision first
        result = self._try_ai_vision(image_path, vendor_hint, previous_transactions)
        if result and result["total_amount"] > 0:
            return result

        # Fallback to Tesseract OCR
        print("AI vision failed, trying Tesseract OCR...")
        return self._try_tesseract(image_path, vendor_hint, previous_transactions)

    def _try_ai_vision(self, image_path, vendor_hint, previous_transactions):
        """Try AI vision models from registry, in fallback chain order"""
        if not self.api_key:
            print("No API key, skipping AI vision")
            return None

        # Resolve vision model chain from registry
        try:
            chain = resolver.resolve_profile("vision")
        except RegistryError as e:
            print(f"Registry error resolving vision profile: {e}")
            return None  # Proceed to Tesseract OCR fallback

        # Encode image to base64
        try:
            with open(image_path, "rb") as f:
                image_data = base64.b64encode(f.read()).decode("utf-8")

            # Detect image format
            ext = os.path.splitext(image_path)[1].lower()
            mime_type = (
                f"image/{ext[1:]}" if ext in [".jpg", ".jpeg", ".png"] else "image/jpeg"
            )

        except Exception as e:
            print(f"Error encoding image: {e}")
            return None

        # Build context
        context_info = ""
        if previous_transactions:
            context_info = "\n\nPrevious transactions from this vendor:\n"
            for tx in previous_transactions[:3]:
                context_info += f"- Date: {tx.get('Datum', 'N/A')}, Description: {tx.get('Omschrijving', 'N/A')}, Amount: €{tx.get('Bedrag', 'N/A')}\n"

        prompt = f"""Extract invoice data from this image:

1. Date (YYYY-MM-DD format)
2. Total amount (number only)
3. VAT amount (number only, 0.00 if not found)
4. Description (invoice/order/customer numbers)
5. Vendor name
{context_info}
Return ONLY valid JSON:
{{"date": "YYYY-MM-DD", "total_amount": 0.00, "vat_amount": 0.00, "description": "text", "vendor": "name"}}"""

        # Iterate models in chain order from registry
        for model in chain:
            try:
                print(f"Trying vision model: {model.model_id}")
                response = requests.post(
                    self.base_url,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model.model_id,
                        "messages": [
                            {
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": prompt},
                                    {
                                        "type": "image_url",
                                        "image_url": {
                                            "url": f"data:{mime_type};base64,{image_data}"
                                        },
                                    },
                                ],
                            }
                        ],
                        "temperature": 0.1,
                        "max_tokens": model.max_tokens,
                    },
                    timeout=model.timeout,
                )

                if response.status_code == 200:
                    result = response.json()
                    content = result["choices"][0]["message"]["content"].strip()

                    # Capture token usage
                    usage = result.get("usage", {})
                    tokens_used = usage.get("total_tokens", 0)
                    if tokens_used == 0:
                        tokens_used = usage.get("prompt_tokens", 0) + usage.get(
                            "completion_tokens", 0
                        )

                    if content.startswith("```json"):
                        content = (
                            content.replace("```json", "").replace("```", "").strip()
                        )

                    data = json.loads(content)
                    print(f"✓ Vision extraction successful with {model.model_id}")

                    # Log AI usage
                    if self.usage_tracker and self.tenant and tokens_used > 0:
                        self.usage_tracker.log_ai_request(
                            administration=self.tenant,
                            template_type="vision_extraction",
                            tokens_used=tokens_used,
                            model_used=model.model_id,
                        )

                    return {
                        "date": self._validate_date(data.get("date")),
                        "total_amount": round(float(data.get("total_amount", 0)), 2),
                        "vat_amount": round(float(data.get("vat_amount", 0)), 2),
                        "description": str(data.get("description", "")),
                        "vendor": str(data.get("vendor", vendor_hint or "Unknown")),
                    }
                else:
                    print(
                        f"{model.model_id} error: {response.status_code} - {response.text[:200]}"
                    )

            except json.JSONDecodeError as e:
                print(f"{model.model_id} JSON error: {e}")
                continue
            except Exception as e:
                print(f"{model.model_id} failed: {str(e)[:200]}")
                continue

        return None  # All models failed, proceed to Tesseract OCR fallback

    def _try_tesseract(self, image_path, vendor_hint, previous_transactions):
        """Fallback to Tesseract OCR + AI text extraction"""
        try:
            import subprocess

            subprocess.run(
                [r"C:\Program Files\Tesseract-OCR\tesseract.exe", "--version"],
                capture_output=True,
                check=True,
            )
        except Exception:
            print("Tesseract not installed")
            return self._fallback_data(vendor_hint)

        try:
            import pytesseract

            pytesseract.pytesseract.tesseract_cmd = (
                r"C:\Program Files\Tesseract-OCR\tesseract.exe"
            )

            image = Image.open(image_path)
            if image.mode != "RGB":
                image = image.convert("RGB")

            text = pytesseract.image_to_string(image)
            print(f"OCR extracted {len(text)} characters")

            if not text.strip():
                return self._fallback_data(vendor_hint)

            # Use AI to extract from OCR text
            from ai_extractor import AIExtractor

            ai = AIExtractor()
            result = ai.extract_invoice_data(text, vendor_hint, previous_transactions)
            print("✓ Tesseract OCR + AI extraction successful")
            return result

        except Exception as e:
            print(f"Tesseract error: {e}")
            return self._fallback_data(vendor_hint)

    def _validate_date(self, date_str):
        if not date_str:
            return datetime.now().strftime("%Y-%m-%d")
        try:
            for fmt in ["%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"]:
                try:
                    return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
                except ValueError:
                    continue
            return datetime.now().strftime("%Y-%m-%d")
        except Exception:
            return datetime.now().strftime("%Y-%m-%d")

    def _fallback_data(self, vendor_hint):
        return {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "total_amount": 0.0,
            "vat_amount": 0.0,
            "description": f"{vendor_hint or 'Unknown'} invoice",
            "vendor": vendor_hint or "Unknown",
        }
