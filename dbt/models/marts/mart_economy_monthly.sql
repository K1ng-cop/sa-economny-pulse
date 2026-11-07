-- The headline table: one row per month with the rand, fuel, inflation and Cape Town weather
-- side by side. Answers questions like "does a weaker rand show up at the pump a month later?"

with months as (

    select distinct month_start
    from {{ ref('dim_date') }}
    where month_start between (select date_trunc('month', min(rate_date)) from {{ ref('fct_fx_daily') }})
                          and date_trunc('month', current_date)

),

usd_zar as (

    -- average of published rates only; weekend fills would over-weight Fridays
    select
        date_trunc('month', rate_date)::date    as month_start,
        round(avg(zar_per_unit), 4)             as usd_zar_avg,
        count(*)                                as fx_trading_days
    from {{ ref('fct_fx_daily') }}
    where currency_code = 'USD' and not is_filled
    group by 1

),

fuel as (

    select
        period_month                                                        as month_start,
        max(price_rand)  filter (where product_code = 'petrol_95_ulp')      as petrol_95_gauteng_rand,
        max(change_rand) filter (where product_code = 'petrol_95_ulp')      as petrol_95_gauteng_change_rand,
        max(price_rand)  filter (where product_code = 'diesel_50ppm')       as diesel_50ppm_gauteng_rand,
        max(change_rand) filter (where product_code = 'diesel_50ppm')       as diesel_50ppm_gauteng_change_rand
    from {{ ref('fct_fuel_prices') }}
    where region = 'gauteng'
    group by 1

),

cpi as (

    select
        period_month        as month_start,
        index_value         as cpi_headline_index,
        yoy_inflation_pct   as cpi_headline_yoy_pct
    from {{ ref('fct_cpi_monthly') }}
    where series_code = 'CPS00000'  -- headline CPI, all urban areas

),

weather as (

    select
        date_trunc('month', weather_date)::date as month_start,
        round(avg(temp_max_c), 1)               as cape_town_avg_max_temp_c,
        round(sum(rain_mm), 1)                  as cape_town_rain_mm
    from {{ ref('fct_weather_daily') }}
    where location = 'cape_town'
    group by 1

),

combined as (

    select
        months.month_start,
        usd_zar.usd_zar_avg,
        round((usd_zar.usd_zar_avg / lag(usd_zar.usd_zar_avg) over (order by months.month_start) - 1) * 100, 2)
                                                as usd_zar_change_pct,
        usd_zar.fx_trading_days,
        fuel.petrol_95_gauteng_rand,
        fuel.petrol_95_gauteng_change_rand,
        fuel.diesel_50ppm_gauteng_rand,
        fuel.diesel_50ppm_gauteng_change_rand,
        cpi.cpi_headline_index,
        cpi.cpi_headline_yoy_pct,
        weather.cape_town_avg_max_temp_c,
        weather.cape_town_rain_mm
    from months
    left join usd_zar using (month_start)
    left join fuel    using (month_start)
    left join cpi     using (month_start)
    left join weather using (month_start)

)

select
    *,
    -- fuel prices are set from the previous month's rand and oil prices, so line up
    -- this month's pump change with LAST month's rand move
    lag(usd_zar_change_pct) over (order by month_start)  as usd_zar_change_pct_prev_month
from combined
