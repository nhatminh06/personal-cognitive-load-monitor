{{ config(materialized='incremental', unique_key='event_date', incremental_strategy='merge') }}

select
  event_date,
  avg(distraction_ratio) as average_distraction_ratio,
  sum(distraction_minutes) as distraction_minutes
from {{ ref('stg_session_features') }}
group by event_date
