"""Compatibility import for the qualified G1B.4 test harness."""

import importlib.util
from pathlib import Path

source = Path(__file__).resolve().parents[2] / "gateway" / "kafka_gateway.py"
spec = importlib.util.spec_from_file_location("cogniflow_https_gateway", source)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
KafkaGateway = module.KafkaGateway
