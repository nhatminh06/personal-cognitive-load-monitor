{{ config(materialized='incremental', unique_key='session_id', incremental_strategy='merge') }}

select
  session_id,
  max(event_time) as latest_event_time,
  count(*) as event_count,
  avg(focus_ratio) as average_focus_ratio,
  avg(distraction_ratio) as average_distraction_ratio
from {{ ref('stg_session_features') }}
group by session_id
