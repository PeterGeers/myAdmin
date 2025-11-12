-- Add AI outcome columns to pricing_recommendations table
ALTER TABLE pricing_recommendations 
ADD COLUMN ai_recommended_adr DECIMAL(10,2) NULL,
ADD COLUMN ai_historical_adr DECIMAL(10,2) NULL,
ADD COLUMN ai_variance VARCHAR(10) NULL,
ADD COLUMN ai_reasoning TEXT NULL;