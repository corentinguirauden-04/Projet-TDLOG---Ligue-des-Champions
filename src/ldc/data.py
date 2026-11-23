"""Données de la phase de ligue 2026-27 : Elo par défaut, résultats joués (J1-J4) et calendrier (J5-J8).

Source des matchs : UEFA.com (mise à jour du 4 novembre 2026).
Convention : "Domicile - Extérieur", la première équipe reçoit.
"""
from __future__ import annotations

import json
from pathlib import Path

from ldc.config import ELO_FILE, MAX_ELO, MIN_ELO

# Notes Elo manuelles de secours (36 clubs de la phase de ligue).
# Remplacées dynamiquement par data/elo.json via `load_elo()`.
DEFAULT_ELO: dict[str, int] = {
    "AEK": 1695, "Arsenal": 2047, "Aston Villa": 1899, "Atletico": 1910, "Dortmund": 1899,
    "Barcelona": 2032, "Bayern": 2046, "Bodo/Glimt": 1779, "Club Brugge": 1839, "Como": 1838,
    "Fenerbahce": 1779, "Feyenoord": 1716, "Galatasaray": 1824, "Inter": 1949, "LASK": 1643,
    "Leipzig": 1832, "Lens": 1779, "Lille": 1780, "Liverpool": 1937, "Man City": 2002,
    "Man United": 1851, "Napoli": 1818, "PSG": 1989, "Porto": 1843, "PSV": 1782,
    "Real Betis": 1829, "Real Madrid": 2001, "Roma": 1865, "Slovan Bratislava": 1541,
    "Sabah": 1558, "Shakhtar": 1687, "Slavia Praha": 1744, "Sporting CP": 1863,
    "Viking": 1715, "Villarreal": 1789,
    "Stuttgart": 1819,
}

_PLAYED = """
AEK 1-0 LASK
Club Brugge 2-3 Aston Villa
Dortmund 3-2 Villarreal
Porto 0-2 Man City
Lille 2-3 Real Betis
Real Madrid 2-1 Inter
Barcelona 5-1 Feyenoord
Stuttgart 3-1 Viking
Liverpool 2-1 Atletico
PSG 6-1 Slovan Bratislava
Sporting CP 3-1 Galatasaray
Napoli 0-1 Arsenal
Fenerbahce 1-1 Roma
PSV 1-1 Shakhtar
Como 4-1 Leipzig
Bayern 5-0 Bodo/Glimt
Man United 4-0 Sabah
Slavia Praha 2-3 Lens
Lens 0-2 Sporting CP
Sabah 2-0 Slavia Praha
Arsenal 3-0 Lille
Atletico 2-0 Man United
Inter 3-4 Club Brugge
Galatasaray 1-4 Barcelona
Leipzig 1-0 PSV
Viking 3-3 Bayern
Villarreal 3-1 Napoli
Feyenoord 3-2 Como
LASK 3-6 Liverpool
Roma 3-4 Real Madrid
Aston Villa 6-0 Fenerbahce
Shakhtar 3-1 AEK
Bodo/Glimt 1-0 Dortmund
Man City 2-4 PSG
Real Betis 3-2 Porto
Slovan Bratislava 0-3 Stuttgart
Fenerbahce 2-2 Slavia Praha
Sabah 1-2 Dortmund
Roma 4-0 Slovan Bratislava
Porto 0-1 PSV
Liverpool 4-3 Villarreal
Man City 5-1 AEK
PSG 4-2 Barcelona
Napoli 4-3 Bodo/Glimt
Stuttgart 1-1 Atletico
Como 4-1 Man United
Lille 2-4 Galatasaray
Aston Villa 3-1 Viking
Club Brugge 3-0 Lens
Bayern 2-2 Arsenal
Inter 1-0 Shakhtar
Real Madrid 4-1 Leipzig
Real Betis 1-0 Feyenoord
Sporting CP 2-3 LASK
Shakhtar 0-1 Sporting CP
Galatasaray 2-0 Stuttgart
Atletico 0-2 Bayern
Barcelona 3-0 Aston Villa
Feyenoord 0-3 Inter
Bodo/Glimt 0-0 Lille
LASK 4-0 Slovan Bratislava
Man United 3-2 Roma
Villarreal 0-6 PSG
AEK 2-3 Real Madrid
Fenerbahce 3-2 Liverpool
Dortmund 2-1 Real Betis
Porto 4-1 Napoli
PSV 1-2 Club Brugge
Leipzig 2-3 Man City
Lens 1-9 Como
Slavia Praha 1-2 Arsenal
Viking 4-1 Sabah
"""

