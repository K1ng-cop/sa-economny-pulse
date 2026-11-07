-- CPI index values with their labels, plus year-on-year inflation and the monthly change.
with cpi_values as (

    select * from {{ ref('stg_cpi_values') }}

),

cpi_series as (

    select * from {{ ref('stg_cpi_series') }}

),

labelled as (

    select
        cpi_values.series_code,
        cpi_series.series_name,
        cpi_series.series_detail,
        cpi_series.area,
        cpi_values.period_month,
        cpi_values.index_value
    from cpi_values
    inner join cpi_series using (series_code)

)

select
    this_month.*,
    year_ago.index_value                                                        as index_value_year_ago,
    round((this_month.index_value / nullif(year_ago.index_value, 0) - 1) * 100, 1)   as yoy_inflation_pct,
    round((this_month.index_value / nullif(last_month.index_value, 0) - 1) * 100, 1) as mom_change_pct
from labelled as this_month
-- joining on the actual date (not lag(..., 12)) stays correct even if a month is missing
left join labelled as year_ago
    on  year_ago.series_code = this_month.series_code
    and year_ago.period_month = (this_month.period_month - interval '1 year')::date
left join labelled as last_month
    on  last_month.series_code = this_month.series_code
    and last_month.period_month = (this_month.period_month - interval '1 month')::date
