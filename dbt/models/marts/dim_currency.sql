select
    currency_code,
    currency_name,
    currency_symbol
from {{ ref('currencies') }}
