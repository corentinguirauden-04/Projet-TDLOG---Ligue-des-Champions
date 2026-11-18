"""Génère les graphiques de qualification pour toutes les équipes.

À lancer depuis le dossier du projet :
    python generate_outputs.py --source clubelo                          # utilise clubelo (HTML local ou API si elo.json absent/autre source)
    python generate_outputs.py --source beyondelo                        # récupère les Elo beyondELO si besoin (dernier JSON ne provenant pas de beyondELO) 
    python generate_outputs.py --source beyondelo 100000 --date 2026-10-01  # 100 000 sim. avec les Elo beyondELO du 2026-10-01
    python generate_outputs.py --source beyondelo --refresh              # force le re-téléchargement depuis l'API beyondELO
    python generate_outputs.py --source manual                           # utilise DEFAULT_ELO de ldc_data.py -> outputs/manual/
    python generate_outputs.py --source manual --elo-file mon_elo.json   # utilise un fichier JSON personnalisé -> outputs/manual/

Le nombre de simulations est de 20 000 par défaut. Les images et le CSV sont
enregistrés dans outputs/<source>/ (equipes/<equipe>/, classement_global.png,
seuils_points_top_8_16_24.png, probabilites_equipes.csv).
"""
from __future__ import annotations

import argparse
import csv
import importlib
import json
import re
import sys
from pathlib import Path

import ldc_elo


BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "outputs"
ELO_FILE = BASE_DIR / "elo.json"
DEFAULT_N_SIMS = 20_000
SEED = 42


def _ensure_elo_source(
    source: str,
    date: str | None = None,
    refresh: bool = False,
    elo_file: Path | None = None,
) -> int:
    """Met à jour elo.json depuis la source demandée si nécessaire."""
    if source == "manual":
        import datetime as dt
        import ldc_data

        if elo_file is not None:
            raw = json.loads(elo_file.read_text(encoding="utf-8"))
            manual_elo = raw["elo"] if isinstance(raw, dict) and "elo" in raw else raw
            if not isinstance(manual_elo, dict) or set(manual_elo) != set(ldc_data.DEFAULT_ELO):
                print(
                    "Erreur : le fichier Elo manuel doit contenir exactement les 36 équipes attendues.",
                    file=sys.stderr,
                )
                return 1
        else:
            manual_elo = ldc_data.DEFAULT_ELO

        payload = {
            "date": date or dt.date.today().isoformat(),
            "source": "manual",
            "elo": {team: int(round(float(val))) for team, val in manual_elo.items()},
        }
        temp_path = ELO_FILE.with_suffix(".json.tmp")
        temp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        temp_path.replace(ELO_FILE)
        importlib.reload(ldc_data)
        return 0

    needs_fetch = refresh or date is not None or not ELO_FILE.exists()
    if not needs_fetch:
        try:
            current = json.loads(ELO_FILE.read_text(encoding="utf-8"))
            needs_fetch = current.get("source") != source
        except Exception:
            needs_fetch = True

    if not needs_fetch:
        return 0

    elo_args = ["--source", source]
    if date is not None:
        elo_args.append(date)
    status = ldc_elo.main(elo_args)
    if status == 0 and "ldc_data" in sys.modules:
        importlib.reload(sys.modules["ldc_data"])
    return status


def safe_filename(team: str) -> str:
    """Transforme un nom d'équipe en nom de fichier Windows-compatible."""
    name = team.lower().replace("/", "-")
    name = re.sub(r"[^a-z0-9_-]+", "_", name)
    return name.strip("_") or "equipe"


