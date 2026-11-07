{{
    config(
        materialized='incremental',
        unique_key=['weather_date', 'location'],
        incremental_strategy='delete+insert'
    )
}}
-- One row per day per location. Incremental, like fct_fx_daily.

select
    weather_date,
    location,
    temp_max_c,
    temp_min_c,
    temp_mean_c,
    rain_mm,
    wind_max_kmh
from {{ ref('stg_weather_daily') }}

{% if is_incremental() %}
where weather_date >= (select max(weather_date) - 7 from {{ this }})
{% endif %}
