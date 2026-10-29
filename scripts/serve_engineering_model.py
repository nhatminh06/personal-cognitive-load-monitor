"""Run the existing KServe adapter with a synthetic-only local package."""

from __future__ import annotations

import argparse
from http import HTTPStatus

from fastapi.responses import JSONResponse
from kserve.model_server import ModelServer, parser
from kserve.protocol.rest import server as rest_server

from cogniflow_kserve.engineering import validated_engineering_manifest
from cogniflow_kserve.predictor import CogniFlowPredictor
from cogniflow_kserve import server
from cogniflow_kserve.server import CogniFlowModel
from preprocessing_api.security import is_production
from preprocessing_api.observability import configure_logging, configure_tracing


async def _invalid_input_handler(_, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=HTTPStatus.BAD_REQUEST, content={"error": str(exc)})


def main() -> None:
    configure_logging()
    argument_parser = argparse.ArgumentParser(parents=[parser])
    argument_parser.add_argument("--allow-synthetic-engineering", action="store_true")
    args, _ = argument_parser.parse_known_args()
    if not args.allow_synthetic_engineering or is_production():
        raise RuntimeError("synthetic engineering server requires explicit non-production mode")
    predictor = CogniFlowPredictor(manifest_validator=validated_engineering_manifest)
    model = CogniFlowModel(args.model_name, predictor=predictor)
    model.load()
    server.model = model
    rest_server.invalid_input_handler = _invalid_input_handler
    configure_tracing(server.app, service_name="cognitive-load-kserve")
    ModelServer().start([model])


if __name__ == "__main__":
    main()
