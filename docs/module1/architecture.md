# Module I architecture

```mermaid
flowchart LR
  UI[FastAPI demo] --> API[/predict]
  API --> MODE{INFERENCE_MODE}
  MODE --> RULE[demo rule]
  MODE --> LOCAL[exact local model]
  MODE --> KS[KServe]
  FEAT[shared feature_vector] --> LOCAL
  FEAT --> KS
  DATA[seeded synthetic_proxy CSV] --> DVC[DVC stages]
  DVC --> TRAIN[dummy / logistic / random forest]
  TRAIN --> MF[MLflow run + immutable version]
  MF --> IMG[locked Docker image]
  TEST[GitHub test] --> BUILD[automatic build]
  BUILD --> DEPLOY[workflow_dispatch + protected environment]
```

Graphify baseline/final: 202→281 nodes, 319→419 edges, 18→24 communities. Final god nodes include `CognitiveLoadLevel`, `predict`, `PredictionRequest`, both model clients and `feature_vector`. The shared feature function removed train/serve/notebook ratio duplication; explicit mode branches keep backend failure behavior visible in `main.predict`. Remaining coupling there is intentional orchestration. Semantic community naming was unavailable without a Gemini key, and Terraform extraction was unavailable without its optional HCL parser.

Module II must preserve these stable contracts:

- `POST /predict`: four bounded input fields plus optional `feature_as_of`; output includes `cognitive_load_level`, `inference_source`, optional `model_version`, `feature_as_of`, and `is_fallback=false`.
- Model features, in exact order: `focus_minutes`, `distraction_minutes`, `tasks_due`, `hours_to_deadline`, `focus_ratio`, `distraction_ratio`.
- Levels are exactly `LOW`, `MEDIUM`, `HIGH`; label provenance is `synthetic_proxy` until a separately governed real label source exists.
- Production modes are `local_model` and `kserve`; an unavailable backend returns a 5xx and must never substitute the demonstration rule.
- Module II event schemas should carry a version, event time, feature time and model provenance rather than changing this synchronous API implicitly.
