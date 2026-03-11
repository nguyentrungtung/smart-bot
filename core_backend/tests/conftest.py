import sys
import os

# Ensure the root /app is in sys.path for the container environment
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
