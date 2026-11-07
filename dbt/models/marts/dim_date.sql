-- One row per calendar day, from the start of the CPI history to the end of next year.
with days as (

    select generate_series(
        '2008-01-01'::date,
        (date_trunc('year', current_date) + interval '2 years' - interval '1 day')::date,
        interval '1 day'
    )::date as date_day

)

select
    date_day,
    date_trunc('month', date_day)::date         as month_start,
    extract(year from date_day)::int            as year,
    extract(quarter from date_day)::int         as quarter,
    extract(month from date_day)::int           as month,
    to_char(date_day, 'Mon')                    as month_name,
    to_char(date_day, 'YYYY-MM')                as year_month,
    extract(isodow from date_day)::int          as day_of_week,  -- 1 = Monday
    to_char(date_day, 'Dy')                     as day_name,
    extract(isodow from date_day) in (6, 7)     as is_weekend
from days
