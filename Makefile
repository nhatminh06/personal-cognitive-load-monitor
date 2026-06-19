.PHONY: install sync test coverage run docker-build docker-run train drift dvc-repro helm-template clean

install sync:
	uv sync --all-extras

test:
	uv run pytest src/tests --cov=src/preprocessing_api --cov-report=term-missing --cov-fail-under=80

coverage: test

run:
	uv run uvicorn preprocessing_api.main:app --host 0.0.0.0 --port 8000 --reload

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

helm-template:
	helm template cognitive-load-monitor ./helm/cognitive-load-monitor --namespace cognitive-load

clean:
	rm -rf .pytest_cache .ruff_cache htmlcov coverage.xml .coverage
