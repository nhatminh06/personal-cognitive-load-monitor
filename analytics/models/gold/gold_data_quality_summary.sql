{{ config(materialized='incremental', unique_key='latest_ingestion', incremental_strategy='merge') }}

select
  count(*) as accepted_rows,
  count_if(event_time < current_timestamp - interval '7' day) as stale_rows,
  max(ingested_at) as latest_ingestion,
  current_timestamp as measured_at
from {{ ref('stg_session_features') }}
