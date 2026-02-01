"""
AI Usage Tracker Service for Railway Migration
Tracks AI API usage and associated costs for monitoring and billing purposes.

This service logs all AI API requests to the ai_usage_log table, enabling:
- Cost tracking per tenant
- Usage monitoring and analytics
- Budget management
- Billing reports
"""

import logging
from typing import Optional
from decimal import Decimal

logger = logging.getLogger(__name__)


class AIUsageTracker:
    """
    Tracks AI API usage and costs.
    
    Provides functionality for:
    - Logging AI API requests with token usage
    - Calculating cost estimates based on token usage
    - Storing usage data in the ai_usage_log table
    """
    
    # Model pricing per 1M tokens (input/output average)
    # Source: OpenRouter pricing as of January 2026
    MODEL_PRICING = {
        'google/gemini-flash-1.5': 0.0,  # FREE
        'meta-llama/llama-3.2-3b-instruct:free': 0.0,  # FREE
        'deepseek/deepseek-chat': 0.685,  # Average of $0.27 input + $1.10 output
        'anthropic/claude-3.5-sonnet': 3.0,  # Approximate average
        'default': 0.5  # Conservative default estimate
    }
    
    def __init__(self, db):
        """
        Initialize the AI usage tracker.
        
        Args:
            db: Database connection object with execute_query method
        """
        self.db = db
        logger.info("AIUsageTracker initialized")
    
    def log_ai_request(
        self,
        administration: str,
        template_type: str,
        tokens_used: int,
        model_used: Optional[str] = None
    ) -> bool:
        """
        Log an AI API request with token usage and cost estimate.
        
        Args:
            administration: Tenant/administration identifier
            template_type: Type of template being processed (e.g., 'str_invoice_nl')
            tokens_used: Number of tokens consumed by the API request
            model_used: Optional model identifier for accurate cost calculation
            
        Returns:
            True if logging succeeded, False otherwise
        """
        try:
            # Calculate cost estimate
            cost_estimate = self._calculate_cost(tokens_used, model_used)
            
            # Build feature identifier
            feature = f'template_help_{template_type}'
            
            # Log to database
            query = """
                INSERT INTO ai_usage_log
                (administration, feature, tokens_used, cost_estimate)
                VALUES (%s, %s, %s, %s)
            """
            
            self.db.execute_query(
                query,
                [administration, feature, tokens_used, cost_estimate],
                fetch=False,
                commit=True
            )
            
            logger.info(
                f"Logged AI usage: {administration} - {feature} - "
                f"{tokens_used} tokens - ${cost_estimate:.6f}"
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to log AI usage: {e}")
            # Don't fail the main operation if logging fails
            return False
    
    def _calculate_cost(
        self,
        tokens_used: int,
        model_used: Optional[str] = None
    ) -> Decimal:
        """
        Calculate cost estimate based on token usage and model.
        
        Uses model-specific pricing when available, falls back to default estimate.
        
        Args:
            tokens_used: Number of tokens consumed
            model_used: Optional model identifier
            
        Returns:
            Cost estimate as Decimal (6 decimal places)
        """
        try:
            # Get pricing for model (or use default)
            price_per_million = self.MODEL_PRICING.get(
                model_used,
                self.MODEL_PRICING['default']
            )
            
            # Calculate cost: (tokens / 1,000,000) * price_per_million
            cost = Decimal(tokens_used) / Decimal(1_000_000) * Decimal(price_per_million)
            
            # Round to 6 decimal places
            cost = cost.quantize(Decimal('0.000001'))
            
            logger.debug(
                f"Cost calculation: {tokens_used} tokens * "
                f"${price_per_million}/1M = ${cost:.6f}"
            )
            
            return cost
            
        except Exception as e:
            logger.error(f"Failed to calculate cost: {e}")
            # Return 0 if calculation fails
            return Decimal('0.000000')
    
    def get_usage_summary(
        self,
        administration: str,
        days: int = 30
    ) -> dict:
        """
        Get usage summary for a tenant over specified period.
        
        Args:
            administration: Tenant/administration identifier
            days: Number of days to look back (default: 30)
            
        Returns:
            Dictionary containing:
            {
                'total_requests': int,
                'total_tokens': int,
                'total_cost': Decimal,
                'by_feature': dict
            }
        """
        try:
            # Get aggregated usage
            query = """
                SELECT 
                    COUNT(*) as total_requests,
                    SUM(tokens_used) as total_tokens,
                    SUM(cost_estimate) as total_cost
                FROM ai_usage_log
                WHERE administration = %s
                AND created_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
            """
            
            result = self.db.execute_query(query, [administration, days])
            
            if not result or len(result) == 0:
                return {
                    'total_requests': 0,
                    'total_tokens': 0,
                    'total_cost': Decimal('0.000000'),
                    'by_feature': {}
                }
            
            row = result[0]
            
            # Get breakdown by feature
            feature_query = """
                SELECT 
                    feature,
                    COUNT(*) as requests,
                    SUM(tokens_used) as tokens,
                    SUM(cost_estimate) as cost
                FROM ai_usage_log
                WHERE administration = %s
                AND created_at >= DATE_SUB(NOW(), INTERVAL %s DAY)
                GROUP BY feature
                ORDER BY cost DESC
            """
            
            feature_results = self.db.execute_query(
                feature_query,
                [administration, days]
            )
            
            by_feature = {}
            if feature_results:
                for feature_row in feature_results:
                    by_feature[feature_row['feature']] = {
                        'requests': feature_row['requests'],
                        'tokens': feature_row['tokens'],
                        'cost': feature_row['cost']
                    }
            
            return {
                'total_requests': row['total_requests'] or 0,
                'total_tokens': row['total_tokens'] or 0,
                'total_cost': row['total_cost'] or Decimal('0.000000'),
                'by_feature': by_feature
            }
            
        except Exception as e:
            logger.error(f"Failed to get usage summary: {e}")
            return {
                'total_requests': 0,
                'total_tokens': 0,
                'total_cost': Decimal('0.000000'),
                'by_feature': {}
            }
