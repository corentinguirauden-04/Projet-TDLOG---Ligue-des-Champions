"""Orchestration de la pipeline complète (Elo -> validation -> simulation -> visuels & CSV).

Remplace les anciens scripts dupliqués `main.py` / `generate_outputs.py` en une
couche applicative unique, sans aucun recours à `importlib.reload`.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
import sys
from pathlib import Path

from ldc import data as ldc_data
from ldc import elo as ldc_elo
from ldc import simulation as sim_engine
from ldc import visualization as viz
from ldc.config import DEFAULT_N_SIMS, DEFAULT_SEED, ELO_FILE, OUTPUTS_DIR, SOURCES


def safe_filename(team: str) -> str:
    """Transforme un nom d'équipe en slug portable Windows/Linux."""
    name = team.lower().replace("/", "-")
    name = re.sub(r"[^a-z0-9_-]+", "_", name)
    return name.strip("_") or "equipe"


def write_probabilities_csv(
    sim: dict,
    rank_dist,
    qualifications: dict[str, dict[str, float]],
    path: Path,
) -> None:
    """Écrit le CSV des indicateurs de qualification et de probabilité de chacune des 36 places."""
    n_teams = len(sim["teams"])
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


def _prepare_elo_source(
    source: str,
    date: str | None = None,
    no_refresh: bool = False,
    elo_file: Path | None = None,
) -> int:
    """Prépare `data/elo.json` selon la source choisie (`clubelo`, `beyondelo` ou `manual`)."""
    if source == "manual":
        if elo_file is not None:
            raw = json.loads(elo_file.read_text(encoding="utf-8"))
            raw_map = raw["elo"] if isinstance(raw, dict) and "elo" in raw else raw
            manual_elo, err = ldc_data.validate_elo_map(raw_map)
            if err or manual_elo is None:
                print(f"Erreur : {err}", file=sys.stderr)
                return 1
        else:
            manual_elo = dict(ldc_data.DEFAULT_ELO)

        ldc_data.write_elo_json(
            manual_elo,
            date=date or dt.date.today().isoformat(),
            source="manual",
            path=ELO_FILE,
        )
        return 0

    if source == "beyondelo" and no_refresh and ELO_FILE.is_file():
        try:
            current = json.loads(ELO_FILE.read_text(encoding="utf-8"))
            if current.get("source") == "beyondelo":
                return 0
        except Exception:
            pass

    return ldc_elo.fetch_and_save_elo(
        source=source,
        date=date,
        no_download=(no_refresh and source == "clubelo"),
    )


