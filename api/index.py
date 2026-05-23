import os
import sys

# Ensure project root is importable in Vercel's serverless runtime.
CURRENT_DIR = os.path.dirname(__file__)
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
	sys.path.insert(0, PROJECT_ROOT)

from app import app

# Vercel Python runtime expects a module-level `app`.
