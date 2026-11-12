"""Génère les graphiques de qualification pour toutes les équipes.

À lancer depuis le dossier du projet :
    python generate_outputs.py
    python generate_outputs.py 100000

Le nombre de simulations est de 20 000 par défaut. Les images sont enregistrées
localement dans outputs/ et un CSV contient les probabilités exactes par place.
"""
from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

import ldc_sim as sim_engine
import ldc_viz as viz


BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "outputs"
TEAM_OUTPUT_DIR = OUTPUT_DIR / "equipes"
DEFAULT_N_SIMS = 20_000
SEED = 42


def safe_filename(team: str) -> str:
    """Transforme un nom d'équipe en nom de fichier Windows-compatible."""
    name = team.lower().replace("/", "-")
    name = re.sub(r"[^a-z0-9_-]+", "_", name)
    return name.strip("_") or "equipe"


def write_probabilities_csv(sim, rank_dist, qualifications, path: Path) -> None:
    """Écrit les indicateurs de qualification et la proba de chaque place."""
    fieldnames = [
        "equipe",
        "probabilite_top8",
        "probabilite_top24",
        "probabilite_barrages_9_24",
        "probabilite_elimination_25_36",
        "points_finaux_moyens",
    ] + [f"probabilite_place_{place}" for place in range(1, sim_engine.N_TEAMS + 1)]

    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()
        for team_index, team in enumerate(sim["teams"]):
            q = qualifications[team]
            row = {
                "equipe": team,
                "probabilite_top8": q["top8"],
                "probabilite_top24": q["top24"],
                "probabilite_barrages_9_24": q["playoff"],
                "probabilite_elimination_25_36": q["out"],
                "points_finaux_moyens": q["exp_pts"],
            }
            for place, probability in enumerate(rank_dist[team_index], start=1):
                row[f"probabilite_place_{place}"] = probability
            writer.writerow(row)


def main() -> int:
    try:
        n_sims = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_N_SIMS
    except ValueError:
        print("Erreur : indique un nombre entier de simulations, par exemple 20000.")
        return 2

    if n_sims <= 0:
        print("Erreur : le nombre de simulations doit être strictement positif.")
        return 2

    # Vérification des données avant de lancer les calculs.
    if not sim_engine.TEAMS:
        print("Erreur : aucune équipe n'a été chargée depuis ldc_data.py.")
        return 1

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    TEAM_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Lancement de {n_sims:,} simulations pour {len(sim_engine.TEAMS)} équipes...".replace(",", " "))
    simulation = sim_engine.simulate(n_sims=n_sims, seed=SEED)

    # Ces deux calculs sont effectués une seule fois puis réutilisés pour les 36 fiches.
    rank_dist = sim_engine.rank_distribution(simulation)
    qualifications = sim_engine.qualification_probs(simulation)
    current_table = sim_engine.current_table()

    # Une fiche PNG par équipe.
    for index, team in enumerate(sim_engine.TEAMS, start=1):
        image_path = TEAM_OUTPUT_DIR / f"{safe_filename(team)}.png"
        viz.team_card(
            team,
            simulation,
            current_table,
            image_path,
            n_sims=n_sims,
            rank_dist=rank_dist,
            qualifications=qualifications,
        )
        print(f"[{index:02d}/{len(sim_engine.TEAMS)}] Graphique créé : {image_path.name}")

    # Vue d'ensemble facultative mais pratique pour comparer les équipes.
    overview_path = OUTPUT_DIR / "classement_global.png"
    viz.overview(simulation, current_table, overview_path)

    # Tableau CSV avec les valeurs exactes, y compris les probabilités des 36 places.
    csv_path = OUTPUT_DIR / "probabilites_equipes.csv"
    write_probabilities_csv(simulation, rank_dist, qualifications, csv_path)

    print("\nTerminé !")
    print(f"Équipes traitées : {len(sim_engine.TEAMS)}")
    print(f"Graphiques individuels : {TEAM_OUTPUT_DIR}")
    print(f"Vue d'ensemble : {overview_path}")
    print(f"Probabilités détaillées (CSV) : {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
