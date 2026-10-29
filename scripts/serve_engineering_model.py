"""Run the existing KServe adapter with a synthetic-only local package."""

from __future__ import annotations

import argparse

from kserve.model_server import ModelServer, parser

from cogniflow_kserve.engineering import validated_engineering_manifest
from cogniflow_kserve.predictor import CogniFlowPredictor
from cogniflow_kserve import server
from cogniflow_kserve.server import CogniFlowModel
from preprocessing_api.security import is_production


def main() -> None:
    argument_parser = argparse.ArgumentParser(parents=[parser])
    argument_parser.add_argument("--allow-synthetic-engineering", action="store_true")
    args, _ = argument_parser.parse_known_args()
    if not args.allow_synthetic_engineering or is_production():
        raise RuntimeError("synthetic engineering server requires explicit non-production mode")
    predictor = CogniFlowPredictor(manifest_validator=validated_engineering_manifest)
    model = CogniFlowModel(args.model_name, predictor=predictor)
    model.load()
    server.model = model
    ModelServer().start([model])


if __name__ == "__main__":
    main()
