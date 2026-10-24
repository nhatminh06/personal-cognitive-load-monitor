{{ config(materialized='incremental', unique_key=['session_id', 'event_time'], incremental_strategy='merge') }}

select
  session_id,
  event_time,
  tasks_due,
  hours_to_deadline,
  tasks_due / greatest(hours_to_deadline, 1.0) as tasks_per_deadline_hour
from {{ ref('stg_session_features') }}
