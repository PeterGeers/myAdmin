# Requirements Document

## Introduction

The AI Model Registry centralizes all OpenRouter AI model configuration into a single registry module. Currently, five different backend files independently define model fallback chains with hardcoded model identifiers, timeouts, and token limits. This leads to duplication, inconsistency, and high maintenance cost when models are deprecated or replaced. The registry provides a single source of truth for model metadata, task-based profiles with ordered fallback chains, and per-model defaults — enabling all AI consumers to be refactored to a single configuration point.

## Glossary

- **Registry**: The centralized Python module that stores all AI model definitions and task profile configurations
- **Model_Entry**: A single AI model definition within the Registry, containing the model identifier, metadata, and default parameters
- **Task_Profile**: A named configuration that maps a specific AI task type (e.g., "structured_extraction", "vision") to an ordered list of Model_Entry references forming a fallback chain
- **Fallback_Chain**: An ordered sequence of models within a Task_Profile, tried sequentially until one succeeds
- **Model_Identifier**: The OpenRouter model string (e.g., "deepseek/deepseek-chat", "openai/gpt-4o-mini")
- **Cost_Tier**: A classification of a model's pricing level: "free", "cheap", or "paid"
- **AI_Consumer**: Any backend module that calls the OpenRouter API to perform AI tasks (e.g., AIExtractor, ImageAIProcessor, HybridPricingOptimizer, AITemplateAssistant)
- **Profile_Resolver**: The component within the Registry that returns the Fallback_Chain for a given Task_Profile name

## Requirements

### Requirement 1: Model Entry Definition

**User Story:** As a developer, I want each AI model to be defined once with its metadata, so that model properties are consistent across all consumers.

#### Acceptance Criteria

1. THE Registry SHALL define each Model_Entry with the following attributes: Model_Identifier, Cost_Tier (one of "free", "cheap", or "paid"), maximum token limit (a positive integer not exceeding 16384), default timeout in seconds (a positive integer between 1 and 300), and a boolean indicating vision capability
2. IF a Model_Entry is added with a Model_Identifier that already exists in the Registry, THEN THE Registry SHALL raise a validation error indicating the duplicate Model_Identifier
3. WHEN a Model_Entry is retrieved by Model_Identifier, THE Registry SHALL return the complete set of attributes for that model
4. IF a retrieval is attempted with a Model_Identifier that does not exist in the Registry, THEN THE Registry SHALL raise a descriptive error indicating the unknown Model_Identifier

### Requirement 2: Task Profile Definition

**User Story:** As a developer, I want to define task-based profiles that map to ordered fallback chains, so that each AI use case has a clear, maintainable model sequence.

#### Acceptance Criteria

1. THE Registry SHALL support defining Task_Profile entries with a unique profile name and an ordered list of at least 1 and at most 10 Model_Identifier references
2. THE Registry SHALL include at minimum the following Task_Profile names: "structured_extraction", "vision", "text_generation", "template_assistance", "recommendation"
3. WHEN a Task_Profile is defined, THE Registry SHALL validate that every Model_Identifier in the Fallback_Chain exists as a registered Model_Entry
4. IF a Task_Profile references a Model_Identifier that is not a registered Model_Entry, THEN THE Registry SHALL raise a validation error at import time indicating the unrecognized Model_Identifier and the Task_Profile that references it
5. THE Registry SHALL preserve the insertion order of models within each Fallback_Chain
6. THE Registry SHALL reject Task_Profile definitions that contain duplicate Model_Identifier entries within the same Fallback_Chain

### Requirement 3: Profile Resolution

**User Story:** As a developer, I want to retrieve the fallback chain for a task profile, so that AI consumers can iterate models without knowing the specific configuration.

#### Acceptance Criteria

1. WHEN the Profile_Resolver receives a valid Task_Profile name, THE Profile_Resolver SHALL return the ordered Fallback_Chain as a list where each element contains the model's full configuration (Model_Identifier, timeout, max_tokens, cost_tier, supports_vision)
2. IF the Profile_Resolver receives an unregistered Task_Profile name (case-sensitive match), THEN THE Profile_Resolver SHALL raise a descriptive error indicating the invalid profile name and listing available profiles
3. THE Profile_Resolver SHALL return models in the exact order defined in the Task_Profile

### Requirement 4: Per-Model Default Overrides in Profiles

**User Story:** As a developer, I want task profiles to optionally override a model's default timeout or max_tokens, so that different tasks can tune parameters without changing the global model definition.

#### Acceptance Criteria

