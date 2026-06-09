# Design Document: Invoice Processing Test Tool

## Overview

The Invoice Processing Test Tool is a diagnostic interface that allows System Administrators to test the existing invoice processing pipeline in **dry-run mode**. It reuses the existing `PDFProcessor`, `AIExtractor`, `CsvRuleEngine`, and `TransactionLogic` components but wraps them in a side-effect-free execution context — no database writes, no Google Drive/S3 uploads.

The tool provides full pipeline transparency: raw extracted text, AI/CSV extraction results, formatted transactions, prepared transactions, performance metrics, AI usage preview, and pipeline execution logs. It also supports custom prompt re-runs for testing AI prompt improvements.

### Design Decisions

1. **Wrap, don't fork**: `InvoiceTestService` delegates to existing pipeline components rather than duplicating logic. This ensures the test tool always reflects actual pipeline behavior.
2. **Stdout capture**: Pipeline components use `print()` for diagnostics. The test service captures stdout during execution using `io.StringIO` + `contextlib.redirect_stdout`.
3. **No tenant isolation needed**: The test tool is SysAdmin-only and reads vendor history across all tenants via an explicit `administration` parameter (for previous transaction lookup). It never writes data.
4. **Stateless API**: Each request is self-contained — file upload + processing in a single request/response cycle. No server-side session state.

## Architecture

```mermaid
graph TD
    subgraph Frontend
        A[SysAdminDashboard] --> B[InvoiceTestTool Tab]
        B --> C[FileUpload + VendorInput]
        B --> D[PipelineResults Display]
        B --> E[CustomPrompt Editor]
    end

    subgraph Backend
        F[sysadmin_test_tool_bp] --> G[InvoiceTestService]
        G --> H[PDFProcessor.process_file]
        G --> I[PDFProcessor.extract_transactions]
        G --> J[TransactionLogic.get_last_transactions]
        G --> K[TransactionLogic.prepare_new_transactions]
        G --> L[AIExtractor.extract_invoice_data]
    end

    C -->|POST /api/sysadmin/test-tool/process| F
    E -->|POST /api/sysadmin/test-tool/rerun-prompt| F
    F -->|@cognito_required SysAdmin| G
```

### Integration with Existing Architecture

- **Blueprint registration**: `sysadmin_test_tool_bp` registers under the existing `sysadmin_bp` at `/api/sysadmin/test-tool/`
- **Auth**: Uses `@cognito_required(required_roles=['SysAdmin'])` — same pattern as `sysadmin_health_bp`
- **No `@tenant_required()`**: The test tool is tenant-agnostic (SysAdmin operates across tenants). The vendor history lookup accepts an optional `administration` parameter.
- **Temp file cleanup**: Uses `try/finally` to guarantee cleanup regardless of success or failure

## Components and Interfaces

### Backend Components

#### 1. `sysadmin_test_tool_bp` (Blueprint)

**File**: `backend/src/routes/sysadmin_test_tool.py`

Registered under `/api/sysadmin/test-tool/` via:

```python
sysadmin_bp.register_blueprint(sysadmin_test_tool_bp, url_prefix='/test-tool')
```

**Endpoints**:

| Method | Path                                     | Description                             |
| ------ | ---------------------------------------- | --------------------------------------- |
| POST   | `/api/sysadmin/test-tool/process`        | Upload and process file in dry-run mode |
| POST   | `/api/sysadmin/test-tool/rerun-prompt`   | Re-run AI extraction with custom prompt |
| GET    | `/api/sysadmin/test-tool/vendor-history` | Get previous transactions for a vendor  |

#### 2. `InvoiceTestService` (Service)

**File**: `backend/src/services/invoice_test_service.py`

Orchestrates pipeline execution in dry-run mode with stdout capture, timing, and error collection.

```python
class InvoiceTestService:
    def __init__(self):
        self.processor = PDFProcessor(test_mode=True)
        self.csv_rule_engine = CsvRuleEngine()

    def process_file_dry_run(self, file_path: str, folder_name: str, administration: str = None) -> dict:
        """Execute full pipeline in dry-run mode with timing and log capture."""
        ...

    def rerun_with_custom_prompt(self, text_content: str, custom_prompt: str, vendor_hint: str = None) -> dict:
        """Re-run AI extraction with a custom prompt against already-extracted text."""
        ...

    def get_vendor_history(self, folder_name: str, administration: str = None) -> list:
        """Retrieve previous transactions for a vendor (read-only)."""
        ...
```

