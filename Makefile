.PHONY: install sync test coverage run docker-build docker-run train drift dvc-repro notebooks helm-template verify-local clean module2-ingestion module2-lake module2-batch module2-analytics module2-streaming module2-stop module2-ps

install sync:
	uv sync --all-extras

test:
	uv run pytest src/tests --cov=src/preprocessing_api --cov-report=term-missing --cov-fail-under=81

coverage: test

run:
	uv run uvicorn --app-dir src preprocessing_api.main:app --host 0.0.0.0 --port 8000 --reload

docker-build:
	docker build -t cognitive-load-api:local .

docker-run:
	docker run --rm -p 8000:8000 cognitive-load-api:local

train:
	uv run --extra dev python scripts/train_model.py --input data/raw/sample_data.csv --output models/cognitive_load_model.joblib

drift:
	uv run --extra dev python scripts/generate_drift_report.py --reference data/processed/train.csv --current data/processed/test.csv --output reports/evidently/data_drift.html

dvc-repro:
	uv run --extra dev dvc repro

notebooks:
	@for notebook in notebooks/*.ipynb; do uv run jupyter nbconvert --to notebook --execute --inplace --ExecutePreprocessor.kernel_name=python3 --ExecutePreprocessor.timeout=180 "$$notebook"; done

verify-local:
	uv run ruff check src scripts
	$(MAKE) test
	$(MAKE) dvc-repro
	$(MAKE) notebooks
	$(MAKE) helm-template

helm-template:
	helm template cognitive-load-monitor ./helm/cognitive-load-monitor --namespace cognitive-load

clean:
	rm -rf .pytest_cache .ruff_cache htmlcov coverage.xml .coverage

module2-ingestion:
	docker compose -f infra/module2/docker-compose.yml --profile ingestion up -d

module2-lake:
	docker compose -f infra/module2/docker-compose.yml --profile lake up -d

module2-batch:
	docker compose -f infra/module2/docker-compose.yml --profile lake --profile batch up -d

module2-analytics:
	docker compose -f infra/module2/docker-compose.yml --profile lake --profile analytics up -d

module2-streaming:
	docker compose -f infra/module2/docker-compose.yml --profile ingestion --profile streaming up -d

module2-stop:
	docker compose -f infra/module2/docker-compose.yml --profile ingestion --profile lake --profile batch --profile analytics --profile orchestration --profile streaming stop

module2-ps:
	docker compose -f infra/module2/docker-compose.yml --profile ingestion --profile lake --profile batch --profile analytics --profile orchestration --profile streaming ps -a
