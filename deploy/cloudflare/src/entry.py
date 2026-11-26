import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "vendor"))

from workers import asgi
from app import application

Default = asgi.entrypoint(application)
