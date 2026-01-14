* Build a STR Pricing front-end as a component
** Start the calculation model as designed in test_hybrid_pricing.py
*** delete rows in pricing_recommendations before loading new rows, 
*** delete ai_insights before new are added
*** Fill pricing_recommendations
*** Show the results in 1 table compared by listing based on a kind of logic as defined in analyze_pricing_factors.py
*** Show a trend line on a month by month base of the historic adr recommended adr 

* Can you write a migration prompt to :
*** migrate the production backend to t3.small with 2 containers (Backend and MySQL) 
*** migrate the production frontend to amplify with github (url will be admin.pgeers.nl and url/dns records remain hosted at godaddy)
*** Basic HTTP Auth Cost: $0 Code: Built into Flask/nginx Simple: Browser popup login
*** Focus on a stepwise approach and proper testing after each step
*** Focus on the api's used between frontend and backend and its impact

Docker logs backend:
# View backend logs
docker logs myadmin-backend-1
# Follow logs in real-time
docker logs -f myadmin-backend-1
# Last 50 lines
docker logs --tail 50 myadmin-backend-1