### API Endpoint Contracts

#### POST `/api/sysadmin/test-tool/process`

**Request**: `multipart/form-data`

| Field            | Type   | Required | Constraints                                                                   |
| ---------------- | ------ | -------- | ----------------------------------------------------------------------------- |
| `file`           | File   | Yes      | PDF/JPG/JPEG/PNG/CSV/EML/MHTML, max 20 MB                                     |
| `folderName`     | string | No       | Alphanumeric + hyphens + underscores, max 100 chars. Defaults to "TestVendor" |
| `administration` | string | No       | Tenant identifier for vendor history lookup                                   |

**Response**: `200 OK`

```json
{
  "success": true,
  "pipeline_result": {
    "raw_text": "extracted text content...",
    "raw_text_truncated": false,
    "extraction_result": {
      "date": "2024-01-15",
      "total_amount": 150.00,
      "vat_amount": 31.50,
      "description": "Invoice #12345",
      "vendor": "SomeVendor"
    },
    "formatted_transactions": [...],
    "prepared_transactions": [...],
    "parser_used": "ai",
    "folder_name": "SomeVendor"
  },
  "performance": {
    "total_duration_ms": 3450,
    "ai_duration_ms": 2800,
    "ai_model": "deepseek/deepseek-chat",
    "ai_tokens": {
      "prompt_tokens": 420,
      "completion_tokens": 85,
      "total_tokens": 505
    }
  },
  "ai_usage_preview": {
    "administration": "TestAdmin",
    "feature": "invoice_extraction_SomeVendor",
    "tokens_used": 505,
    "cost_estimate": "0.000346",
    "cost_breakdown": {
      "model": "deepseek/deepseek-chat",
      "rate_per_million": 0.685,
      "total_tokens": 505,
      "formula": "(505 / 1000000) * 0.685"
    }
  },
  "execution_log": "Starting file processing...\nAI extraction for SomeVendor...\n...",
  "errors": []
}
```

**Error Responses**:

| Status | Condition                                                               |
| ------ | ----------------------------------------------------------------------- |
| 400    | No file provided, unsupported file type, empty file, invalid folderName |
| 401    | Unauthenticated                                                         |
| 403    | Non-SysAdmin user                                                       |
| 500    | Unexpected server error                                                 |

#### POST `/api/sysadmin/test-tool/rerun-prompt`

**Request**: `application/json`

```json
{
  "text_content": "the raw extracted text from a previous process call",
  "custom_prompt": "Modified extraction prompt text...",
  "vendor_hint": "SomeVendor"
}
```

| Field           | Type   | Required | Constraints                          |
| --------------- | ------ | -------- | ------------------------------------ |
| `text_content`  | string | Yes      | The extracted text to run AI against |
| `custom_prompt` | string | Yes      | 1–10,000 characters                  |
| `vendor_hint`   | string | No       | Vendor name for context              |

**Response**: `200 OK`

```json
{
  "success": true,
  "extraction_result": {
    "date": "2024-01-15",
    "total_amount": 150.0,
    "vat_amount": 31.5,
    "description": "Invoice #12345",
    "vendor": "SomeVendor"
  },
  "performance": {
    "ai_duration_ms": 2100,
    "ai_model": "deepseek/deepseek-chat",
    "ai_tokens": {
      "prompt_tokens": 380,
      "completion_tokens": 90,
      "total_tokens": 470
    }
  },
  "ai_usage_preview": {
    "administration": "test-tool-rerun",
    "feature": "invoice_extraction_rerun",
    "tokens_used": 470,
    "cost_estimate": "0.000322",
    "cost_breakdown": {
      "model": "deepseek/deepseek-chat",
      "rate_per_million": 0.685,
      "total_tokens": 470,
      "formula": "(470 / 1000000) * 0.685"
    }
  },
  "errors": []
}
```

#### GET `/api/sysadmin/test-tool/vendor-history`

**Query Parameters**:

