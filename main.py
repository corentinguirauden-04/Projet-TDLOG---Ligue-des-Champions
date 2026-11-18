"""Point d'entrée unique de la pipeline Ligue des Champions.

Exécute toute la chaîne :
1. Récupération / préparation des notes Elo (`clubelo`, `beyondelo` ou `manual`).
2. Vérification de cohérence du calendrier et des données (`ldc_data.check()`).
3. Simulation Monte Carlo et génération des graphiques + CSV dans `outputs/<source>/`.

Exemples :
    python main.py --source clubelo
    python main.py --source beyondelo
    python main.py --source manual
    python main.py --source manual --elo-file mon_elo.json
    python main.py --source clubelo --date 2026-10-01 --n-sims 50000
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import generate_outputs


SOURCES = ("html", "clubelo", "beyondelo", "manual")


def _prompt_source() -> str:
    """Demande la source Elo de manière interactive si aucun argument n'est fourni."""
    print("Choisis la source Elo :")
    print("  1. html (HTML ClubElo local)")
    print("  2. clubelo (API ClubElo)")
    print("  3. beyondelo (API beyondELO)")
    print("  4. manual (Elo personnalisé)")
    choice = input("Source [html] : ").strip().lower()
    mapping = {"": "html", "1": "html", "2": "clubelo", "3": "beyondelo", "4": "manual"}
    resolved = mapping.get(choice, choice)
    if resolved not in SOURCES:
        raise ValueError(f"Source invalide : {choice!r}. Choix possibles : {', '.join(SOURCES)}.")
    return resolved


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Exécute la pipeline complète (Elo -> vérification -> simulation -> outputs)."
    )
    parser.add_argument(
        "-s",
        "--source",
        choices=SOURCES,
        default=None,
        help="Source des notes Elo : clubelo, beyondelo ou manual.",
    )
    parser.add_argument(
        "-n",
        "--n-sims",
        type=int,
        default=generate_outputs.DEFAULT_N_SIMS,
        help=f"Nombre de simulations Monte Carlo (défaut : {generate_outputs.DEFAULT_N_SIMS}).",
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
        help="Réutilise elo.json s'il provient déjà de la même source.",
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

    gen_args = [str(args.n_sims), "--source", source]
    if args.date is not None:
        gen_args.extend(["--date", args.date])
    if args.elo_file is not None:
        gen_args.extend(["--elo-file", str(args.elo_file)])
    if not args.no_refresh and source != "manual":
        gen_args.append("--refresh")

    # 1. Prépare elo.json selon la source choisie et génère les sorties.
    status = generate_outputs.main(gen_args)
    if status != 0:
        return status

    # 2. Vérifie la cohérence finale des données utilisées.
    import ldc_data

    ldc_data.check()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
