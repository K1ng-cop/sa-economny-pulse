-- Cape Town weather within physically believable limits.
select weather_date, location, temp_min_c, temp_max_c, rain_mm
from {{ ref('stg_weather_daily') }}
where temp_max_c not between -5 and 45
   or temp_min_c not between -10 and 40
   or rain_mm    not between 0 and 300
   or temp_min_c > temp_max_c
