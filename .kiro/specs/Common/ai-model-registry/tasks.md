# Implementation Plan: AI Model Registry

## Overview

Implement a centralized AI model registry module (`backend/src/services/ai_model_registry.py`) that replaces hardcoded model fallback chains across five consumer modules. The registry defines model entries, task profiles with ordered fallback chains, per-profile overrides, and a ProfileResolver. After the registry is built and validated, each AI consumer is refactored to use the resolver exclusively.

## Tasks

- [x] 1. Create core registry module with data models and validation
  - [x] 1.1 Create `backend/src/services/ai_model_registry.py` with ModelEntry, ModelOverride, TaskProfile, ResolvedModel dataclasses, RegistryError exception, and validation functions
    - Define `ModelEntry` frozen dataclass with fields: model_id (str), cost_tier (Literal["free","cheap","paid"]), max_tokens (int 1–16384), default_timeout (int 1–300), supports_vision (bool)
    - Define `ModelOverride` frozen dataclass with optional timeout (1–600) and max_tokens (1–16384)
    - Define `TaskProfile` frozen dataclass with name, fallback_chain (tuple of model_id strings), and overrides dict
    - Define `ResolvedModel` frozen dataclass with model_id, timeout, max_tokens, cost_tier, supports_vision
    - Define `RegistryError(Exception)` class
    - Implement `_validate_model_entry()` raising RegistryError for invalid attributes
    - Implement `_validate_profile()` raising RegistryError for: empty/oversized chain, unknown model refs, duplicates in chain, orphaned overrides, override values out of range
    - _Requirements: 1.1, 1.2, 2.1, 2.3, 2.4, 2.5, 2.6, 4.3, 4.4, 4.5_

  - [x] 1.2 Implement ProfileResolver class with resolve_profile, list_models, list_profiles, and get_profile_detail methods
    - `resolve_profile(profile_name)` returns ordered list of ResolvedModel with merged defaults/overrides
    - Raise RegistryError with available profiles list when profile_name is unknown
    - `list_models()` returns all registered ModelEntry instances
    - `list_profiles()` returns all profile name strings
    - `get_profile_detail(profile_name)` returns detailed info with override indicators
    - _Requirements: 3.1, 3.2, 3.3, 4.1, 4.2, 12.1, 12.2, 12.3, 12.4_

  - [x] 1.3 Add model registrations and profile definitions with import-time validation
    - Register all 10 models from design (deepseek/deepseek-chat, meta-llama/llama-3.2-3b-instruct:free, moonshotai/kimi-k2:free, google/gemini-flash-1.5, microsoft/phi-3-mini-128k-instruct:free, openai/gpt-3.5-turbo, openai/gpt-4o-mini, google/gemini-2.0-flash-exp:free, anthropic/claude-3-haiku, anthropic/claude-3.5-sonnet)
    - Define all 5 profiles: structured_extraction, vision, text_generation, template_assistance, recommendation
    - Include per-profile overrides as specified in design
    - Run validation for all models and profiles at module import time
    - Expose module-level `resolver` instance
    - _Requirements: 2.2, 10.1, 10.2, 10.3, 10.4_

