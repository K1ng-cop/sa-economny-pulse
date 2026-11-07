-- Rand per unit should be between R5 and R50 for USD, EUR and GBP.
-- Anything outside that is almost certainly a bad value, not a real market move.
-- A singular test passes when this query returns no rows.
select rate_date, currency_code, zar_per_unit
from {{ ref('stg_fx_rates') }}
where zar_per_unit not between 5 and 50
