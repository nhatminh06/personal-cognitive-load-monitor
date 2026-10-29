"""KServe ModelServer adapter for the verified CogniFlow predictor."""

from __future__ import annotations

import argparse
from typing import Any

from fastapi import HTTPException
from kserve.errors import InvalidInput
from kserve.model import Model
from kserve.model_server import ModelServer, app, parser

from cogniflow_kserve.predictor import CogniFlowPredictor


class CogniFlowModel(Model):
    def __init__(self, name: str, predictor: CogniFlowPredictor | None = None) -> None:
        super().__init__(name)
        self.predictor = predictor or CogniFlowPredictor()

    def load(self) -> bool:
        self.ready = self.predictor.load()
        return self.ready

    def predict(
        self,
        payload: dict[str, Any],
        headers: dict[str, str] | None = None,
        response_headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        try:
            return self.predictor.predict(payload)
        except ValueError as exc:
            raise InvalidInput(str(exc)) from exc


model: CogniFlowModel | None = None


@app.get("/v1/models/{model_name}/metadata")
async def metadata(model_name: str) -> dict[str, Any]:
    if model is None or model_name != model.name or not model.ready or model.predictor.provenance is None:
        raise HTTPException(status_code=503, detail="verified model provenance is unavailable")
    return model.predictor.provenance


def main() -> None:
    global model
    argument_parser = argparse.ArgumentParser(parents=[parser])
    args, _ = argument_parser.parse_known_args()
    model = CogniFlowModel(args.model_name)
    model.load()
    ModelServer().start([model])


if __name__ == "__main__":
    main()
