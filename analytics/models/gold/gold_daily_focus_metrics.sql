{{ config(materialized='incremental', unique_key='event_date', incremental_strategy='merge') }}

select
  event_date,
  count(*) as event_count,
  avg(focus_ratio) as average_focus_ratio,
  sum(focus_minutes) as focus_minutes
from {{ ref('stg_session_features') }}
group by event_date
