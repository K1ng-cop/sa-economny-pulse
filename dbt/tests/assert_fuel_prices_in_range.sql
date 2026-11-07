-- Fuel between R5 and R100 per litre (or kg for LPG). Catches decimal-place mistakes
-- like 2028 rand instead of 20.28.
select effective_date, region, product_code, price_rand
from {{ ref('stg_fuel_prices') }}
where price_rand not between 5 and 100
