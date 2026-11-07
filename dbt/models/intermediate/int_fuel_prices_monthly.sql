-- One row per month per region per product: the price set in that month's adjustment,
-- and how much it moved from the previous adjustment.
with fuel as (

    select * from {{ ref('stg_fuel_prices') }}

)

select
    date_trunc('month', effective_date)::date   as period_month,
    effective_date,
    region,
    product_code,
    price_unit,
    price_rand,
    price_rand - lag(price_rand) over (
        partition by region, product_code
        order by effective_date
    )                                           as change_rand
from fuel
