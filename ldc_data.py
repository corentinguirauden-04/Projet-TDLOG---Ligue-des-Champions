"""
Données de la phase de ligue 2026-27 : Elo, résultats joués (J1-J4) et calendrier restant (J5-J8).
Source des matchs : UEFA.com (mise à jour du 4 novembre 2026).
Convention : "Domicile - Extérieur", la première équipe reçoit.
"""

# Elo de départ : valeurs de ton fichier tdlog_projet.py.
# ATTENTION : Stuttgart n'y figurait pas (36e équipe). La valeur 1800 est un PLACEHOLDER à remplacer
# par la vraie valeur (même source que les autres Elo, ex. clubelo.com).
ELO = {
    "AEK": 1695, "Arsenal": 2047, "Aston Villa": 1899, "Atletico": 1910, "Dortmund": 1899,
    "Barcelona": 2032, "Bayern": 2046, "Bodo/Glimt": 1779, "Club Brugge": 1839, "Como": 1838,
    "Fenerbahce": 1779, "Feyenoord": 1716, "Galatasaray": 1824, "Inter": 1949, "LASK": 1643,
    "Leipzig": 1832, "Lens": 1779, "Lille": 1780, "Liverpool": 1937, "Man City": 2002,
    "Man United": 1851, "Napoli": 1818, "PSG": 1989, "Porto": 1843, "PSV": 1782,
    "Real Betis": 1829, "Real Madrid": 2001, "Roma": 1865, "Slovan Bratislava": 1541,
    "Sabah": 1558, "Shakhtar": 1687, "Slavia Praha": 1744, "Sporting CP": 1863,
    "Viking": 1715, "Villarreal": 1789,
    "Stuttgart": 1819,  # <-- PLACEHOLDER
}

DEFAULT_ELO = dict(ELO)

# Si elo.json existe (créé par ldc_elo.py à partir de ClubElo), il remplace les valeurs ci-dessus.
import json as _json
import os as _os

ELO_DATE = None
_p = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "elo.json")
if _os.path.exists(_p):
    with open(_p, encoding="utf-8") as _f:
        _d = _json.load(_f)
    assert set(_d["elo"]) == set(ELO), "elo.json incomplet ou noms différents"
    ELO = _d["elo"]
    ELO_DATE = _d["date"]

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


def _split_result(line):
    """'Club Brugge 2-3 Aston Villa' -> ('Club Brugge', 'Aston Villa', 2, 3)"""
    toks = line.split()
    for i, t in enumerate(toks):
        if len(t) == 3 and t[0].isdigit() and t[1] == "-" and t[2].isdigit():
            return " ".join(toks[:i]), " ".join(toks[i + 1:]), int(t[0]), int(t[2])
    raise ValueError(f"score introuvable : {line}")


PLAYED = [_split_result(l) for l in _PLAYED.strip().splitlines()]
REMAINING = [tuple(s.strip() for s in l.split(" - ")) for l in _REMAINING.strip().splitlines()]
TEAMS = sorted(ELO)


def check():
    """Vérifie la cohérence du calendrier : 144 matchs, 8 par équipe (4 dom / 4 ext), pas de doublon."""
    allm = [(h, a) for h, a, _, _ in PLAYED] + REMAINING
    assert len(PLAYED) == 72, len(PLAYED)
    assert len(REMAINING) == 72, len(REMAINING)
    assert len(TEAMS) == 36
    for t in TEAMS:
        home = sum(h == t for h, _ in allm)
        away = sum(a == t for _, a in allm)
        assert home == 4 and away == 4, (t, home, away)
    pairs = {frozenset(m) for m in allm}
    assert len(pairs) == 144, len(pairs)
    for h, a in allm:
        assert h in ELO and a in ELO, (h, a)
    return True


if __name__ == "__main__":
    print(check(), len(PLAYED), len(REMAINING))
