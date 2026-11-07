{{
    config(
        materialized='incremental',
        unique_key=['rate_date', 'currency_code'],
        incremental_strategy='delete+insert'
    )
}}
-- One row per day per currency. Incremental: each run only reprocesses recent days.

select
    rate_date,
    currency_code,
    zar_per_unit,
    is_filled
from {{ ref('int_fx_rates_filled') }}

{% if is_incremental() %}
-- {{ this }} is this table as it already exists. Reprocess the last 7 days so late
-- corrections and newly filled weekend days are picked up; older rows are left alone.
where rate_date >= (select max(rate_date) - 7 from {{ this }})
{% endif %}
