-- Add last year ADR column to pricing_recommendations table
ALTER TABLE pricing_recommendations 
ADD COLUMN last_year_adr DECIMAL(10,2) NULL;