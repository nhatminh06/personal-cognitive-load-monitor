{{ config(materialized='incremental', unique_key='session_id', incremental_strategy='merge') }}

select
  session_id,
  avg(tasks_due) as average_tasks_due,
  min(hours_to_deadline) as nearest_deadline_hours,
  avg(focus_ratio) as average_focus_ratio
from {{ ref('stg_session_features') }}
group by session_id