1. WHEN a Task_Profile specifies an override for timeout or max_tokens on a specific Model_Identifier within its Fallback_Chain, THE Profile_Resolver SHALL return the overridden value instead of the Model_Entry default for that parameter
2. WHEN a Task_Profile does not specify an override for a parameter, THE Profile_Resolver SHALL return the Model_Entry default value for that parameter
3. THE Registry SHALL validate that overridden timeout values are positive integers between 1 and 600 (seconds) and overridden max_tokens values are positive integers between 1 and 16384
4. IF a Task_Profile specifies an override for a Model_Identifier that is not part of its Fallback_Chain, THEN THE Registry SHALL raise a validation error indicating the Model_Identifier is not referenced in the profile's Fallback_Chain
5. IF an override value fails validation, THEN THE Registry SHALL raise a validation error indicating which parameter on which Model_Identifier is invalid and stating the acceptable range

### Requirement 5: Consumer Refactoring — AIExtractor

**User Story:** As a developer, I want the AIExtractor to use the Registry instead of its hardcoded model list, so that model changes only require updating the Registry.

#### Acceptance Criteria

1. WHEN AIExtractor performs invoice extraction, THE AIExtractor SHALL obtain the Fallback_Chain from the Registry using the "structured_extraction" Task_Profile
2. THE AIExtractor SHALL iterate models in the order provided by the Profile_Resolver, skipping to the next model on timeout, API error, or invalid response, and returning the result from the first model that succeeds
3. THE AIExtractor SHALL use each model's configured timeout and max_tokens from the resolved profile when making OpenRouter API requests
4. WHEN all models in the Fallback_Chain fail, THE AIExtractor SHALL return a dict with a single "error" key containing a string message indicating extraction failure
5. IF the Profile_Resolver raises an error for the "structured_extraction" Task_Profile, THEN THE AIExtractor SHALL return a dict with a single "error" key containing a string message indicating registry unavailability
6. THE AIExtractor SHALL contain no hardcoded Model_Identifier strings, obtaining all model references exclusively from the Registry

### Requirement 6: Consumer Refactoring — ImageAIProcessor

**User Story:** As a developer, I want the ImageAIProcessor to use the Registry instead of its hardcoded vision model list, so that vision model updates are centralized.

#### Acceptance Criteria

1. WHEN ImageAIProcessor performs image-based extraction, THE ImageAIProcessor SHALL obtain the Fallback_Chain from the Registry using the "vision" Task_Profile
2. THE "vision" Task_Profile SHALL contain only models where the vision capability attribute is true
3. THE ImageAIProcessor SHALL iterate models in the order provided by the Profile_Resolver
4. THE ImageAIProcessor SHALL use each model's configured timeout and max_tokens from the resolved profile
5. WHEN all models in the Fallback_Chain fail, THE ImageAIProcessor SHALL return None from the AI vision attempt and proceed to the Tesseract OCR fallback, preserving the current two-tier fallback behavior

### Requirement 7: Consumer Refactoring — AITemplateAssistant

**User Story:** As a developer, I want the AITemplateAssistant to use the Registry instead of its hardcoded model list, so that template assistance model changes are centralized.

#### Acceptance Criteria

1. WHEN AITemplateAssistant generates fix suggestions, THE AITemplateAssistant SHALL obtain the Fallback_Chain from the Registry using the "template_assistance" Task_Profile
2. THE AITemplateAssistant SHALL use each model's configured timeout and max_tokens from the resolved profile
3. THE AITemplateAssistant SHALL iterate models in the order provided by the Profile_Resolver
4. IF the Registry raises an error when resolving the "template_assistance" Task_Profile, THEN THE AITemplateAssistant SHALL return an error response indicating that the AI service is unavailable without attempting any model calls

### Requirement 8: Consumer Refactoring — HybridPricingOptimizer

**User Story:** As a developer, I want the HybridPricingOptimizer to use the Registry instead of its hardcoded model list, so that pricing recommendation model changes are centralized.

#### Acceptance Criteria

1. WHEN HybridPricingOptimizer generates pricing recommendations, THE HybridPricingOptimizer SHALL obtain the Fallback_Chain from the Registry using the "recommendation" Task_Profile
2. THE HybridPricingOptimizer SHALL iterate models in the order provided by the Profile_Resolver
3. THE HybridPricingOptimizer SHALL use each model's configured timeout and max_tokens from the resolved profile
4. WHEN all models in the Fallback_Chain fail, THE HybridPricingOptimizer SHALL return None for AI insights and continue with rule-based pricing generation without AI adjustments
5. IF the "recommendation" Task_Profile cannot be resolved from the Registry, THEN THE HybridPricingOptimizer SHALL log the error and return None for AI insights