| Param            | Type   | Required | Description        |
| ---------------- | ------ | -------- | ------------------ |
| `folderName`     | string | Yes      | Vendor/folder name |
| `administration` | string | No       | Tenant filter      |

**Response**: `200 OK`

```json
{
  "success": true,
  "vendor_name": "SomeVendor",
  "transactions": [
    {
      "date": "2024-01-10",
      "amount": 125.5,
      "description": "Invoice #12300"
    }
  ],
  "count": 1
}
```

### Frontend Components

#### `InvoiceTestTool` (Tab Component)

**File**: `frontend/src/components/SysAdmin/InvoiceTestTool.tsx`

Top-level component containing the file upload form, vendor configuration, and results display.

**Sub-components**:

| Component              | File                                | Responsibility                                                         |
| ---------------------- | ----------------------------------- | ---------------------------------------------------------------------- |
| `TestToolUploadForm`   | `InvoiceTestTool.tsx` (inline)      | File input, vendor name, administration, submit button                 |
| `PipelineResultsPanel` | `PipelineResultsPanel.tsx`          | Renders all pipeline stage outputs in sequential order                 |
| `CustomPromptEditor`   | `CustomPromptEditor.tsx`            | Textarea with original/modified prompt, re-run button, comparison view |
| `PerformanceMetrics`   | `PipelineResultsPanel.tsx` (inline) | Timing, model, token counts                                            |
| `AIUsagePreview`       | `PipelineResultsPanel.tsx` (inline) | Usage log entry preview and cost breakdown                             |
| `ExecutionLog`         | `PipelineResultsPanel.tsx` (inline) | Collapsible stdout capture display                                     |
| `VendorHistoryPanel`   | `VendorHistoryPanel.tsx`            | Read-only list of previous transactions                                |
| `ErrorDisplay`         | `PipelineResultsPanel.tsx` (inline) | Stage-by-stage error details with stack traces                         |

**State Flow**:

```
Upload File → Loading State → Display Results → (Optional) Edit Prompt → Re-run → Show Comparison
```

## Data Models

### Pipeline Result (Backend → Frontend)

```typescript
interface PipelineResult {
  raw_text: string;
  raw_text_truncated: boolean;
  extraction_result: ExtractionResult | null;
  formatted_transactions: Transaction[];
  prepared_transactions: PreparedTransaction[];
  parser_used: "ai" | "csv_rule" | "ai_failed";
  folder_name: string;
}

interface ExtractionResult {
  date: string;
  total_amount: number;
  vat_amount: number;
  description: string;
  vendor: string;
}

interface Transaction {
  date: string;
  amount: number;
  description: string;
  debet?: string;
  credit?: string;
  parser_used_hint?: string;
}

interface PreparedTransaction {
  ID: string;
  TransactionNumber: string;
  TransactionDate: string;
  TransactionDescription: string;
  TransactionAmount: number;
  Debet: string;
  Credit: string;
  ReferenceNumber: string;
  Ref1: string | null;
  Ref2: string | null;
  Ref3: string;
  Ref4: string;
  Administration: string;
}
```

### Performance Metrics

```typescript
interface PerformanceMetrics {
  total_duration_ms: number;
  ai_duration_ms: number | null; // null if CSV rule used
  ai_model: string | null; // null if CSV rule used
  ai_tokens: TokenUsage | null; // null if CSV rule used
}

interface TokenUsage {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
}
```

### AI Usage Preview

```typescript
interface AIUsagePreview {
  administration: string;
  feature: string;
  tokens_used: number;
  cost_estimate: string; // decimal string to 6 places
  cost_breakdown: {
    model: string;
    rate_per_million: number;
    total_tokens: number;
    formula: string;
  };
}
```

### Error Detail

```typescript
interface PipelineError {
  stage:
    | "file_parsing"
    | "text_extraction"
    | "ai_extraction"
    | "csv_rule"
    | "transaction_formatting"
    | "transaction_preparation";
  error_type: string;
  message: string;
  stack_trace?: string; // max 50 frames
  model_failures?: ModelFailure[]; // for AI extraction failures
  csv_rule_details?: CsvRuleDebug; // for CSV rule failures
}

interface ModelFailure {
  model: string;
  failure_reason: "timeout" | "api_error" | "invalid_response";
  details: string;
}

interface CsvRuleDebug {
  rules_evaluated: string[];
  pattern_matched: boolean;
  failure_reason: string;
}
```

