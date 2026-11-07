select
    product_code,
    product_name,
    fuel_type,
    grade,
    price_basis
from {{ ref('fuel_products') }}