def run_pipeline(
    source: str = "clubelo",
    n_sims: int = DEFAULT_N_SIMS,
    date: str | None = None,
    no_refresh: bool = False,
    elo_file: Path | None = None,
    seed: int = DEFAULT_SEED,
) -> int:
    """Exécute toute la chaîne : Elo -> vérification -> simulation -> graphiques & CSV."""
    if n_sims <= 0:
        print("Erreur : le nombre de simulations doit être strictement positif.", file=sys.stderr)
        return 2

    status = _prepare_elo_source(source, date=date, no_refresh=no_refresh, elo_file=elo_file)
    if status != 0:
        return status

    ldc_data.check()
    elo_map, elo_date = ldc_data.load_elo()

    output_dir = OUTPUTS_DIR / source
    team_output_dir = output_dir / "equipes"
    ranking_output_dir = output_dir / "classements"
    team_output_dir.mkdir(parents=True, exist_ok=True)
    ranking_output_dir.mkdir(parents=True, exist_ok=True)

    print(
        f"Lancement de {n_sims:,} simulations ({source}) "
        f"pour {len(ldc_data.TEAMS)} équipes...".replace(",", " ")
    )
    sim = sim_engine.simulate(n_sims=n_sims, seed=seed, elo=elo_map, elo_date=elo_date)

    # Pré-calculs effectués une seule fois puis injectés dans toutes les fonctions de tracé.
    rank_dist = sim_engine.rank_distribution(sim)
    qualifications = sim_engine.qualification_probs(sim, rank_dist=rank_dist)
    importance = sim_engine.match_importance(sim)
    pts_by_rank = sim_engine.points_by_position(sim)
    current_table = sim_engine.current_table()

    for index, team in enumerate(ldc_data.TEAMS, start=1):
        team_dir_name = safe_filename(team)
        per_team_dir = team_output_dir / team_dir_name
        per_team_dir.mkdir(parents=True, exist_ok=True)
        viz.team_card(
            team, sim, current_table, per_team_dir / "classement.png",
            n_sims=n_sims, rank_dist=rank_dist, qualifications=qualifications,
        )
        viz.team_points_card(
            team, sim, current_table, per_team_dir / "points.png",
            n_sims=n_sims, qualifications=qualifications,
        )
        viz.team_important_matches_card(
            team, sim, current_table, per_team_dir / "matchs_cles.png",
            n_sims=n_sims, importance=importance,
        )
        print(f"[{index:02d}/{len(ldc_data.TEAMS)}] Graphiques créés : {team_dir_name}/")

    for position in range(1, sim_engine.N_TEAMS + 1):
        viz.position_points_card(
            position, sim, ranking_output_dir / f"{position}.png",
            n_sims=n_sims, pts_by_rank=pts_by_rank,
        )
    print(f"Graphiques par position créés : {ranking_output_dir} (1.png à {sim_engine.N_TEAMS}.png)")

    overview_path = output_dir / "classement_global.png"
    viz.overview(sim, current_table, overview_path, qualifications=qualifications)

    thresholds_path = output_dir / "seuils_points_top_8_16_24.png"
    viz.points_thresholds_card(sim, thresholds_path, n_sims=n_sims, pts_by_rank=pts_by_rank)

    csv_path = output_dir / "probabilites_equipes.csv"
    write_probabilities_csv(sim, rank_dist, qualifications, csv_path)

    print("\nTerminé !")
    print(f"Source : {source}")
    print(f"Équipes traitées : {len(ldc_data.TEAMS)}")
    print(f"Dossiers par équipe : {team_output_dir}")
    print(f"Points par position : {ranking_output_dir}")
    print(f"Vue d'ensemble : {overview_path}")
    print(f"Seuils de points Top 8/16/24 : {thresholds_path}")
    print(f"Probabilités détaillées (CSV) : {csv_path}")
    return 0


def _prompt_source() -> str:
    """Demande la source Elo de manière interactive si aucun argument n'est fourni."""
    print("Choisis la source Elo :")
    print("  1. clubelo (ClubElo : API avec repli HTML automatique)")
    print("  2. beyondelo (API beyondELO)")
    print("  3. manual (Elo personnalisé)")
    choice = input("Source [clubelo] : ").strip().lower()
    mapping = {"": "clubelo", "1": "clubelo", "2": "beyondelo", "3": "manual"}
    resolved = mapping.get(choice, choice)
    if resolved not in SOURCES:
        raise ValueError(f"Source invalide : {choice!r}. Choix possibles : {', '.join(SOURCES)}.")
    return resolved


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Exécute la pipeline complète (Elo -> vérification -> simulation -> outputs)."
    )
    parser.add_argument(
        "-s", "--source",
        choices=SOURCES,
        default=None,
        help="Source des notes Elo : clubelo (défaut), beyondelo ou manual.",
    )
    parser.add_argument(
        "-n", "--n-sims",
        type=int,
        default=DEFAULT_N_SIMS,
        help=f"Nombre de simulations Monte Carlo (défaut : {DEFAULT_N_SIMS}).",
    )
    parser.add_argument(
        "--date",
        default=None,
        help="Date historique (AAAA-MM-JJ) pour l'API clubelo ou beyondelo.",
    )
    parser.add_argument(
        "--elo-file",
        type=Path,
        default=None,
        help="Fichier JSON d'Elo personnalisé (utilisé avec --source manual).",
    )
    parser.add_argument(
        "--no-refresh",
        action="store_true",
        help="Réutilise data/clubelo_ranking.html ou data/elo.json sans téléchargement réseau.",
    )
    args = parser.parse_args(argv)

    source = args.source
    if source is None:
        if sys.stdin.isatty():
            try:
                source = _prompt_source()
            except ValueError as exc:
                print(exc, file=sys.stderr)
                return 2
        else:
            source = "clubelo"

    if args.elo_file is not None and source != "manual":
        print("L'option --elo-file s'utilise uniquement avec --source manual.", file=sys.stderr)
        return 2

    return run_pipeline(
        source=source,
        n_sims=args.n_sims,
        date=args.date,
        no_refresh=args.no_refresh,
        elo_file=args.elo_file,
    )