## Correctness Properties

_A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees._

### Property 1: File extension validation

_For any_ filename string, the file validation function SHALL accept it if and only if it has an extension in {pdf, jpg, jpeg, png, csv, eml, mhtml} (case-insensitive), and reject all other extensions.

**Validates: Requirements 2.1, 2.5**

### Property 2: Dry-run produces no side effects

_For any_ valid file upload processed through the test tool pipeline, the system SHALL make zero database write calls (INSERT, UPDATE, DELETE), zero Google Drive upload calls, and zero S3 upload calls.

**Validates: Requirements 2.2, 2.3, 5.4**

### Property 3: Temporary file cleanup

_For any_ file processed through the test tool (whether the pipeline succeeds or fails at any stage), all temporary files created during processing SHALL be removed after the request completes.

**Validates: Requirements 2.6**

### Property 4: Raw text truncation invariant

_For any_ extracted text output, if the text length exceeds 50,000 characters then the returned text SHALL be exactly 50,000 characters with `raw_text_truncated` set to true; if the text length is ≤ 50,000 characters then the full text SHALL be returned with `raw_text_truncated` set to false.

**Validates: Requirements 3.1**

### Property 5: Extraction result field completeness

_For any_ successful extraction (AI or CSV rule), the extraction result SHALL contain all five fields (date, total_amount, vat_amount, description, vendor) as explicitly present keys, with missing values represented as empty string or 0.0 rather than omitted keys.

**Validates: Requirements 3.2, 3.3**

### Property 6: Parser used is a valid enum value

_For any_ pipeline execution result, the `parser_used` field SHALL be exactly one of: "ai", "csv_rule", or "ai_failed".

**Validates: Requirements 3.6**

### Property 7: AI metrics conditional on parser used

_For any_ pipeline execution result, if `parser_used` is "ai" then `ai_duration_ms` SHALL be a non-negative integer, `ai_model` SHALL be a non-empty string, and `ai_tokens` SHALL contain non-negative integers for prompt_tokens, completion_tokens, and total_tokens. If `parser_used` is "csv_rule" then `ai_duration_ms`, `ai_model`, and `ai_tokens` SHALL all be null.

**Validates: Requirements 4.2, 4.3, 4.4, 4.6**

### Property 8: Cost calculation correctness

_For any_ AI extraction result with token usage data, the `cost_estimate` SHALL equal `(total_tokens / 1,000,000) × rate_per_million` rounded to 6 decimal places, where `rate_per_million` is the pricing rate for the model used (from the MODEL_PRICING lookup table).

**Validates: Requirements 5.1, 5.2, 5.3**

### Property 9: Prompt length validation

_For any_ custom prompt string submitted to the re-run endpoint, if the length is between 1 and 10,000 characters (inclusive) then the request SHALL be processed (returning either a successful extraction or an AI failure result). If the length is 0 or exceeds 10,000 characters, the request SHALL be rejected with a 400 status code.

**Validates: Requirements 6.3, 6.4**

### Property 10: Vendor name validation

_For any_ input string for the vendor/folder name field, the system SHALL accept it if and only if it matches `^[a-zA-Z0-9_-]{1,100}$` (alphanumeric, hyphens, underscores, 1–100 characters).

**Validates: Requirements 7.1**

### Property 11: Vendor history count limit

_For any_ vendor name query, the returned transaction list SHALL contain at most 20 items.

**Validates: Requirements 7.3**

### Property 12: Partial result preservation on failure

_For any_ pipeline execution that fails at stage N, all successfully completed stages prior to N SHALL have their outputs present in the response (non-null, correctly populated).

**Validates: Requirements 8.4**

### Property 13: Execution log truncation

_For any_ pipeline execution producing stdout output, the `execution_log` field SHALL contain at most 10,000 characters. If the actual log exceeds 10,000 characters, it SHALL be truncated to the most recent 10,000 characters.

**Validates: Requirements 8.5**

## Error Handling

### Strategy

The test tool uses a **stage-by-stage error collection** approach. Each pipeline stage runs in its own try/except block, and errors are accumulated rather than causing early termination. This ensures maximum diagnostic value.

### Error Collection Pattern

