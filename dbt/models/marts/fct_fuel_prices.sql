-- One row per price adjustment per region per product.
select
    period_month,
    effective_date,
    region,
    product_code,
    price_unit,
    price_rand,
    change_rand
from {{ ref('int_fuel_prices_monthly') }}
