"""
AI Template Assistant Service for Railway Migration
Provides AI-powered assistance for fixing template validation errors using OpenRouter API.

This service helps Tenant Administrators fix template errors without requiring SysAdmin access
to tenant data, maintaining privacy while providing intelligent assistance.
"""

import os
import re
import json
import logging
import requests
from typing import Dict, List, Any, Optional
from services.ai_usage_tracker import AIUsageTracker

logger = logging.getLogger(__name__)


class AITemplateAssistant:
    """
    AI-powered template assistance using OpenRouter.
    
    Provides functionality for:
    - Analyzing template validation errors
    - Generating fix suggestions with code examples
    - Sanitizing templates to remove PII before sending to AI
    - Applying auto-fixes to templates
    """
    
    def __init__(self, db=None):
        """
        Initialize the AI template assistant.
        
        Loads API key from environment and sets up model fallback chain.
        
        Args:
            db: Optional database connection for usage tracking
        """
        self.api_key = os.getenv('OPENROUTER_API_KEY')
        self.api_url = 'https://openrouter.ai/api/v1/chat/completions'
        self.db = db
        
        # Initialize usage tracker if database is provided
        self.usage_tracker = AIUsageTracker(db) if db else None
        
        # Smart fallback strategy: try FREE models first, then cheap, then paid as backup
        self.models = [
            "google/gemini-flash-1.5",  # FREE - Primary, fast, good for structured output
            "meta-llama/llama-3.2-3b-instruct:free",  # FREE - Backup if Gemini rate-limited
            "deepseek/deepseek-chat",  # Very cheap ($0.27/$1.10 per 1M tokens) - Excellent for code analysis
            "anthropic/claude-3.5-sonnet"  # Paid fallback (last resort, most reliable)
        ]
        
        if not self.api_key:
            logger.warning("OPENROUTER_API_KEY not set - AI assistance will be unavailable")
        
        logger.info(f"AITemplateAssistant initialized with fallback chain: {', '.join(self.models)}")
    
    def get_fix_suggestions(
        self,
        template_type: str,
        template_content: str,
        validation_errors: List[Dict],
        required_placeholders: List[str],
        administration: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get AI suggestions for fixing template errors.
        
        Sends template and validation errors to OpenRouter AI for analysis
        and receives structured fix suggestions.
        
        Args:
            template_type: Type of template (e.g., 'str_invoice_nl')
            template_content: Template HTML content
            validation_errors: List of validation error dictionaries
            required_placeholders: List of required placeholder names
            administration: Optional tenant identifier for usage tracking
            
        Returns:
            Dictionary containing:
            {
                'success': bool,
                'ai_suggestions': dict (if successful),
                'error': str (if failed)
            }
        """
        try:
            logger.info(f"Getting AI fix suggestions for template type '{template_type}'")
            
            # Check if API key is available
            if not self.api_key:
                return {
                    'success': False,
                    'error': 'AI service not configured - OPENROUTER_API_KEY not set'
                }
            
            # Sanitize template to remove PII
            sanitized_template = self._sanitize_template(template_content)
            
            # Build prompt for AI
            prompt = self._build_prompt(
                template_type,
                sanitized_template,
                validation_errors,
                required_placeholders
            )
            
            # Try models in fallback chain
            last_error = None
            for model in self.models:
                try:
                    logger.info(f"Trying model: {model}")
                    
                    # Call OpenRouter API
                    response = requests.post(
                        self.api_url,
                        headers={
                            'Authorization': f'Bearer {self.api_key}',
                            'Content-Type': 'application/json',
                            'HTTP-Referer': os.getenv('APP_URL', 'http://localhost:3000'),
                            'X-Title': 'Template Assistant'
                        },
                        json={
                            'model': model,
                            'messages': [
                                {
                                    'role': 'system',
                                    'content': (
                                        'You are a helpful assistant that fixes HTML template errors. '
                                        'Provide specific, actionable fixes with code examples. '
                                        'Always respond with valid JSON.'
                                    )
                                },
                                {
                                    'role': 'user',
                                    'content': prompt
                                }
                            ],
                            'temperature': 0.3,  # Lower for more consistent fixes
                            'max_tokens': 2000
                        },
                        timeout=30
                    )
                    
                    if response.status_code != 200:
                        logger.warning(f"{model} API error: {response.status_code} - trying next model")
                        last_error = f'AI service returned error: {response.status_code}'
                        continue
                    
                    # Parse AI response
                    ai_response = response.json()
                    
                    if 'choices' not in ai_response or len(ai_response['choices']) == 0:
                        logger.warning(f"{model} returned invalid format - trying next model")
                        last_error = 'Invalid response from AI service'
                        continue
                    
                    response_text = ai_response['choices'][0]['message']['content']
                    suggestions = self._parse_ai_response(response_text)
                    
                    # Extract token usage from response
                    tokens_used = 0
                    if 'usage' in ai_response:
                        usage = ai_response['usage']
                        # Total tokens = prompt tokens + completion tokens
                        tokens_used = usage.get('total_tokens', 0)
                        if tokens_used == 0:
                            # Fallback: sum prompt and completion tokens
                            tokens_used = usage.get('prompt_tokens', 0) + usage.get('completion_tokens', 0)
                    
                    # Log AI usage if tracker is available and administration is provided
                    if self.usage_tracker and administration and tokens_used > 0:
                        self.usage_tracker.log_ai_request(
                            administration=administration,
                            template_type=template_type,
                            tokens_used=tokens_used,
                            model_used=model
                        )
                    
                    logger.info(f"Successfully received AI suggestions using {model} ({tokens_used} tokens)")
                    
                    return {
                        'success': True,
                        'ai_suggestions': suggestions,
                        'model_used': model,
                        'tokens_used': tokens_used
                    }
                    
                except requests.exceptions.Timeout:
                    logger.warning(f"{model} timed out - trying next model")
                    last_error = 'AI service request timed out'
                    continue
                except requests.exceptions.RequestException as e:
                    logger.warning(f"{model} request failed: {e} - trying next model")
                    last_error = f'AI service request failed: {str(e)}'
                    continue
                except Exception as e:
                    logger.warning(f"{model} failed: {e} - trying next model")
                    last_error = f'Failed to process response: {str(e)}'
                    continue
            
            # All models failed
            logger.error(f"All models failed. Last error: {last_error}")
            return {
                'success': False,
                'error': last_error or 'All AI models failed'
            }
            
        except Exception as e:
            logger.error(f"Unexpected error in get_fix_suggestions: {e}")
            return {
                'success': False,
                'error': f'Failed to get AI suggestions: {str(e)}'
            }
    
    def _build_prompt(
        self,
        template_type: str,
        template_content: str,
        validation_errors: List[Dict],
        required_placeholders: List[str]
    ) -> str:
        """
        Build prompt for AI analysis.
        
        Creates a structured prompt that includes template type, validation errors,
        required placeholders, and the sanitized template content.
        
        Args:
            template_type: Type of template
            template_content: Sanitized template HTML content
            validation_errors: List of validation error dictionaries
            required_placeholders: List of required placeholder names
            
        Returns:
            Formatted prompt string
        """
        # Format errors for prompt
        formatted_errors = self._format_errors(validation_errors)
        
        # Limit template content to prevent token overflow
        max_template_length = 10000  # ~10KB
        truncated_template = template_content[:max_template_length]
        if len(template_content) > max_template_length:
            truncated_template += "\n... (template truncated for analysis)"
        
        prompt = f"""
I have an HTML template for a {template_type} report that has validation errors.

**Required Placeholders**: {', '.join(required_placeholders)}

**Validation Errors**:
{formatted_errors}

**Template Code**:
```html
{truncated_template}
```

Please analyze the errors and provide:

1. A brief explanation of each issue
2. Specific fixes with code examples
3. The location in the template where fixes should be applied
4. Whether each fix can be auto-applied

Format your response as JSON:
{{
  "analysis": "Overall analysis of the issues",
  "fixes": [
    {{
      "issue": "Description of the specific issue",
      "suggestion": "How to fix it",
      "code_example": "Code to add or replace",
      "location": "Where in template (e.g., 'header section', 'line 45')",
      "auto_fixable": true or false
    }}
  ],
  "auto_fix_available": true or false,
  "confidence": "high, medium, or low"
}}
"""
        return prompt
    
    def _sanitize_template(self, template_content: str) -> str:
        """
        Remove any potentially sensitive data from template.
        
        Sanitizes the template by removing:
        - Email addresses
        - Phone numbers
        - Potential addresses
        
        Preserves placeholders like {{ email }} and {{ phone }}.
        
        Args:
            template_content: Original template HTML content
            
        Returns:
            Sanitized template content
        """
        sanitized = template_content
        
        # Remove hardcoded email addresses (but keep placeholders)
        # Match emails that are NOT inside {{ }}
        sanitized = re.sub(
            r'(?<!\{)\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b(?!\})',
            'email@example.com',
            sanitized
        )
        
        # Remove hardcoded phone numbers (10+ digits)
        # Match phone numbers that are NOT inside {{ }}
        sanitized = re.sub(
            r'(?<!\{)\b\d{10,}\b(?!\})',
            '0123456789',
            sanitized
        )
        
        # Remove potential street addresses (basic pattern)
        # Match patterns like "123 Main Street" but not placeholders
        # Use a more specific pattern that captures the full address
        sanitized = re.sub(
            r'(?<!\{)\b\d+\s+[A-Za-z]+\s+(Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr)\b(?!\})',
            '123 Main Street',
            sanitized,
            flags=re.IGNORECASE
        )
        
        logger.debug("Template sanitized - removed potential PII")
        
        return sanitized
    
    def _format_errors(self, errors: List[Dict]) -> str:
        """
        Format errors for prompt.
        
        Converts error dictionaries into a human-readable format
        for inclusion in the AI prompt.
        
        Args:
            errors: List of error dictionaries
            
        Returns:
            Formatted error string
        """
        if not errors:
            return "No errors"
        
        formatted = []
        for i, error in enumerate(errors, 1):
            error_type = error.get('type', 'unknown')
            message = error.get('message', 'No message')
            severity = error.get('severity', 'error')
            line = error.get('line', '')
            
            error_str = f"{i}. [{error_type}] {message}"
            if line:
                error_str += f" (line {line})"
            error_str += f" [severity: {severity}]"
            
            formatted.append(error_str)
        
        return '\n'.join(formatted)
    
    def _parse_ai_response(self, response_text: str) -> Dict:
        """
        Parse AI response into structured format.
        
        Extracts JSON from AI response, handling cases where the AI
        wraps the JSON in markdown code blocks.
        
        Args:
            response_text: Raw response text from AI
            
        Returns:
            Parsed response dictionary
        """
        try:
            # Try to extract JSON from response
            # AI might wrap it in markdown code blocks
            if '```json' in response_text:
                json_start = response_text.find('```json') + 7
                json_end = response_text.find('```', json_start)
                response_text = response_text[json_start:json_end]
            elif '```' in response_text:
                json_start = response_text.find('```') + 3
                json_end = response_text.find('```', json_start)
                response_text = response_text[json_start:json_end]
            
            # Parse JSON
            parsed = json.loads(response_text.strip())
            
            # Validate structure
            if not isinstance(parsed, dict):
                raise ValueError("Response is not a dictionary")
            
            # Ensure required fields exist
            if 'analysis' not in parsed:
                parsed['analysis'] = 'Analysis not provided'
            if 'fixes' not in parsed:
                parsed['fixes'] = []
            if 'auto_fix_available' not in parsed:
                parsed['auto_fix_available'] = False
            if 'confidence' not in parsed:
                parsed['confidence'] = 'low'
            
            logger.debug("Successfully parsed AI response")
            
            return parsed
            
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse AI response as JSON: {e}")
            # Fallback: return raw text as analysis
            return {
                'analysis': response_text,
                'fixes': [],
                'auto_fix_available': False,
                'confidence': 'low'
            }
        except Exception as e:
            logger.error(f"Failed to parse AI response: {e}")
            return {
                'analysis': 'Failed to parse AI response',
                'fixes': [],
                'auto_fix_available': False,
                'confidence': 'low'
            }
    
    def apply_auto_fixes(
        self,
        template_content: str,
        fixes: List[Dict]
    ) -> str:
        """
        Apply auto-fixable suggestions to template.
        
        Iterates through fixes and applies those marked as auto_fixable.
        Currently supports adding missing placeholders.
        
        Args:
            template_content: Original template HTML content
            fixes: List of fix dictionaries from AI
            
        Returns:
            Modified template content with fixes applied
        """
        try:
            logger.info(f"Applying auto-fixes to template ({len(fixes)} fixes)")
            
            modified_template = template_content
            fixes_applied = 0
            
            for fix in fixes:
                if not fix.get('auto_fixable', False):
                    continue
                
                issue = fix.get('issue', '')
                code_example = fix.get('code_example', '')
                location = fix.get('location', '')
                
                # Skip if code_example is invalid
                if not code_example or not isinstance(code_example, str):
                    logger.warning(f"Skipping fix with invalid code_example: {issue}")
                    continue
                
                # Apply fix based on issue type
                if 'missing' in issue.lower() and 'placeholder' in issue.lower():
                    # Add missing placeholder
                    modified_template = self._add_placeholder(
                        modified_template,
                        code_example,
                        location
                    )
                    fixes_applied += 1
                    logger.debug(f"Applied fix for: {issue}")
            
            logger.info(f"Successfully applied {fixes_applied} auto-fixes")
            
            return modified_template
            
        except Exception as e:
            logger.error(f"Failed to apply auto-fixes: {e}")
            # Return original template if fixes fail
            return template_content
    
    def _add_placeholder(
        self,
        template: str,
        code_to_add: str,
        location: str
    ) -> str:
        """
        Add missing placeholder to template.
        
        Attempts to intelligently place the code based on the location hint.
        Falls back to adding at the end of the body if location is unclear.
        
        Args:
            template: Original template HTML content
            code_to_add: Code snippet to add
            location: Location hint from AI (e.g., 'header section', 'line 45')
            
        Returns:
            Modified template with code added
        """
        try:
            # Try to find a good insertion point based on location hint
            location_lower = location.lower()
            
            # Check for specific section hints
            if 'header' in location_lower:
                # Try to add in header section
                if '<header' in template:
                    # Add before closing header tag
                    template = template.replace('</header>', f'{code_to_add}\n</header>', 1)
                    return template
                elif '<head>' in template:
                    # Add before closing head tag
                    template = template.replace('</head>', f'{code_to_add}\n</head>', 1)
                    return template
            
            elif 'footer' in location_lower:
                # Try to add in footer section
                if '<footer' in template:
                    template = template.replace('</footer>', f'{code_to_add}\n</footer>', 1)
                    return template
            
            elif 'body' in location_lower or 'main' in location_lower:
                # Try to add in body/main section
                if '<main' in template:
                    template = template.replace('</main>', f'{code_to_add}\n</main>', 1)
                    return template
            
            # Default: add before closing body tag
            if '</body>' in template:
                template = template.replace('</body>', f'{code_to_add}\n</body>', 1)
            else:
                # Last resort: append to end
                template += '\n' + code_to_add
            
            return template
            
        except Exception as e:
            logger.error(f"Failed to add placeholder: {e}")
            # Return original template if addition fails
            return template
