"""
Invoice Test Service

Orchestrates invoice pipeline execution in dry-run mode with stdout capture,
timing, and error collection. Wraps existing pipeline components (PDFProcessor,
CsvRuleEngine) without forking — ensures the test tool always reflects actual
pipeline behavior.

Used by the SysAdmin Test Tool for diagnostics without database writes,
Google Drive uploads, or S3 uploads.
"""

import io
import os
import time
import contextlib
import traceback
from decimal import Decimal

from pdf_processor import PDFProcessor
from csv_rules import CsvRuleEngine
from services.ai_model_registry import resolver, RegistryError


class InvoiceTestService:
    """Service for testing the invoice pipeline in dry-run mode.

    Provides full pipeline transparency: raw extracted text, AI/CSV extraction
    results, formatted transactions, prepared transactions, performance metrics,
    AI usage preview, and pipeline execution logs.
    """

    def __init__(self):
        """Initialize with pipeline components in test mode.

        PDFProcessor is initialized with test_mode=True to avoid any
        production side effects. CsvRuleEngine is stateless and needs
        no special configuration.
        """
        self.processor = PDFProcessor(test_mode=True)
        self.csv_rule_engine = CsvRuleEngine()

    # Maximum characters for raw text output
    MAX_RAW_TEXT_LENGTH = 50_000
    # Maximum characters for execution log output
    MAX_EXECUTION_LOG_LENGTH = 10_000

    def process_file_dry_run(self, file_path: str, folder_name: str, administration: str = None) -> dict:
        """Execute full pipeline in dry-run mode with timing and log capture.

        Processes a file through all pipeline stages (file parsing, text extraction,
        AI/CSV extraction, transaction formatting, transaction preparation) without
        writing to the database or uploading to external storage.

        Args:
            file_path: Path to the uploaded file to process.
            folder_name: Vendor/folder name for pipeline context.
            administration: Optional tenant identifier for vendor history lookup.

        Returns:
            dict with keys: pipeline_result, performance, ai_usage_preview,
            execution_log, errors.
        """
        errors = []
        pipeline_result = {}
        performance = {
            'total_duration_ms': 0,
            'ai_duration_ms': None,
            'ai_model': None,
            'ai_tokens': None,
        }
        ai_usage_preview = None
        execution_log = ""

        # Validate registry availability upfront (same chain as AIExtractor)
        try:
            resolver.resolve_profile("structured_extraction")
        except RegistryError as e:
            errors.append({
                'stage': 'registry_resolution',
                'error_type': 'RegistryError',
                'message': f'Could not load structured_extraction profile: {e}',
            })
            # Return immediately — cannot proceed without model configuration
            return {
                'pipeline_result': pipeline_result,
                'performance': performance,
                'ai_usage_preview': ai_usage_preview,
                'execution_log': execution_log,
                'errors': errors,
            }

        # Patch processor to capture AI result metadata for metrics
        self.processor._last_ai_result = None
        original_extract_with_ai = self.processor._extract_with_ai

        def _capturing_extract_with_ai(lines, folder_name_arg):
            result = original_extract_with_ai(lines, folder_name_arg)
            self.processor._last_ai_result = result
            return result

        self.processor._extract_with_ai = _capturing_extract_with_ai

        try:
            # Capture all stdout from pipeline components
            stdout_buffer = io.StringIO()
            start_time = time.time()

            # folder_name is always included regardless of pipeline success/failure
            pipeline_result['folder_name'] = folder_name

            with contextlib.redirect_stdout(stdout_buffer):
                # --- Stage 1: File parsing ---
                file_data = None
                try:
                    # Mock drive result for dry-run (no actual upload)
                    mock_drive_result = {
                        'id': os.path.basename(file_path),
                        'url': f'dry-run://{os.path.basename(file_path)}',
                    }
                    file_data = self.processor.process_file(
                        file_path, mock_drive_result, folder_name
                    )
                    # Extract raw text and apply truncation
                    raw_text = file_data.get('txt', '')
                    raw_text_truncated = len(raw_text) > self.MAX_RAW_TEXT_LENGTH
                    if raw_text_truncated:
                        raw_text = raw_text[:self.MAX_RAW_TEXT_LENGTH]

                    pipeline_result['raw_text'] = raw_text
                    pipeline_result['raw_text_truncated'] = raw_text_truncated
                except Exception as e:
                    errors.append({
                        'stage': 'file_parsing',
                        'error_type': type(e).__name__,
                        'message': str(e),
                        'stack_trace': self._format_stack_trace(e, max_frames=50),
                    })
                    # Cannot continue without parsed file
                    total_duration_ms = int((time.time() - start_time) * 1000)
                    performance['total_duration_ms'] = total_duration_ms
                    execution_log = self._truncate_log(stdout_buffer.getvalue())
                    return {
                        'pipeline_result': pipeline_result,
                        'performance': performance,
                        'ai_usage_preview': ai_usage_preview,
                        'execution_log': execution_log,
                        'errors': errors,
                    }

                # --- Stage 2: Transaction extraction (AI or CSV) ---
                transactions = []
                extraction_result = None
                try:
                    ai_start_time = time.time()
                    transactions = self.processor.extract_transactions(file_data)
                    ai_end_time = time.time()

                    # Determine parser used
                    parser_used = self._determine_parser_used(transactions, file_data)
                    pipeline_result['parser_used'] = parser_used

                    # Extract AI metrics from the file_data's ai_data or from captured result
                    ai_usage_meta = self._extract_ai_usage_meta(file_data, transactions)

                    if parser_used == 'ai' or parser_used == 'ai_failed':
                        ai_duration_ms = int((ai_end_time - ai_start_time) * 1000)
                        performance['ai_duration_ms'] = ai_duration_ms
                        performance['ai_model'] = ai_usage_meta.get('model') or None
                        if ai_usage_meta.get('total_tokens', 0) > 0 or ai_usage_meta.get('model'):
                            performance['ai_tokens'] = {
                                'prompt_tokens': ai_usage_meta.get('prompt_tokens', 0),
                                'completion_tokens': ai_usage_meta.get('completion_tokens', 0),
                                'total_tokens': ai_usage_meta.get('total_tokens', 0),
                            }
                        else:
                            performance['ai_tokens'] = {
                                'prompt_tokens': 0,
                                'completion_tokens': 0,
                                'total_tokens': 0,
                            }
                    # For csv_rule, AI metrics stay as None (omitted)

                    # Build extraction result with all 5 required fields
                    extraction_result = self._build_extraction_result(
                        file_data, transactions, parser_used
                    )
                    pipeline_result['extraction_result'] = extraction_result
                    pipeline_result['formatted_transactions'] = transactions

                except Exception as e:
                    errors.append({
                        'stage': 'transaction_formatting',
                        'error_type': type(e).__name__,
                        'message': str(e),
                        'stack_trace': self._format_stack_trace(e, max_frames=50),
                    })
                    pipeline_result['extraction_result'] = None
                    pipeline_result['formatted_transactions'] = []
                    pipeline_result['parser_used'] = 'ai_failed'

                # --- Stage 3: Transaction preparation ---
                try:
                    if transactions:
                        prepared = self._prepare_transactions_dry_run(
                            transactions, folder_name, administration, file_data
                        )
                        pipeline_result['prepared_transactions'] = prepared
                    else:
                        pipeline_result['prepared_transactions'] = []
                except Exception as e:
                    errors.append({
                        'stage': 'transaction_preparation',
                        'error_type': type(e).__name__,
                        'message': str(e),
                        'stack_trace': self._format_stack_trace(e, max_frames=50),
                    })
                    pipeline_result['prepared_transactions'] = []

            # End of stdout capture — compute final metrics
            total_duration_ms = int((time.time() - start_time) * 1000)
            performance['total_duration_ms'] = total_duration_ms
            execution_log = self._truncate_log(stdout_buffer.getvalue())

            # Build AI usage preview if AI was used
            if performance.get('ai_model') or (performance.get('ai_tokens') and
                    performance['ai_tokens'].get('total_tokens', 0) > 0):
                ai_usage_preview = self._build_ai_usage_preview(
                    administration, folder_name, performance
                )

            # Include the prompt template used (without text content to save space)
            prompt_used = self._get_prompt_template()

            return {
                'pipeline_result': pipeline_result,
                'performance': performance,
                'ai_usage_preview': ai_usage_preview,
                'execution_log': execution_log,
                'errors': errors,
                'prompt_used': prompt_used,
            }

        finally:
            # Restore original method
            self.processor._extract_with_ai = original_extract_with_ai
            # Always cleanup temp file
            if os.path.exists(file_path):
                os.remove(file_path)

    def _determine_parser_used(self, transactions, file_data):
        """Determine which parser was used based on extraction outcome.

        Returns one of: "ai", "csv_rule", or "ai_failed".
        """
        if not transactions:
            return 'ai_failed'

        first_tx = transactions[0] if transactions else {}
        if isinstance(first_tx, dict) and first_tx.get('parser_used_hint') == 'csv_rule':
            return 'csv_rule'

        # Image AI data means AI was used
        if 'ai_data' in file_data:
            return 'ai'

        # Check if extraction produced a valid amount
        amount = first_tx.get('amount', 0) if isinstance(first_tx, dict) else 0
        try:
            if float(amount) > 0:
                return 'ai'
        except (ValueError, TypeError):
            pass

        return 'ai_failed'

    def _extract_ai_usage_meta(self, file_data, transactions):
        """Extract AI usage metadata (_usage) from file_data or processor state.

        AI extraction stores a _usage dict with model, prompt_tokens,
        completion_tokens, and total_tokens on the ai_data result.
        """
        # Check ai_data first (image processing path)
        ai_data = file_data.get('ai_data', {})
        if isinstance(ai_data, dict) and '_usage' in ai_data:
            return ai_data['_usage']

        # For PDF/EML paths, the _usage is on the ai_result returned from
        # _extract_with_ai, which is not directly exposed. We can check if
        # the processor stored it. Since PDFProcessor doesn't expose _usage
        # directly to extract_transactions callers, we need to inspect
        # the last ai_result. The processor's _extract_with_ai returns it in
        # the ai_result dict with _usage key — but that gets consumed
        # internally by _format_vendor_transactions and lost.
        #
        # Workaround: we can access it via processor's internal state if it
        # stores it, or re-read from the AIExtractor. For now, check if any
        # transaction has hints or if file_data was enriched.
        #
        # Best approach: check processor._last_ai_result if available
        if hasattr(self.processor, '_last_ai_result'):
            last_result = self.processor._last_ai_result
            if isinstance(last_result, dict) and '_usage' in last_result:
                return last_result['_usage']

        return {}

    def _build_extraction_result(self, file_data, transactions, parser_used):
        """Build extraction result dict with all 5 required fields.

        Ensures date, total_amount, vat_amount, description, and vendor are
        always present (empty string / 0.0 defaults for missing values).
        """
        # Try to reconstruct from ai_data (image path)
        ai_data = file_data.get('ai_data')
        if ai_data and isinstance(ai_data, dict):
            return {
                'date': ai_data.get('date', ''),
                'total_amount': ai_data.get('total_amount', 0.0),
                'vat_amount': ai_data.get('vat_amount', 0.0),
                'description': ai_data.get('description', ''),
                'vendor': ai_data.get('vendor', ''),
            }

        # Reconstruct from formatted transactions
        if transactions:
            first_tx = transactions[0] if isinstance(transactions[0], dict) else {}
            total_amount = first_tx.get('amount', 0.0)
            vat_amount = 0.0
            # Second transaction is typically VAT
            if len(transactions) > 1:
                second_tx = transactions[1]
                if isinstance(second_tx, dict):
                    desc = second_tx.get('description', '')
                    if 'VAT' in (desc or '').upper() or 'BTW' in (desc or '').upper():
                        vat_amount = second_tx.get('amount', 0.0)

            return {
                'date': first_tx.get('date', ''),
                'total_amount': total_amount,
                'vat_amount': vat_amount,
                'description': first_tx.get('description', ''),
                'vendor': file_data.get('folder', '').split('/')[-1] if file_data.get('folder') else '',
            }

        # No data available
        return {
            'date': '',
            'total_amount': 0.0,
            'vat_amount': 0.0,
            'description': '',
            'vendor': '',
        }

    def _prepare_transactions_dry_run(self, transactions, folder_name, administration, file_data):
        """Prepare transactions using TransactionLogic in read-only mode.

        Gets previous transactions for the vendor and prepares new transaction
        records without saving to the database.
        """
        from transaction_logic import TransactionLogic

        tl = TransactionLogic(test_mode=False)  # Read-only access to production DB for vendor history
        previous_transactions = tl.get_last_transactions(folder_name, administration)

        # Handle error result from get_last_transactions
        if isinstance(previous_transactions, dict) and previous_transactions.get('error'):
            print(f"Transaction template error: {previous_transactions.get('message', 'Unknown')}")
            return []

        if not previous_transactions:
            return []

        # Build vendor_data from extracted transactions
        vendor_data = {}
        if transactions:
            first_tx = transactions[0] if isinstance(transactions[0], dict) else {}
            vendor_data = {
                'date': first_tx.get('date'),
                'total_amount': first_tx.get('amount', 0),
                'description': first_tx.get('description', ''),
            }
            # Get VAT from second transaction if present
            if len(transactions) > 1:
                second_tx = transactions[1]
                if isinstance(second_tx, dict):
                    desc = second_tx.get('description', '')
                    if 'VAT' in (desc or '').upper() or 'BTW' in (desc or '').upper():
                        vendor_data['vat_amount'] = second_tx.get('amount', 0)

        # Build new_data for prepare_new_transactions
        new_data = {
            'folder_name': folder_name,
            'description': vendor_data.get('description', f'Dry-run test for {folder_name}'),
            'amount': vendor_data.get('total_amount', 0),
            'drive_url': file_data.get('url', 'dry-run://test'),
            'filename': file_data.get('name', 'test-file'),
            'vendor_data': vendor_data,
            'administration': administration or 'test-tool-dry-run',
        }

        prepared = tl.prepare_new_transactions(previous_transactions, new_data)
        print(f"Prepared {len(prepared)} transaction records (dry-run)")
        return prepared

    def _build_ai_usage_preview(self, administration, folder_name, performance):
        """Build AI usage preview showing what would be logged.

        Computes cost estimate using the same formula as AIUsageTracker.
        """
        from services.ai_usage_tracker import AIUsageTracker

        model = performance.get('ai_model', '') or ''
        tokens = performance.get('ai_tokens', {}) or {}
        total_tokens = tokens.get('total_tokens', 0)

        # Get rate from MODEL_PRICING
        rate_per_million = AIUsageTracker.MODEL_PRICING.get(
            model, AIUsageTracker.MODEL_PRICING.get('default', 0.5)
        )

        # Calculate cost: (tokens / 1,000,000) × rate_per_million, rounded to 6 places
        if total_tokens > 0:
            cost = Decimal(total_tokens) / Decimal(1_000_000) * Decimal(str(rate_per_million))
            cost = cost.quantize(Decimal('0.000001'))
        else:
            cost = Decimal('0.000000')

        return {
            'administration': administration or 'test-tool-dry-run',
            'feature': f'invoice_extraction_{folder_name}',
            'tokens_used': total_tokens,
            'cost_estimate': str(cost),
            'cost_breakdown': {
                'model': model,
                'rate_per_million': rate_per_million,
                'total_tokens': total_tokens,
                'formula': f'({total_tokens} / 1000000) * {rate_per_million}',
            },
        }

    def _truncate_log(self, log_text: str) -> str:
        """Truncate execution log to the most recent MAX_EXECUTION_LOG_LENGTH characters."""
        if len(log_text) <= self.MAX_EXECUTION_LOG_LENGTH:
            return log_text
        # Keep the most recent characters
        return log_text[-self.MAX_EXECUTION_LOG_LENGTH:]

    def _get_prompt_template(self) -> str:
        """Return the AI extraction prompt template (without text content)."""
        from services.invoice_test_ai_rerun import get_prompt_template
        return get_prompt_template()

    def rerun_with_custom_prompt(self, text_content: str, custom_prompt: str, vendor_hint: str = None) -> dict:
        """Re-run AI extraction with a custom prompt against already-extracted text.

        Delegates to invoice_test_ai_rerun module.
        """
        from services.invoice_test_ai_rerun import rerun_with_custom_prompt as _rerun
        return _rerun(text_content, custom_prompt, vendor_hint,
                      call_ai_fn=self._call_ai_with_custom_prompt)

    def _call_ai_with_custom_prompt(self, ai, text_content: str, custom_prompt: str, vendor_hint: str = None) -> dict:
        """Call OpenRouter API with a custom prompt. Delegates to module function."""
        from services.invoice_test_ai_rerun import _call_ai_with_custom_prompt
        return _call_ai_with_custom_prompt(ai, text_content, custom_prompt, vendor_hint)

    def get_vendor_history(self, folder_name: str, administration: str = None) -> list:
        """Retrieve previous transactions for a vendor (read-only).

        Delegates to invoice_test_ai_rerun module.
        """
        from services.invoice_test_ai_rerun import get_vendor_history
        return get_vendor_history(folder_name, administration)

    @staticmethod
    def _capture_stdout(func, *args, **kwargs):
        """Execute a function while capturing its stdout output.

        Uses io.StringIO + contextlib.redirect_stdout to capture any print()
        statements emitted by pipeline components during execution.

        Args:
            func: The callable to execute.
            *args: Positional arguments to pass to func.
            **kwargs: Keyword arguments to pass to func.

        Returns:
            tuple of (func_result, captured_output_string).
        """
        stdout_buffer = io.StringIO()
        with contextlib.redirect_stdout(stdout_buffer):
            result = func(*args, **kwargs)
        return result, stdout_buffer.getvalue()

    @staticmethod
    def _format_stack_trace(e: Exception, max_frames: int = 50) -> str:
        """Format an exception's stack trace, limited to max_frames.

        Extracts the traceback from the exception and formats it as a string,
        keeping only the most recent max_frames frames to prevent excessively
        long traces from cluttering diagnostics.

        Args:
            e: The exception to format.
            max_frames: Maximum number of stack frames to include (default 50).

        Returns:
            Formatted stack trace string limited to max_frames.
        """
        # Use traceback.extract_tb to get structured frame data, then limit
        tb = traceback.extract_tb(e.__traceback__)
        limited_tb = tb[-max_frames:] if len(tb) > max_frames else tb

        # Format the limited traceback
        lines = ["Traceback (most recent call last):\n"]
        lines.extend(traceback.format_list(limited_tb))
        lines.extend(traceback.format_exception_only(type(e), e))

        return "".join(lines)