- [ ] 2. Write tests for the registry module
  - [x] 2.1 Write property tests for model entry validation
    - **Property 1: Model_Entry attribute validation**
    - **Property 2: Duplicate model rejection**
    - **Property 3: Model registration round-trip**
    - **Validates: Requirements 1.1, 1.2, 1.3**
    - Create `backend/tests/unit/test_ai_model_registry_props.py`
    - Use Hypothesis with @settings(max_examples=100)
    - Implement st_model_id, st_cost_tier, st_max_tokens, st_timeout strategies

  - [x] 2.2 Write property tests for profile validation and resolution
    - **Property 4: Unknown identifier/profile raises descriptive error**
    - **Property 5: Fallback chain length validation**
    - **Property 6: Referential integrity**
    - **Property 7: Order preservation in fallback chains**
    - **Property 8: No duplicate models within a chain**
    - **Validates: Requirements 1.4, 2.1, 2.3, 2.4, 2.5, 2.6, 3.2, 3.3**

  - [x] 2.3 Write property tests for override logic
    - **Property 9: Override precedence**
    - **Property 10: Override value range validation**
    - **Property 11: Orphaned override rejection**
    - **Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5**

  - [x] 2.4 Write property tests for introspection completeness
    - **Property 15: Introspection completeness**
    - **Validates: Requirements 12.1, 12.2**

  - [x] 2.5 Write unit tests for registry module
    - Create `backend/tests/unit/test_ai_model_registry.py`
    - Test that all 5 required profiles exist and resolve
    - Test that vision profile models all have supports_vision=True
    - Test override merging for actual profile data
    - Test error messages contain profile/model names
    - _Requirements: 2.2, 3.1, 3.2, 6.2, 12.1, 12.2_

- [x] 3. Checkpoint - Ensure registry tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Refactor AIExtractor to use the registry
  - [x] 4.1 Refactor `backend/src/services/ai_extractor.py` to import and use the registry resolver
    - Import `resolver` and `RegistryError` from `services.ai_model_registry`
    - Replace hardcoded model list with `resolver.resolve_profile("structured_extraction")`
    - Use each ResolvedModel's timeout and max_tokens in API requests
    - Iterate models in chain order, skip on timeout/API error/invalid response
    - Return `{"error": "Registry unavailable: ..."}` on RegistryError
    - Return `{"error": "AI extraction failed: invalid response format"}` when all models fail
    - Remove all hardcoded Model_Identifier strings
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 11.1, 11.2, 11.3, 11.4_

  - [x] 4.2 Write unit tests for AIExtractor registry integration
    - Test fallback iteration order with mocked API responses
    - Test registry error handling returns proper error dict
    - Test all-models-fail returns terminal error structure
    - Test usage tracking calls log_ai_request with correct fields
    - _Requirements: 5.2, 5.4, 5.5, 11.3, 11.4_

- [x] 5. Refactor ImageAIProcessor to use the registry
  - [x] 5.1 Refactor `backend/src/services/image_ai_processor.py` to import and use the registry resolver
    - Import `resolver` and `RegistryError` from `services.ai_model_registry`
    - Replace hardcoded vision model list with `resolver.resolve_profile("vision")`
    - Use each ResolvedModel's timeout and max_tokens in API requests
    - Iterate models in chain order
    - Return None on all-models-fail (proceed to Tesseract OCR fallback)
    - Return None on RegistryError (proceed to Tesseract OCR fallback)
    - Remove all hardcoded Model_Identifier strings
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 11.2, 11.3_

  - [x] 5.2 Write unit tests for ImageAIProcessor registry integration
    - Test vision profile resolution and model iteration
    - Test fallback to None (Tesseract path) on chain exhaustion
    - Test registry error handling returns None
    - _Requirements: 6.1, 6.5, 11.3_

- [x] 6. Refactor AITemplateAssistant to use the registry
  - [x] 6.1 Refactor `backend/src/services/ai_template_assistant.py` to import and use the registry resolver
    - Import `resolver` and `RegistryError` from `services.ai_model_registry`
    - Replace hardcoded model list with `resolver.resolve_profile("template_assistance")`
    - Use each ResolvedModel's timeout and max_tokens in API requests
    - Iterate models in chain order
    - Return `{"success": False, "error": "AI service unavailable"}` on RegistryError without making API calls
    - Return `{"success": False, "error": "All models failed"}` when all models fail
    - Remove all hardcoded Model_Identifier strings
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 11.1, 11.2, 11.3, 11.4_

  - [x] 6.2 Write unit tests for AITemplateAssistant registry integration
    - Test profile resolution and model iteration
    - Test registry error returns error response without API calls
    - Test terminal failure structure
    - Test usage tracking with correct model_used
    - _Requirements: 7.1, 7.4, 11.3, 11.4_

