-- One row per CPI series per month. A full rebuild each run: Stats SA can revise
-- and re-base the whole history in a new release, so incremental would be unsafe.
select
    series_code,
    series_name,
    series_detail,
    area,
    period_month,
    index_value,
    yoy_inflation_pct,
    mom_change_pct
from {{ ref('int_cpi_inflation') }}
