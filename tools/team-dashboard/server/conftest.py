"""
pytest conftest — adds server directory to sys.path so tests can import
modules directly (e.g. `from transcript_parser import ...`).

The `tools/team-dashboard/` path contains a dash, which is invalid in Python
package names, so we use path-based imports rather than package imports.
"""

import sys
from pathlib import Path

# Add the server directory to sys.path so tests can import directly
SERVER_DIR = Path(__file__).parent
sys.path.insert(0, str(SERVER_DIR))
