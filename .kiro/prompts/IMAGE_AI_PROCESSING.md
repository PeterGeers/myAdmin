# AI Vision Image Processing

## Overview
PNG/JPG invoice images are now processed using **AI vision models first**, with **Tesseract OCR as fallback**.

## Processing Flow

```
PNG/JPG Upload
    ↓
AI Vision Models (CHEAP)
    ├─ openai/gpt-4o-mini ✓ ~$0.00015/image
    ├─ google/gemini-2.0-flash-exp:free (rate-limited)
    └─ anthropic/claude-3-haiku (backup)
    ↓ (if all fail)
Tesseract OCR
    ↓
AI Text Extraction (existing ai_extractor.py)
    ↓
Transaction Data
```

## Key Features

1. **No OCR needed for most invoices** - AI vision understands layout directly
2. **Very cheap** - Uses `gpt-4o-mini` (~$0.00015 per image)
3. **Automatic fallback** - If AI fails, uses Tesseract OCR
4. **Context-aware** - Uses previous transactions for better accuracy
5. **PDF unchanged** - PDF processing remains as-is

## Files Modified

- `src/image_ai_processor.py` - NEW: AI vision processor
- `src/pdf_processor.py` - Updated `_process_image()` to use AI vision
- `test/test_image_ai.py` - NEW: Test script

## Testing

```bash
cd backend
python test/test_image_ai.py path/to/invoice.png
```

## Configuration

Uses existing `OPENROUTER_API_KEY` from `.env` file. No additional setup needed.

## Advantages over OCR

- Better table understanding
- Handles rotated/skewed images
- Understands context (invoice vs receipt)
- No Tesseract installation required (but still supported as fallback)
- More accurate amount extraction