def write_probabilities_csv(sim, rank_dist, qualifications, path: Path, n_teams: int) -> None:
    """Écrit les indicateurs de qualification et la proba de chaque place."""
    fieldnames = [
        "equipe",
        "probabilite_top8",
        "probabilite_top24",
        "probabilite_barrages_9_24",
        "probabilite_elimination_25_36",
        "points_finaux_moyens",
    ] + [f"probabilite_place_{place}" for place in range(1, n_teams + 1)]

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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Génère les graphiques et probabilités de qualification."
    )
    parser.add_argument(
        "n_sims",
        nargs="?",
        type=int,
        default=DEFAULT_N_SIMS,
        help="Nombre de simulations Monte Carlo (défaut : 20000).",
    )
    parser.add_argument(
        "-s",
        "--source",
        choices=("html", "clubelo", "beyondelo", "manual"),
        default="html",
        help="Source Elo utilisée pour la simulation et le sous-dossier de sortie (défaut : html).",
    )
    parser.add_argument(
        "--elo-file",
        type=Path,
        default=None,
        help="Fichier JSON d'Elo personnalisé (utilisé avec --source manual).",
    )
    parser.add_argument(
        "--date",
        default=None,
        help="Date historique (AAAA-MM-JJ) à récupérer depuis l'API.",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Force le re-téléchargement de elo.json depuis la source choisie.",
    )
    args = parser.parse_args(argv)
    n_sims: int = args.n_sims

    if n_sims <= 0:
        print("Erreur : le nombre de simulations doit être strictement positif.")
        return 2

    status = _ensure_elo_source(
        args.source,
        date=args.date,
        refresh=args.refresh,
        elo_file=args.elo_file,
    )
    if status != 0:
        return status

    # Import tardif afin que ldc_data lise le elo.json mis à jour ci-dessus.
    import ldc_sim as sim_engine
    import ldc_viz as viz

    # Vérification des données avant de lancer les calculs.
    if not sim_engine.TEAMS:
        print("Erreur : aucune équipe n'a été chargée depuis ldc_data.py.")
        return 1

    output_dir = OUTPUT_DIR / args.source
    team_output_dir = output_dir / "equipes"
    output_dir.mkdir(parents=True, exist_ok=True)
    team_output_dir.mkdir(parents=True, exist_ok=True)

    print(
        f"Lancement de {n_sims:,} simulations ({args.source}) "
        f"pour {len(sim_engine.TEAMS)} équipes...".replace(",", " ")
    )
    simulation = sim_engine.simulate(n_sims=n_sims, seed=SEED)

    # Ces calculs sont effectués une seule fois puis réutilisés pour les 36 fiches.
    rank_dist = sim_engine.rank_distribution(simulation)
    qualifications = sim_engine.qualification_probs(simulation)
    importance = sim_engine.match_importance(simulation)
    current_table = sim_engine.current_table()

    # Un sous-dossier par équipe contenant ses 3 graphes (classement, points, matchs clés).
    for index, team in enumerate(sim_engine.TEAMS, start=1):
        team_dir_name = safe_filename(team)
        per_team_dir = team_output_dir / team_dir_name
        per_team_dir.mkdir(parents=True, exist_ok=True)
        viz.team_card(
            team,
            simulation,
            current_table,
            per_team_dir / "classement.png",
            n_sims=n_sims,
            rank_dist=rank_dist,
            qualifications=qualifications,
        )
        viz.team_points_card(
            team,
            simulation,
            current_table,
            per_team_dir / "points.png",
            n_sims=n_sims,
            qualifications=qualifications,
        )
        viz.team_important_matches_card(
            team,
            simulation,
            current_table,
            per_team_dir / "matchs_cles.png",
            n_sims=n_sims,
            importance=importance,
        )
        print(f"[{index:02d}/{len(sim_engine.TEAMS)}] Graphiques créés : {team_dir_name}/")

    # Vues d'ensemble : probabilités de qualification + seuils de points Top 8 / 16 / 24.
    overview_path = output_dir / "classement_global.png"
    viz.overview(simulation, current_table, overview_path)

    thresholds_path = output_dir / "seuils_points_top_8_16_24.png"
    viz.points_thresholds_card(simulation, thresholds_path, n_sims=n_sims)

    # Tableau CSV avec les valeurs exactes, y compris les probabilités des 36 places.
    csv_path = output_dir / "probabilites_equipes.csv"
    write_probabilities_csv(simulation, rank_dist, qualifications, csv_path, sim_engine.N_TEAMS)

    print("\nTerminé !")
    print(f"Source : {args.source}")
    print(f"Équipes traitées : {len(sim_engine.TEAMS)}")
    print(f"Dossiers par équipe : {team_output_dir}")
    print(f"Vue d'ensemble : {overview_path}")
    print(f"Seuils de points Top 8/16/24 : {thresholds_path}")
    print(f"Probabilités détaillées (CSV) : {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
