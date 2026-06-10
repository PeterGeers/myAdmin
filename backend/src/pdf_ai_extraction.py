"""
AI-powered invoice data extraction using OpenRouter API.

Handles AI extraction calls and usage logging for the PDF processing pipeline.
"""
from typing import Optional, List


def extract_with_ai(lines: List[str], folder_name: str) -> Optional[dict]:
    """Extract invoice data using AI only. No vendor-specific fallback.
    
    Args:
        lines: List of text lines from the document
        folder_name: Vendor/folder name for context
    
    Returns:
        Dictionary with extracted invoice data, or None on error
    """
    try:
        from ai_extractor import AIExtractor
        ai_extractor = AIExtractor()

        previous_transactions = []
        try:
            from database import DatabaseManager
            db = DatabaseManager()
            previous_transactions = db.get_previous_transactions(folder_name, limit=3)
        except Exception as e:
            print(f"Could not get previous transactions: {e}")

        text_content = '\n'.join(lines)
        print(f"Starting AI extraction for {folder_name}...", flush=True)
        ai_result = ai_extractor.extract_invoice_data(
            text_content, folder_name, previous_transactions
        )

        if ai_result and ai_result.get('total_amount', 0) > 0:
            print(f"AI extraction successful for {folder_name}: €{ai_result['total_amount']}", flush=True)
            return ai_result
        else:
            print(f"AI extraction returned no valid amount for {folder_name}", flush=True)
            return ai_result  # Return the zero-amount result

    except Exception as e:
        print(f"AI extraction error for {folder_name}: {e}", flush=True)
        return None


def log_ai_usage(folder_name: str, ai_result: Optional[dict], tenant: Optional[str] = None) -> None:
    """Log AI extraction usage to ai_usage_log with actual token counts.
    
    Args:
        folder_name: Vendor/folder name for the extraction
        ai_result: AI extraction result containing _usage metadata
        tenant: Current tenant identifier for tracking
    """
    try:
        from database import DatabaseManager
        from services.ai_usage_tracker import AIUsageTracker

        db = DatabaseManager()
        tracker = AIUsageTracker(db)

        # Use actual token counts from the API response metadata
        usage_meta = ai_result.get('_usage', {}) if ai_result else {}
        tokens_used = usage_meta.get('total_tokens', 0)
        model_used = usage_meta.get('model', 'deepseek/deepseek-chat')

        # Skip logging if no token data available (e.g., fallback result)
        if tokens_used == 0:
            return

        tracker.log_ai_request(
            administration=tenant or 'unknown',
            template_type=f"invoice_extraction_{folder_name}",
            tokens_used=tokens_used,
            model_used=model_used
        )
    except Exception as e:
        # Never fail the extraction because of logging
        print(f"Could not log AI usage: {e}")