_REMAINING = """
Bodo/Glimt - LASK
Galatasaray - Aston Villa
Arsenal - Dortmund
Como - AEK
Feyenoord - Porto
Man City - Napoli
Leipzig - Lens
Real Madrid - PSV
Slovan Bratislava - Real Betis
Sabah - Barcelona
Slavia Praha - Villarreal
Atletico - Viking
Club Brugge - Liverpool
Inter - Stuttgart
Shakhtar - Fenerbahce
Lille - Bayern
PSG - Roma
Sporting CP - Man United
Viking - Feyenoord
Villarreal - Sabah
AEK - Galatasaray
Roma - Sporting CP
Aston Villa - PSG
Barcelona - Man City
Bayern - Slavia Praha
Man United - Leipzig
Napoli - Club Brugge
Real Betis - Como
Slovan Bratislava - Shakhtar
Arsenal - Real Madrid
Dortmund - Inter
LASK - Fenerbahce
Liverpool - Porto
Lens - Bodo/Glimt
PSV - Atletico
Stuttgart - Lille
Bodo/Glimt - Atletico
Galatasaray - Feyenoord
AEK - Roma
Aston Villa - Dortmund
Inter - Liverpool
Porto - Slavia Praha
Lille - Slovan Bratislava
Real Madrid - LASK
Stuttgart - Club Brugge
Fenerbahce - Villarreal
Sabah - Napoli
Como - PSG
Man United - Bayern
Leipzig - Shakhtar
Lens - Man City
Real Betis - Arsenal
Sporting CP - Barcelona
Viking - PSV
Arsenal - Sabah
Roma - Lille
Atletico - Fenerbahce
Dortmund - AEK
Club Brugge - Bodo/Glimt
Bayern - Real Betis
Barcelona - Como
Shakhtar - Real Madrid
Feyenoord - Leipzig
LASK - Porto
Liverpool - Lens
Man City - Sporting CP
PSG - Galatasaray
PSV - Stuttgart
Slavia Praha - Aston Villa
Napoli - Viking
Villarreal - Man United
Slovan Bratislava - Inter
"""


def _split_result(line: str) -> tuple[str, str, int, int]:
    """'Club Brugge 2-3 Aston Villa' -> ('Club Brugge', 'Aston Villa', 2, 3)."""
    tokens = line.split()
    for i, token in enumerate(tokens):
        if "-" in token:
            left, _, right = token.partition("-")
            if left.isdigit() and right.isdigit():
                return " ".join(tokens[:i]), " ".join(tokens[i + 1:]), int(left), int(right)
    raise ValueError(f"Score introuvable : {line}")


PLAYED: list[tuple[str, str, int, int]] = [_split_result(line) for line in _PLAYED.strip().splitlines()]
REMAINING: list[tuple[str, str]] = [
    tuple(part.strip() for part in line.split(" - "))  # type: ignore[misc]
    for line in _REMAINING.strip().splitlines()
]
TEAMS: list[str] = sorted(DEFAULT_ELO)


