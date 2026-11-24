"""Point d'entrée CLI de la pipeline Ligue des Champions.

Exemples :
    python main.py
    python main.py --source clubelo
    python main.py --source beyondelo --n-sims 500000
    python main.py --source manual --elo-file mon_elo.json
"""
from __future__ import annotations

import sys
from pathlib import Path

# Permet d'importer `ldc` directement depuis `src/` sans installation préalable.
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from ldc.pipeline import main

if __name__ == "__main__":
    raise SystemExit(main())
