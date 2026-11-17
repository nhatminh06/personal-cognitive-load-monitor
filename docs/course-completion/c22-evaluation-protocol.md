# C2.2 evaluation protocol — declared before candidate evaluation

Protocol `feature_groups_v1`, fixed hash-order seed 42. For each row derive the
canonical six-feature vector with `feature_vector`; encode normalized floats as
compact JSON (normalize signed zero), then SHA-256 those bytes. This group key
excludes labels, IDs and time. Identical canonical vectors must stay together.
Reject conflicting labels within a group. Within each label, sort group keys by
SHA-256 of `42:` plus the group key; allocate floor(60%) to train, through
floor(80%) to validation, and the rest to final test. Require at least three
unique groups per class and all three classes. Record actual rows/classes,
explicit row-index membership and a digest binding the protocol, dataset and
membership. Input remains chronologically stored, but this split is group-held-out,
not a future-time forecast. Preserve legacy chronological manifests for auditing.

Candidates: majority most-frequent; train-fitted StandardScaler + logistic
regression (seed 42, max_iter 1000); balanced random forest (seed 42, 200 trees).
All use identical partitions/features and no tuning. Primary selection metric:
validation macro-F1; secondary: validation accuracy; exact ties prefer majority,
then logistic regression, then random forest. This is the existing Module I
simple-to-complex policy, shared across local and KFP callers. Invalid/nonfinite
metrics fail closed. Freeze selection before computing final-test metrics for
only the winner; never select or tune from final-test results.

Report feature-group overlap (must be zero), actual row/class/group counts,
selection/tie evidence and exact accuracy/macro-F1. Determinism and tampered or
overlapping membership have regression tests. Repeated latent synthetic label
rules still prevent claims about real people or independent scientific validity.
No approval or deployment follows automatically from any measured score.
