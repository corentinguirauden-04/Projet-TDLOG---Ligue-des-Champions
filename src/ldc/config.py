"""Configuration centrale, chemins et constantes partagées du projet.

Regroupe en un seul point de vérité les répertoires (`DATA_DIR`, `OUTPUTS_DIR`,
`WEB_DIR`) et les paramètres par défaut utilisés par l'ensemble des couches
(ingestion, simulation, visualisation, pipeline et serveur web).
"""
from __future__ import annotations

import os
from pathlib import Path

# Chemins racine du dépôt (indépendants du répertoire courant d'exécution).
ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "data"
OUTPUTS_DIR = ROOT_DIR / "outputs"
WEB_DIR = ROOT_DIR / "web"

ELO_FILE = DATA_DIR / "elo.json"
CLUBELO_HTML_FILE = DATA_DIR / "clubelo_ranking.html"
LIVE_MATCHES_FILE = DATA_DIR / "live_matches.json"
CUSTOM_ELO_FILE = OUTPUTS_DIR / "manual" / "custom_elo.json"

# Sources Elo exposées par la pipeline et l'interface web.
SOURCES = ("clubelo", "beyondelo", "manual")
SOURCE_LABELS = {
    "clubelo": "ClubElo",
    "beyondelo": "beyondELO",
    "manual": "Personnalisé",
}

# Paramètres du modèle et des simulations Monte Carlo.
DEFAULT_N_SIMS = 500_000
MIN_N_SIMS = 100
MAX_N_SIMS = 1_000_000
DEFAULT_SEED = 42
HOME_BONUS = 100
K_ELO = 20

# Bornes de validation des notes Elo.
MIN_ELO = 500
MAX_ELO = 3000

# Endpoints et clé API (surchargeable via variable d'environnement).
CLUBELO_RANKING_URL = "https://clubelo.com/Ranking"
# Clé beyondELO avec valeur par défaut dans le dépôt (comme auparavant).
BEYONDELO_API_KEY = os.environ.get(
    "BEYONDELO_API_KEY",
    "be_53JJFu4692fXmqaSUFz7ykzKlEOHrRlcDpUP3eZrj-s",
).strip()
FOOTBALL_DATA_API_TOKEN = os.environ.get("FOOTBALL_DATA_API_TOKEN", "").strip()
LIVE_MATCH_POLL_SECONDS = 300  # 5 minutes
LIVE_AUTO_N_SIMS = DEFAULT_N_SIMS
