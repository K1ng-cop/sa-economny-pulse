-- One row per calendar day per currency. Weekends and public holidays have no published
-- rate, so they carry the last known rate forward and are flagged with is_filled = true.
with rates as (

    select * from {{ ref('stg_fx_rates') }}

),

calendar as (

    select generate_series(min(rate_date), max(rate_date), interval '1 day')::date as rate_date
    from rates

),

currencies as (

    select distinct currency_code from rates

),

grid as (

    -- every day x every currency, whether a rate was published or not
    select calendar.rate_date, currencies.currency_code
    from calendar
    cross join currencies

),

with_gaps as (

    select
        grid.rate_date,
        grid.currency_code,
        rates.zar_per_unit,
        -- count() skips nulls, so this only goes up on days that HAVE a rate.
        -- Each published rate starts a group that the gap days after it join.
        count(rates.zar_per_unit) over (
            partition by grid.currency_code
            order by grid.rate_date
        ) as rate_group
    from grid
    left join rates
        on  rates.rate_date = grid.rate_date
        and rates.currency_code = grid.currency_code

)

select
    rate_date,
    currency_code,
    first_value(zar_per_unit) over (
        partition by currency_code, rate_group
        order by rate_date
    )                           as zar_per_unit,
    zar_per_unit is null        as is_filled
from with_gaps
