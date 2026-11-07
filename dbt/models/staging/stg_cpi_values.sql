-- One row per CPI series per month.
with source as (

    select * from {{ source('raw', 'cpi_values') }}

),

renamed as (

    select
        h03                     as series_code,
        period                  as period_month,
        value::numeric(8, 1)    as index_value,
        _loaded_at              as loaded_at
    from source

)

select * from renamed