- [x] 7. Refactor HybridPricingOptimizer to use the registry
  - [x] 7.1 Refactor `backend/src/services/hybrid_pricing_optimizer.py` to import and use the registry resolver
    - Import `resolver` and `RegistryError` from `services.ai_model_registry`
    - Replace hardcoded model list with `resolver.resolve_profile("recommendation")`
    - Use each ResolvedModel's timeout and max_tokens in API requests
    - Iterate models in chain order
    - Return None for AI insights when all models fail (continue with rule-based pricing)
    - Log error and return None for AI insights on RegistryError
    - Remove all hardcoded Model_Identifier strings
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 11.2, 11.3_

  - [x] 7.2 Write unit tests for HybridPricingOptimizer registry integration
    - Test profile resolution and model iteration
    - Test all-models-fail returns None and continues rule-based
    - Test registry error logs and returns None
    - _Requirements: 8.4, 8.5, 11.3_

- [x] 8. Checkpoint - Ensure all consumer refactoring tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 9. Refactor InvoiceTestService to use the registry
  - [x] 9.1 Refactor InvoiceTestService to use the registry via AIExtractor
    - Ensure `process_file_dry_run` uses the same fallback chain as AIExtractor (resolved from "structured_extraction")
    - Refactor `rerun_with_custom_prompt` to obtain fallback chain from registry instead of hardcoded list
    - Include successful Model_Identifier in performance metrics under "ai_model" field
    - On registry error, return error in errors array with stage="registry_resolution"
    - Remove all hardcoded Model_Identifier strings
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 10.5_

  - [-] 9.2 Write unit tests for InvoiceTestService registry integration
    - Test dry-run uses same chain as AIExtractor
    - Test custom prompt re-run uses registry
    - Test ai_model field in performance metrics
    - Test registry error returns stage="registry_resolution"
    - _Requirements: 9.1, 9.2, 9.3, 9.4_

- [ ] 10. Consumer integration tests and hardcoded string verification
  - [-] 10.1 Write integration tests for registry-consumer pipeline
    - Create `backend/tests/integration/test_ai_model_registry_integration.py`
    - Test full pipeline dry-run with registry resolution
    - Verify consumers use resolved timeout/max_tokens in HTTP calls via request mock
    - Verify AIUsageTracker receives correct model_used from resolved chain
    - _Requirements: 5.3, 11.4_

  - [-] 10.2 Write property tests for consumer fallback behavior
    - **Property 12: Fallback iteration — first success wins**
    - **Property 13: Vision profile invariant**
    - **Property 14: Terminal failure structure**
    - **Validates: Requirements 5.2, 6.2, 11.2, 11.3**

  - [-] 10.3 Verify no hardcoded model strings remain in consumer modules
    - Static analysis of ai_extractor.py, image_ai_processor.py, ai_template_assistant.py, hybrid_pricing_optimizer.py, and InvoiceTestService
    - Confirm zero hardcoded Model_Identifier strings in consumer files
    - All model references come exclusively from the registry
    - _Requirements: 5.6, 10.5_

- [x] 11. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The registry module must stay under 500 lines per the project's file size guidelines
- All tests use pytest with @pytest.mark.unit or @pytest.mark.integration markers
- Property tests use Hypothesis with @settings(max_examples=100)
- Test file: `backend/tests/unit/test_ai_model_registry_props.py` for property tests
- Test file: `backend/tests/unit/test_ai_model_registry.py` for unit tests
- Test file: `backend/tests/integration/test_ai_model_registry_integration.py` for integration tests

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2"] },
    { "id": 2, "tasks": ["1.3"] },
    { "id": 3, "tasks": ["2.1", "2.2", "2.3", "2.4", "2.5"] },
    { "id": 4, "tasks": ["4.1", "5.1", "6.1", "7.1"] },
    { "id": 5, "tasks": ["4.2", "5.2", "6.2", "7.2"] },
    { "id": 6, "tasks": ["9.1"] },
    { "id": 7, "tasks": ["9.2", "10.1", "10.2", "10.3"] }
  ]
}
```