### Requirement 9: Consumer Refactoring — InvoiceTestService

**User Story:** As a developer, I want the InvoiceTestService to inherit model configuration from the Registry through the AIExtractor, so that the test tool reflects actual pipeline configuration.

#### Acceptance Criteria

1. WHEN InvoiceTestService executes a dry-run extraction via process_file_dry_run, THE InvoiceTestService SHALL use the same Fallback_Chain as AIExtractor (resolved from the "structured_extraction" Task_Profile), including model order, timeout, and max_tokens values
2. WHEN InvoiceTestService executes a custom prompt re-run via rerun_with_custom_prompt, THE InvoiceTestService SHALL obtain the Fallback_Chain from the Registry using the "structured_extraction" Task_Profile instead of a hardcoded model list
3. WHEN a dry-run or custom prompt re-run extraction succeeds, THE InvoiceTestService SHALL include the Model_Identifier of the successful model in the performance metrics response under the "ai_model" field, where the value matches a Model_Identifier from the resolved Task_Profile
4. IF the Registry is unreachable or the "structured_extraction" Task_Profile cannot be resolved, THEN THE InvoiceTestService SHALL return an error in the errors array with stage "registry_resolution" and a message indicating the profile could not be loaded

### Requirement 10: Single-File Maintainability

**User Story:** As a developer, I want all model and profile configuration in a single Python module, so that adding, removing, or reordering models requires editing only one file.

#### Acceptance Criteria

1. THE Registry SHALL be implemented as a single Python module located in the backend services directory, containing all Model_Entry definitions and all Task_Profile configurations
2. WHEN a model is added to the Registry, THE Registry SHALL include that model in the resolved Fallback_Chain of any Task_Profile that references the new Model_Identifier without requiring modifications to any AI_Consumer module
3. WHEN a model is removed from the Registry, THE Registry SHALL raise a validation error at module import time if any Task_Profile still references the removed Model_Identifier
4. WHEN the order of Model_Identifiers within a Task_Profile Fallback_Chain is changed in the Registry, THE Profile_Resolver SHALL return the updated order without requiring modifications to any AI_Consumer module
5. THE AI_Consumer modules SHALL contain zero hardcoded Model_Identifier strings, obtaining all model references exclusively from the Registry

### Requirement 11: Backward Compatibility

**User Story:** As a developer, I want the refactored AI consumers to maintain identical external behavior, so that existing functionality is preserved during the migration.

#### Acceptance Criteria

1. THE refactored AI_Consumer modules SHALL produce response dictionaries containing the same field names and value types as the current implementation: date (string), total_amount (float), vat_amount (float), description (string), vendor (string), and \_usage metadata (dict with prompt_tokens, completion_tokens, total_tokens, model) for extraction consumers, and success (boolean), ai_suggestions (dict), model_used (string), tokens_used (integer) for the AITemplateAssistant
2. THE refactored AI_Consumer modules SHALL iterate models in Fallback_Chain order, skip a model on timeout or API error, skip a model on invalid response format, and return the result from the first model that produces a valid response
3. IF all models in the Fallback_Chain fail, THEN THE refactored AI_Consumer module SHALL return the same terminal failure structure as the current implementation: an error dictionary with an "error" key for AIExtractor, None for ImageAIProcessor vision path, and a dictionary with success=False and an error message for AITemplateAssistant
4. THE refactored AI_Consumer modules SHALL report usage data to AIUsageTracker by calling log_ai_request with the fields: administration (string), template_type (string), tokens_used (integer), and model_used (string)

### Requirement 12: Registry Introspection

**User Story:** As a developer, I want to list all registered models and profiles programmatically, so that I can build diagnostics and administrative tooling.

#### Acceptance Criteria

1. THE Registry SHALL provide a method to list all registered Model_Entry definitions, returning for each entry the Model_Identifier, Cost_Tier, maximum token limit, default timeout in seconds, and vision capability flag
2. THE Registry SHALL provide a method to list all defined Task_Profile names
3. WHEN a specific Task_Profile name is requested, THE Registry SHALL return the ordered Fallback_Chain with each model's Model_Identifier, resolved timeout, resolved max_tokens (reflecting any per-profile overrides), and any override indicators
4. IF the introspection method receives a Task_Profile name that is not registered, THEN THE Registry SHALL raise a descriptive error indicating the invalid profile name and listing available profile names
