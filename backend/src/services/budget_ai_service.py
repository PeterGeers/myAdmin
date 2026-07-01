"""
Budget AI Service — OpenRouter integration for budget AI features.

Uses the AI Model Registry for model fallback chain resolution.
All model identifiers, timeouts, and token limits come from the
registry's "text_generation" task profile.
"""

import json
import os
import logging
import re

import requests

from services.ai_model_registry import resolver, RegistryError
from services.ai_usage_tracker import AIUsageTracker

logger = logging.getLogger(__name__)


class BudgetAIService:
    """OpenRouter integration for budget AI features.

    Uses the AI Model Registry for model fallback chain resolution.
    All model identifiers, timeouts, and token limits come from the
    registry's "text_generation" task profile — no hardcoded model IDs.
    """

    def __init__(self, db=None):
        self.api_key = os.getenv("OPENROUTER_API_KEY")
        self.api_url = "https://openrouter.ai/api/v1/chat/completions"
        self.db = db
        self.usage_tracker = AIUsageTracker(db) if db else None

    def _get_model_chain(self) -> list:
        """Resolve model fallback chain from the AI Model Registry.

        Returns:
            Ordered list of ResolvedModel instances from the "text_generation" profile.

        Raises:
            RegistryError: If the profile cannot be resolved.
        """
        return resolver.resolve_profile("text_generation")

    def _call_openrouter(
        self,
        system_prompt: str,
        user_prompt: str,
        administration: str,
        max_tokens_override: int | None = None,
        timeout_override: int | None = None,
    ) -> dict:
        """Call OpenRouter with registry-resolved fallback chain.

        Iterates models in chain order, using each model's configured
        timeout and max_tokens (or the provided overrides). Falls back
        to the next model on timeout, API error, or invalid response.

        Args:
            system_prompt: System message for the LLM.
            user_prompt: User message for the LLM.
            administration: Tenant identifier for usage tracking.
            max_tokens_override: Optional per-call max_tokens limit.
            timeout_override: Optional per-call timeout in seconds (caps model timeout).

        Returns:
            dict with keys: success, content, model_used, tokens_used on success;
            or success=False with error message on failure.
        """
        if not self.api_key:
            return {
                "success": False,
                "error": "AI service unavailable: API key not configured",
            }

        try:
            chain = self._get_model_chain()
        except RegistryError as e:
            return {"success": False, "error": f"AI service unavailable: {e}"}

        for model in chain:
            try:
                # Use the stricter of model timeout and caller-specified override
                effective_timeout = model.timeout
                if timeout_override is not None:
                    effective_timeout = min(model.timeout, timeout_override)

                response = requests.post(
                    self.api_url,
                    json={
                        "model": model.model_id,
                        "max_tokens": max_tokens_override or model.max_tokens,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                    },
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    timeout=effective_timeout,
                )
                if response.status_code == 200:
                    data = response.json()
                    content = (
                        data.get("choices", [{}])[0]
                        .get("message", {})
                        .get("content", "")
                    )
                    tokens_used = data.get("usage", {}).get("total_tokens", 0)

                    # Track usage with the successful model
                    if self.usage_tracker:
                        self.usage_tracker.log_ai_request(
                            administration=administration,
                            template_type="budget",
                            tokens_used=tokens_used,
                            model_used=model.model_id,
                        )

                    return {
                        "success": True,
                        "content": content,
                        "model_used": model.model_id,
                        "tokens_used": tokens_used,
                    }
            except requests.exceptions.Timeout:
                logger.warning(f"Budget AI: timeout for model {model.model_id}")
                continue
            except Exception as e:
                logger.warning(f"Budget AI: error for model {model.model_id}: {e}")
                continue

        return {"success": False, "error": "AI service unavailable: all models failed"}

    # ------------------------------------------------------------------
    # AI Feature stubs (implemented in tasks 14.2–14.5)
    # ------------------------------------------------------------------

    def generate_narrative(
        self, dashboard_data: dict, period: str, year: int, administration: str
    ) -> dict:
        """Generate a Dutch executive summary from dashboard data.

        Formats dashboard rows into a compact prompt and requests a 2-4 sentence
        narrative highlighting the largest variances. Payload is limited to 50 rows.

        Args:
            dashboard_data: Aggregated budget vs actuals data with 'rows' list.
            period: Period filter (e.g., 'ytd', 'q1', 'month-3').
            year: Fiscal year.
            administration: Tenant identifier.

        Returns:
            dict with success, data (narrative, model_used, tokens_used) on success;
            or success=False with error message on failure.
        """
        rows = dashboard_data.get("rows", [])[:50]

        if not rows:
            return {
                "success": True,
                "data": {
                    "narrative": "Geen data beschikbaar voor analyse.",
                    "model_used": None,
                    "tokens_used": 0,
                },
            }

        # Format rows into compact text for the prompt
        row_lines = []
        for r in rows:
            budget = r.get("budget", 0)
            actual = r.get("actual", 0)
            variance = r.get("variance", 0)
            row_lines.append(
                f"- {r.get('code', '')} {r.get('name', '')}: "
                f"budget={budget:.2f}, realisatie={actual:.2f}, afwijking={variance:.2f}"
            )
        row_text = "\n".join(row_lines)

        system_prompt = (
            "Je bent een financieel analist. Schrijf een beknopte samenvatting "
            "van 2-4 zinnen in het Nederlands over de budget vs realisatie data. "
            "Benadruk de grootste afwijkingen (positief en negatief). "
            "Gebruik professioneel financieel Nederlands."
        )

        user_prompt = (
            f"Budget vs Realisatie overzicht voor boekjaar {year}, periode: {period}\n\n"
            f"Data:\n{row_text}"
        )

        result = self._call_openrouter(
            system_prompt,
            user_prompt,
            administration,
            max_tokens_override=500,
            timeout_override=15,
        )

        if not result["success"]:
            return result

        return {
            "success": True,
            "data": {
                "narrative": result["content"],
                "model_used": result["model_used"],
                "tokens_used": result["tokens_used"],
            },
        }

    def translate_query(
        self, question: str, year: int, hierarchy_context: list, administration: str
    ) -> dict:
        """Translate natural language question to dashboard parameters.

        Sends the user's natural language question along with account hierarchy
        context to the AI model. The model returns JSON with dashboard filter
        parameters. Results are validated against the allowed schema and checked
        for injection attempts before returning.

        Args:
            question: User's natural language budget question.
            year: Fiscal year context.
            hierarchy_context: Account hierarchy for context (list of dicts with code/name).
            administration: Tenant identifier.

        Returns:
            dict with success, data (interpreted_params, filter_description,
            model_used, tokens_used) on success; or success=False with error.
        """
        # Build context from hierarchy (limit to 100 entries to control token usage)
        hierarchy_text = "\n".join(
            f"- {h['code']}: {h['name']}" for h in hierarchy_context[:100]
        )

        system_prompt = (
            "You are a financial query translator. Convert the user's Dutch/English question "
            "into dashboard API parameters as JSON. Only use these keys: "
            "year (int), level (parent|subparent|account), period (month-1..month-12|q1..q4|ytd|full), "
            "parent_code (string), subparent_code (string), reference_number (string). "
            "Return ONLY valid JSON, no other text."
        )

        user_prompt = (
            f"Fiscal year context: {year}\n"
            f"Account hierarchy:\n{hierarchy_text}\n\n"
            f"User question: {question}"
        )

        result = self._call_openrouter(
            system_prompt, user_prompt, administration, max_tokens_override=300
        )

        if not result["success"]:
            return result

        # Parse JSON from response
        content = result["content"].strip()
        # Try to extract JSON from potential markdown code blocks
        json_match = re.search(r"\{[^}]*\}", content, re.DOTALL)
        if json_match:
            content = json_match.group()

        try:
            params = json.loads(content)
        except json.JSONDecodeError:
            return {
                "success": False,
                "error": "Could not interpret query. Try rephrasing with specific account names or periods.",
            }

        # Validate against allowed schema
        allowed_keys = {
            "year",
            "level",
            "period",
            "parent_code",
            "subparent_code",
            "reference_number",
        }
        validated_params = {}

        for key, value in params.items():
            if key not in allowed_keys:
                continue
            str_val = str(value)
            # Security: reject values with semicolons or exceeding 100 chars
            if ";" in str_val or len(str_val) > 100:
                return {
                    "success": False,
                    "error": "Could not interpret query safely. Try rephrasing your question.",
                }
            # Security: reject SQL fragments
            if re.search(
                r"(SELECT|INSERT|UPDATE|DELETE|DROP|ALTER|EXEC)", str_val, re.IGNORECASE
            ):
                return {
                    "success": False,
                    "error": "Could not interpret query safely. Try rephrasing your question.",
                }
            validated_params[key] = value

        return {
            "success": True,
            "data": {
                "interpreted_params": validated_params,
                "filter_description": f"Interpreted from: {question}",
                "model_used": result["model_used"],
                "tokens_used": result["tokens_used"],
            },
        }

    def suggest_adjustments(
        self, budget_lines: list, context_notes: str, administration: str
    ) -> dict:
        """Suggest adjustments to draft budget lines based on context.

        Sends current budget line amounts and user-provided context notes to the
        AI service, parses the response into structured suggestions, and filters
        out any suggestions referencing account codes not in the provided lines.

        Args:
            budget_lines: List of dicts with account_code, account_name, and
                month_01..month_12 fields. Max 100 lines.
            context_notes: User-provided context for adjustments (e.g.,
                "rent increases 5% in June", "dropped platform X").
            administration: Tenant identifier for usage tracking.

        Returns:
            dict with success, data.suggestions, data.model_used, data.tokens_used;
            or success=False with error message.
        """
        if len(budget_lines) > 100:
            return {
                "success": False,
                "error": "Too many budget lines for AI analysis. Select a subset (max 100 lines).",
            }

        # Build compact line summary for the prompt
        line_text = "\n".join(
            f"- {item['account_code']} ({item.get('account_name', '')}): "
            + ", ".join(
                f"m{i + 1}={item.get(f'month_{i + 1:02d}', 0)}" for i in range(12)
            )
            for item in budget_lines
        )

        valid_codes = {item["account_code"] for item in budget_lines}

        system_prompt = (
            "You are a financial budget advisor. Given budget line data and context notes, "
            "suggest specific adjustments. Return a JSON array of suggestions. Each suggestion: "
            '{"account_code": "...", "account_name": "...", "affected_months": [1-12], '
            '"current_amounts": [...], "suggested_amounts": [...], "reasoning": "..."}'
            "\nReturn ONLY the JSON array, no other text."
        )

        user_prompt = f"Context notes: {context_notes}\n\nBudget lines:\n{line_text}"

        result = self._call_openrouter(system_prompt, user_prompt, administration)

        if not result["success"]:
            return result

        # Parse suggestions from AI response
        try:
            content = result["content"].strip()
            # Extract JSON array from response (handles markdown code blocks)
            json_match = re.search(r"\[.*\]", content, re.DOTALL)
            if json_match:
                content = json_match.group()
            suggestions = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            suggestions = []

        # Filter: only include suggestions for accounts present in the budget lines
        filtered = [s for s in suggestions if s.get("account_code") in valid_codes]

        return {
            "success": True,
            "data": {
                "suggestions": filtered,
                "model_used": result["model_used"],
                "tokens_used": result["tokens_used"],
            },
        }

    def generate_lines(
        self,
        chart_of_accounts: list,
        prior_actuals: list,
        fiscal_year: int,
        context_notes: str,
        administration: str,
    ) -> dict:
        """Generate proposed budget lines from prior-year actuals and context notes.

        Uses AI to analyze the tenant's chart of accounts and prior-year actuals,
        incorporating user-provided context notes (e.g. "rent increases 5% in June"),
        and returns proposed budget lines for review.

        Args:
            chart_of_accounts: Available accounts from rekeningschema.
            prior_actuals: Prior year monthly actuals (list of {account_code, maand, amount}).
            fiscal_year: Target fiscal year for the budget.
            context_notes: User-provided context (e.g. known changes for the year).
            administration: Tenant identifier.

        Returns:
            dict with success, data containing proposed_lines, model_used, tokens_used.
        """
        prior_year = fiscal_year - 1

        # Build account summary from monthly actuals
        account_totals: dict = {}
        for row in prior_actuals:
            code = row.get("account_code", "")
            amount = float(row.get("amount", 0))
            if code not in account_totals:
                account_totals[code] = {}
            month = int(row.get("maand", 0))
            account_totals[code][month] = account_totals[code].get(month, 0) + amount

        # Build account text for AI
        account_lines = []
        for acct in chart_of_accounts[:200]:
            code = acct["account_code"]
            name = acct.get("account_name", "")
            monthly = account_totals.get(code, {})
            total = sum(monthly.values())
            if total != 0 or code in account_totals:
                months_str = ", ".join(
                    f"M{m}:{v:.0f}" for m, v in sorted(monthly.items())
                )
                account_lines.append(
                    f"- {code} {name}: total={total:.2f} [{months_str}]"
                )
            else:
                account_lines.append(f"- {code} {name}: no activity in {prior_year}")

        account_text = "\n".join(account_lines[:150])

        system_prompt = (
            "You are a financial budget advisor. Given a chart of accounts with "
            f"prior-year ({prior_year}) monthly actuals and user context notes, "
            f"generate proposed budget lines for fiscal year {fiscal_year}. "
            "Return a JSON array of proposed budget lines. Each line: "
            '{"account_code": "...", "account_name": "...", '
            '"period_mode": "Monthly", '
            '"detail_dimension_type": null, '
            '"detail_dimension_value": null, '
            '"amounts": [jan, feb, mar, apr, may, jun, jul, aug, sep, oct, nov, dec], '
            '"reasoning": "brief explanation"}'
            "\nOnly include accounts that should have a budget (non-zero expected activity). "
            "Use prior-year actuals as the baseline, adjusted for the context notes. "
            "Return ONLY the JSON array, no markdown."
        )

        user_prompt = (
            f"Chart of accounts with {prior_year} monthly actuals:\n{account_text}"
        )
        if context_notes:
            user_prompt += f"\n\nContext notes for {fiscal_year}:\n{context_notes}"

        result = self._call_openrouter(
            system_prompt, user_prompt, administration, max_tokens_override=4000
        )

        if not result["success"]:
            return result

        # Parse proposed lines from AI response
        try:
            content = result["content"].strip()
            json_match = re.search(r"\[.*\]", content, re.DOTALL)
            if json_match:
                content = json_match.group()
            proposed_lines = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            proposed_lines = []

        # Validate: ensure each line has required fields and amounts is length 12
        valid_lines = []
        for line in proposed_lines:
            if (
                isinstance(line, dict)
                and "account_code" in line
                and "amounts" in line
                and isinstance(line["amounts"], list)
                and len(line["amounts"]) == 12
            ):
                valid_lines.append(line)

        return {
            "success": True,
            "data": {
                "proposed_lines": valid_lines,
                "model_used": result["model_used"],
                "tokens_used": result["tokens_used"],
            },
        }
