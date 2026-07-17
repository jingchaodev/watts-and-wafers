"""Put collectors/ on sys.path so `import vast`, `import composite`, etc. work
regardless of the cwd pytest is invoked from (repo root per README: `python3
-m pytest collectors/tests -q`)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
