"""Shared test setup — make ``app`` importable when running from the repo root.

test_runtime_readiness.py / test_auth_guards.py do ``from app.main import app``;
pytest only auto-inserts the service root when invoked from inside it.
"""

import os
import sys

SERVICE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SERVICE_ROOT not in sys.path:
    sys.path.insert(0, SERVICE_ROOT)
