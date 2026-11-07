-- One row per day per currency: how many rand one unit of that currency costs.
with source as (

    select * from {{ source('raw', 'fx_rates') }}

),

renamed as (

    select
        rate_date,
        base_currency           as currency_code,
        rate::numeric(12, 4)    as zar_per_unit,
        _loaded_at              as loaded_at
    from source
    where quote_currency = 'ZAR'

)

select * from renamed
