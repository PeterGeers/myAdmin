-- Compare recommended_price vs last_year_adr by listing (March-December)
SELECT 
    listing_name,
    COUNT(*) as total_records,
    AVG(recommended_price) as avg_recommended_price,
    AVG(last_year_adr) as avg_last_year_adr,
    AVG(recommended_price) - AVG(last_year_adr) as price_difference,
    ROUND(((AVG(recommended_price) - AVG(last_year_adr)) / AVG(last_year_adr)) * 100, 2) as percentage_change,
    COUNT(CASE WHEN last_year_adr IS NOT NULL THEN 1 END) as records_with_last_year_data
FROM pricing_recommendations 
WHERE MONTH(price_date) BETWEEN 3 AND 12  -- March to December
GROUP BY listing_name
ORDER BY listing_name;