```python
errors = []
result = {}

# Stage 1: File parsing
try:
    file_data = self.processor.process_file(file_path, mock_drive_result, folder_name)
    result['raw_text'] = file_data['txt']
except Exception as e:
    errors.append({
        'stage': 'file_parsing',
        'error_type': type(e).__name__,
        'message': str(e),
        'stack_trace': self._format_stack_trace(e, max_frames=50)
    })
    # Return partial result — can't continue without parsed file
    return {'pipeline_result': result, 'errors': errors, ...}

# Stage 2: Transaction extraction (continues even if AI fails)
try:
    transactions = self.processor.extract_transactions(file_data)
    result['formatted_transactions'] = transactions
except Exception as e:
    errors.append({...})
    result['formatted_transactions'] = []

# Stage 3: Transaction preparation (optional, depends on vendor history)
try:
    prepared = self._prepare_transactions(...)
    result['prepared_transactions'] = prepared
except Exception as e:
    errors.append({...})
    result['prepared_transactions'] = []
```

### AI Extraction Error Details

When AI extraction fails, the error includes per-model failure details:

```python
{
    'stage': 'ai_extraction',
    'error_type': 'AllModelsExhausted',
    'message': 'All 6 AI models failed to extract invoice data',
    'model_failures': [
        {'model': 'deepseek/deepseek-chat', 'failure_reason': 'timeout', 'details': 'No response within 10s'},
        {'model': 'meta-llama/llama-3.2-3b-instruct:free', 'failure_reason': 'api_error', 'details': 'HTTP 429'},
        ...
    ]
}
```

### Timeout Handling

- AI model timeout: 10 seconds per model (existing behavior in `AIExtractor`)
- Total pipeline timeout: Not enforced at service level (HTTP server timeout applies)
- Custom prompt re-run: Same 10-second timeout per model attempt

### File Cleanup

Temp file cleanup is guaranteed via `try/finally`:

```python
def process_file_dry_run(self, file_path, folder_name, administration=None):
    try:
        # ... pipeline execution ...
        return result
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)
```

## Testing Strategy

### Property-Based Testing (Hypothesis)

The project uses **Hypothesis** (Python) for backend property-based testing and **fast-check** (@fast-check/vitest) for frontend.

**Backend PBT Configuration**:

- Library: `hypothesis` (already in project dependencies)
- Minimum iterations: 100 per property (`@settings(max_examples=100)`)
- Each test tagged with property reference comment

**Frontend PBT Configuration**:

- Library: `@fast-check/vitest` (already in project dependencies)
- Minimum iterations: 100 per property (`{ numRuns: 100 }`)

### Test Categories

| Category                  | Framework           | Focus                                                  |
| ------------------------- | ------------------- | ------------------------------------------------------ |
| Property tests (backend)  | pytest + hypothesis | Properties 1–13 (pure logic validation)                |
| Property tests (frontend) | vitest + fast-check | Properties 4, 9, 10 (client-side validation)           |
| Unit tests (backend)      | pytest              | Service methods, error paths, mock AI responses        |
| Unit tests (frontend)     | vitest + RTL        | Component rendering, state transitions, loading states |
| Integration tests         | pytest              | Full endpoint tests with mocked AI/DB                  |

### Property Test Implementation Notes

- **Property 2 (no side effects)**: Use `unittest.mock.patch` on `DatabaseManager.execute_query`, `GoogleDriveService.upload_file`, and S3 storage methods. Verify zero calls with `fetch=False` (write) parameter.
- **Property 8 (cost calculation)**: Use Hypothesis to generate random `(tokens, model)` pairs and verify the formula against `AIUsageTracker._calculate_cost`.
- **Property 12 (partial results)**: Use Hypothesis to select a random stage to fail (via patching), then verify all prior stage outputs are non-null.

### Test File Structure

```
backend/tests/unit/test_invoice_test_service.py       # Service unit tests
backend/tests/unit/test_invoice_test_tool_props.py    # Property-based tests
backend/tests/api/test_sysadmin_test_tool.py          # API integration tests
frontend/src/components/SysAdmin/__tests__/InvoiceTestTool.test.tsx
frontend/src/components/SysAdmin/__tests__/InvoiceTestTool.prop.test.tsx
```