def matches_per_matchday() -> int:
    """Nombre de matchs par journée complète (18 pour 36 clubs)."""
    return max(1, len(TEAMS) // 2)


def current_matchday(played: list[tuple[str, str, int, int]] | None = None) -> int:
    """Nombre de journées complètes déjà disputées."""
    p = PLAYED if played is None else played
    return len(p) // matches_per_matchday()


def total_matchdays(
    played: list[tuple[str, str, int, int]] | None = None,
    remaining: list[tuple[str, str]] | None = None,
) -> int:
    """Nombre total de journées de la phase de ligue."""
    p = PLAYED if played is None else played
    r = REMAINING if remaining is None else remaining
    return (len(p) + len(r)) // matches_per_matchday()


def matchday_for_played(idx: int) -> int:
    """Numéro de journée (1..8) d'un match joué d'indice `idx` dans `PLAYED`."""
    return idx // matches_per_matchday() + 1


def matchday_for_remaining(idx: int, n_played: int | None = None) -> int:
    """Numéro de journée (1..8) d'un match restant d'indice `idx`, même en cours de journée."""
    base = len(PLAYED) if n_played is None else n_played
    return (base + idx) // matches_per_matchday() + 1


def matchday_progress(
    n_played: int | None = None,
    n_remaining: int | None = None,
) -> dict:
    """Synthèse dynamique de l'avancement des journées (complète ou en cours)."""
    mpd = matches_per_matchday()
    played_count = len(PLAYED) if n_played is None else int(n_played)
    rem_count = len(REMAINING) if n_remaining is None else int(n_remaining)
    completed = played_count // mpd
    played_in_current = played_count % mpd
    in_progress = (completed + 1) if played_in_current > 0 else None
    total = (played_count + rem_count) // mpd

    if in_progress is not None:
        label = f"journée {in_progress} en cours ({played_in_current}/{mpd})"
    elif completed == 0:
        label = "avant la 1re journée"
    else:
        label = f"après la journée {completed}"

    return {
        "completed": completed,
        "in_progress": in_progress,
        "played_in_current": played_in_current,
        "matches_per_day": mpd,
        "total": total,
        "label": label,
    }


def validate_elo_map(raw_elo: object) -> tuple[dict[str, int] | None, str | None]:
    """Valide un dictionnaire {équipe: note_elo} (36 équipes exactes, entiers dans [MIN_ELO, MAX_ELO])."""
    if not isinstance(raw_elo, dict):
        return None, "Le format des notes Elo est invalide."
    expected = set(DEFAULT_ELO)
    if set(raw_elo.keys()) != expected:
        return None, f"Les {len(expected)} équipes de la compétition doivent être renseignées."

    cleaned: dict[str, int] = {}
    for team, val in raw_elo.items():
        if isinstance(val, bool):
            return None, f"La note de {team} doit être un nombre entier."
        try:
            num = int(round(float(val)))
        except (TypeError, ValueError):
            return None, f"La note de {team} doit être un nombre entier."
        if not MIN_ELO <= num <= MAX_ELO:
            return None, f"La note de {team} ({num}) doit être comprise entre {MIN_ELO} et {MAX_ELO}."
        cleaned[team] = num
    return cleaned, None


def load_elo(path: Path = ELO_FILE) -> tuple[dict[str, int], str | None]:
    """Charge les notes Elo et la date depuis `data/elo.json`, ou renvoie `DEFAULT_ELO` en secours."""
    if path.is_file():
        payload = json.loads(path.read_text(encoding="utf-8"))
        elo_map, err = validate_elo_map(payload.get("elo"))
        if err or elo_map is None:
            raise ValueError(f"{path.name} invalide : {err}")
        return elo_map, payload.get("date")
    return dict(DEFAULT_ELO), None


def write_elo_json(
    elo: dict[str, int],
    date: str,
    source: str,
    path: Path = ELO_FILE,
) -> None:
    """Écrit `elo.json` de manière atomique (fichier temporaire puis remplacement)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"date": date, "source": source, "elo": elo}
    temp_path = path.with_suffix(".json.tmp")
    temp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    temp_path.replace(path)


def check(
    played: list[tuple[str, str, int, int]] | None = None,
    remaining: list[tuple[str, str]] | None = None,
) -> bool:
    """Vérifie la cohérence du calendrier : 144 matchs, 8 par équipe (4 dom / 4 ext), pas de doublon.

    Supporte aussi bien une journée terminée qu'une journée partiellement jouée.
    """
    p = PLAYED if played is None else played
    r = REMAINING if remaining is None else remaining
    all_matches = [(h, a) for h, a, _, _ in p] + list(r)
    mpd = matches_per_matchday()
    assert len(TEAMS) == 36
    assert len(all_matches) == 144, (len(p), len(r))
    for team in TEAMS:
        home = sum(h == team for h, _ in all_matches)
        away = sum(a == team for _, a in all_matches)
        assert home == 4 and away == 4, (team, home, away)
    pairs = {frozenset(m) for m in all_matches}
    assert len(pairs) == 144, len(pairs)
    for h, a in all_matches:
        assert h in DEFAULT_ELO and a in DEFAULT_ELO, (h, a)
    # Chaque tranche de 18 matchs correspond à une journée complète (36 équipes distinctes).
    for start in range(0, len(all_matches), mpd):
        block = all_matches[start:start + mpd]
        teams_in_block = {t for pair in block for t in pair}
        assert len(teams_in_block) == len(TEAMS), (start // mpd + 1, len(teams_in_block))
    return True


if __name__ == "__main__":
    print(check(), len(PLAYED), len(REMAINING))
