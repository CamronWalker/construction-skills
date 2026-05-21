import sys
from pathlib import Path

HERE = Path(__file__).resolve()
CHARTS_PKG = HERE.parent.parent   # .../charts/
sys.path.insert(0, str(CHARTS_PKG.parent))  # parent of charts/ so `from charts import render` works
