-- One row per CPI series: what each Stats SA series code means.
with source as (

    select * from {{ source('raw', 'cpi_series') }}

),

renamed as (

    select
        h03             as series_code,
        h04             as series_name,
        h05             as series_detail,
        h06             as series_detail_2,
        h13             as area,
        h17             as unit,
        h18             as base_period,
        release_period,
        _loaded_at      as loaded_at
    from source

)

select * from renamed
