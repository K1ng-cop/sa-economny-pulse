-- One row per price change per region per product, in rand.
with source as (

    select * from {{ source('raw', 'fuel_prices') }}

),

renamed as (

    select
        effective_date,
        region,
        product                 as product_name,
        case product
            when '95 ULP'                   then 'petrol_95_ulp'
            when '95 LRP'                   then 'petrol_95_lrp'
            when '93 ULP'                   then 'petrol_93_ulp'
            when '93 LRP'                   then 'petrol_93_lrp'
            when 'Diesel 0.05%'             then 'diesel_500ppm'
            when 'Diesel 0.005%'            then 'diesel_50ppm'
            when 'Illuminating Paraffin'    then 'paraffin'
            when 'Liquefied Petroleum Gas'  then 'lpg'
            else 'unmapped'  -- fails the accepted_values test, so a new label never slips through
        end                     as product_code,
        case unit
            when 'c/l'  then 'litre'
            when 'c/kg' then 'kg'
        end                     as price_unit,
        price_cents,
        (price_cents / 100.0)::numeric(8, 3)  as price_rand,
        _loaded_at              as loaded_at
    from source

)

select * from renamed
