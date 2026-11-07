{#
  Fails when the latest day has far fewer rows than the days before it - a sign that a
  source partly failed (e.g. one currency or location missing) without any error.

  Usage in a .yml file:
    data_tests:
      - daily_row_count_drift:
          arguments:
            date_column: rate_date
            max_drop_pct: 50     # optional, default 50
            lookback_days: 7     # optional, default 7
#}
{% test daily_row_count_drift(model, date_column, max_drop_pct=50, lookback_days=7) %}

with daily_counts as (

    select {{ date_column }} as day, count(*) as row_count
    from {{ model }}
    group by 1

),

latest_day as (

    select max(day) as day from daily_counts

),

baseline as (

    select avg(daily_counts.row_count) as avg_row_count
    from daily_counts, latest_day
    where daily_counts.day <  latest_day.day
      and daily_counts.day >= latest_day.day - {{ lookback_days }}

)

-- a test passes when it returns no rows
select
    latest_day.day          as latest_day,
    daily_counts.row_count  as latest_row_count,
    baseline.avg_row_count  as baseline_avg
from latest_day
join daily_counts on daily_counts.day = latest_day.day
cross join baseline
where daily_counts.row_count < baseline.avg_row_count * (1 - {{ max_drop_pct }} / 100.0)

{% endtest %}
