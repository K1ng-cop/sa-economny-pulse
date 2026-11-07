-- One row per day per location, with short, unit-labelled column names.
with source as (

    select * from {{ source('raw', 'weather_daily') }}

),

renamed as (

    select
        weather_date,
        location,
        latitude,
        longitude,
        temperature_2m_max::numeric(4, 1)   as temp_max_c,
        temperature_2m_min::numeric(4, 1)   as temp_min_c,
        temperature_2m_mean::numeric(4, 1)  as temp_mean_c,
        precipitation_sum::numeric(6, 1)    as rain_mm,
        wind_speed_10m_max::numeric(5, 1)   as wind_max_kmh,
        _loaded_at                          as loaded_at
    from source

)

select * from renamed
