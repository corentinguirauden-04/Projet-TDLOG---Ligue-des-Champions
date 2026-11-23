"""Point d'entrée du serveur web interactif Ligue des Champions.

Exemples :
    python web_app.py
    python web_app.py --host 0.0.0.0 --port 8080
"""
from __future__ import annotations

import sys
from pathlib import Path

# Permet d'importer `ldc` directement depuis `src/` sans installation préalable.
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from ldc.web_server import main

if __name__ == "__main__":
    raise SystemExit(main())
