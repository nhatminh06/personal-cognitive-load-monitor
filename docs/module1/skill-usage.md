# Skill usage

- **Ponytail (installed, full):** reused FastAPI, existing scripts and Helm; added one shared feature module; avoided React, an auth service, and new dependencies. Removed the generated-secret path rather than adding secret-management code.
- **Graphify (installed, 0.9.92):** `update`, `cluster-only`, god-node and impact queries produced a final code graph of 281 nodes, 419 edges and 24 communities. Semantic labels were unavailable because no Gemini key was configured. Terraform parsing was unavailable because the optional HCL parser is not installed. Direct inspection supplemented YAML/notebook lineage.
- **UI/UX Pro Max (not installed):** no output was invented and no unapproved installation occurred. The demo applies the requested accessible professional design directly.

Graph findings: feature calculations had been duplicated between `model_client.py`, `train_model.py`, and notebook 02; `features.feature_vector` is now their single contract. `main.predict` remains a high-connectivity orchestration point because it deliberately selects and reports one backend. CI connects tests to image build and a gated `workflow_dispatch` deploy. No further split was justified for Module I.
