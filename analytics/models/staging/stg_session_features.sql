select * from {{ source('silver', 'session_features') }}
