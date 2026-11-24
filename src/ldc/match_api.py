"""Synchronisation des résultats UEFA via football-data.org.

Le navigateur ne contacte jamais directement le fournisseur : le serveur effectue
au maximum une requête par minute, conserve le dernier état valide et ne considère
un match comme joué qu'une fois son statut FINISHED/AWARDED avec un score final.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from threading import Lock
from typing import Any

from ldc.config import FOOTBALL_DATA_API_TOKEN, LIVE_MATCHES_FILE, LIVE_MATCH_POLL_SECONDS
from ldc.data import PLAYED, REMAINING, TEAMS, check

API_URL = "https://api.football-data.org/v4/competitions/CL/matches?season=2026"
FINAL_STATUSES = {"FINISHED", "AWARDED"}
LIVE_STATUSES = {"IN_PLAY", "PAUSED", "LIVE", "SUSPENDED"}

# Variantes de noms rencontrées dans les flux de résultats.
_TEAM_ALIASES: dict[str, tuple[str, ...]] = {
    "AEK": ("AEK", "AEK Athens", "AEK Athens FC"),
    "Arsenal": ("Arsenal", "Arsenal FC"),
    "Aston Villa": ("Aston Villa", "Aston Villa FC"),
    "Atletico": ("Atletico", "Atletico Madrid", "Atletico de Madrid", "Club Atletico de Madrid", "Club Atlético de Madrid"),
    "Dortmund": ("Dortmund", "Borussia Dortmund"),
    "Barcelona": ("Barcelona", "FC Barcelona"),
    "Bayern": ("Bayern", "Bayern Munich", "Bayern München", "FC Bayern München"),
    "Bodo/Glimt": ("Bodo/Glimt", "Bodo Glimt", "Bodø/Glimt", "Bodoe Glimt"),
    "Club Brugge": ("Club Brugge", "Brugge", "Club Brugge KV"),
    "Como": ("Como", "Como 1907"),
    "Fenerbahce": ("Fenerbahce", "Fenerbahçe", "Fenerbahce SK", "Fenerbahçe SK"),
    "Feyenoord": ("Feyenoord",),
    "Galatasaray": ("Galatasaray", "Galatasaray SK"),
    "Inter": ("Inter", "Internazionale", "Inter Milan", "FC Internazionale Milano"),
    "LASK": ("LASK", "LASK Linz"),
    "Leipzig": ("Leipzig", "RB Leipzig"),
    "Lens": ("Lens", "RC Lens"),
    "Lille": ("Lille", "Lille OSC"),
    "Liverpool": ("Liverpool", "Liverpool FC"),
    "Man City": ("Man City", "Manchester City", "Manchester City FC"),
    "Man United": ("Man United", "Manchester United", "Man Utd", "Manchester United FC"),
    "Napoli": ("Napoli", "SSC Napoli"),
    "PSG": ("PSG", "Paris SG", "Paris Saint-Germain", "Paris Saint-Germain FC"),
    "Porto": ("Porto", "FC Porto"),
    "PSV": ("PSV", "PSV Eindhoven"),
    "Real Betis": ("Real Betis", "Betis", "Real Betis Balompie", "Real Betis Balompié"),
    "Real Madrid": ("Real Madrid", "Real Madrid CF"),
    "Roma": ("Roma", "AS Roma"),
    "Slovan Bratislava": ("Slovan Bratislava", "Slovan", "ŠK Slovan Bratislava"),
    "Sabah": ("Sabah", "Sabah FK", "Sabah Baku"),
    "Shakhtar": ("Shakhtar", "Shakhtar Donetsk", "FC Shakhtar Donetsk"),
    "Slavia Praha": ("Slavia Praha", "Slavia Prague", "SK Slavia Praha"),
    "Sporting CP": ("Sporting CP", "Sporting", "Sporting Lisbon", "Sporting Clube de Portugal"),
    "Stuttgart": ("Stuttgart", "VfB Stuttgart"),
    "Viking": ("Viking", "Viking FK"),
    "Villarreal": ("Villarreal", "Villarreal CF"),
}

def _norm(value: Any) -> str:
    import unicodedata
    text = str(value).translate(str.maketrans({"ø": "o", "Ø": "O", "æ": "ae", "Æ": "AE", "œ": "oe", "Œ": "OE", "ł": "l", "Ł": "L", "ß": "ss"}))
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return "".join(c.lower() for c in text if c.isalnum())

_ALIAS_TO_TEAM = {
    _norm(alias): team
    for team, aliases in _TEAM_ALIASES.items()
    for alias in aliases
}
for _team in TEAMS:
    _ALIAS_TO_TEAM.setdefault(_norm(_team), _team)

_BASE_FIXTURES = [(h, a) for h, a, _, _ in PLAYED] + list(REMAINING)
_BASE_RESULTS = {(h, a): (int(hg), int(ag)) for h, a, hg, ag in PLAYED}
_CACHE_LOCK = Lock()
_CACHE: dict[str, Any] | None = None
_CACHE_MONOTONIC = 0.0


def _signature(played: list[tuple[str, str, int, int]], remaining: list[tuple[str, str]]) -> str:
    payload = {
        "played": played,
        "remaining": remaining,
    }
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def static_match_state() -> dict[str, Any]:
    played = list(PLAYED)
    remaining = list(REMAINING)
    return {
        "played": played,
        "remaining": remaining,
        "live": [],
        "signature": _signature(played, remaining),
        "configured": bool(FOOTBALL_DATA_API_TOKEN),
        "connected": False,
        "provider": "football-data.org",
        "last_checked_at": None,
        "results_updated_at": None,
        "matched_fixtures": 0,
        "total_fixtures": len(_BASE_FIXTURES),
        "error": None,
        "has_external_data": False,
    }


def _read_saved_state() -> dict[str, Any] | None:
    if not LIVE_MATCHES_FILE.is_file():
        return None
    try:
        saved = json.loads(LIVE_MATCHES_FILE.read_text(encoding="utf-8"))
        played = [
            (str(x["home"]), str(x["away"]), int(x["hg"]), int(x["ag"]))
            for x in saved["played"]
        ]
        remaining = [(str(x[0]), str(x[1])) for x in saved["remaining"]]
        live = saved.get("live", [])
        check(played=played, remaining=remaining)
        return {
            "played": played,
            "remaining": remaining,
            "live": live if isinstance(live, list) else [],
            "signature": _signature(played, remaining),
            "configured": bool(FOOTBALL_DATA_API_TOKEN),
            "connected": False,
            "provider": "football-data.org",
            "last_checked_at": saved.get("last_checked_at"),
            "results_updated_at": saved.get("results_updated_at"),
            "matched_fixtures": int(saved.get("matched_fixtures", 0)),
            "total_fixtures": len(_BASE_FIXTURES),
            "error": None,
            "has_external_data": True,
        }
    except (OSError, ValueError, KeyError, TypeError, AssertionError, json.JSONDecodeError):
        return None


def _fetch_payload() -> dict[str, Any]:
    if not FOOTBALL_DATA_API_TOKEN:
        raise RuntimeError("Clé absente : définis la variable d'environnement FOOTBALL_DATA_API_TOKEN.")
    request = urllib.request.Request(
        API_URL,
        headers={
            "X-Auth-Token": FOOTBALL_DATA_API_TOKEN,
            "Accept": "application/json",
            "User-Agent": "LDC-Monte-Carlo-TDLOG/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"football-data.org HTTP {exc.code}: {body}") from exc
    except Exception as exc:
        raise RuntimeError(f"football-data.org inaccessible : {exc}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("matches"), list):
        raise ValueError("Réponse football-data.org invalide : liste 'matches' absente.")
    return payload


def build_match_state(payload: dict[str, Any], previous: dict[str, Any] | None = None) -> dict[str, Any]:
    """Convertit une réponse API en PLAYED/REMAINING en préservant le calendrier du projet."""
    raw_matches = payload.get("matches")
    if not isinstance(raw_matches, list):
        raise ValueError("Réponse API sans liste de matchs.")

    # Conserver les scores statiques de départ et les résultats confirmés déjà synchronisés.
    results = dict(_BASE_RESULTS)
    if previous:
        for h, a, hg, ag in previous.get("played", []):
            results[(h, a)] = (int(hg), int(ag))

    api_by_pair: dict[tuple[str, str], dict[str, Any]] = {}
    def resolve_team(team_info: Any) -> str | None:
        if not isinstance(team_info, dict):
            return None
        # football-data.org expose plusieurs libellés : le nom long, le nom court
        # et le sigle. On essaie chacun pour éviter de perdre un match sur un alias.
        for field in ("name", "shortName", "tla"):
            raw_name = team_info.get(field)
            if raw_name:
                found = _ALIAS_TO_TEAM.get(_norm(raw_name))
                if found:
                    return found
        return None

    for item in raw_matches:
        if not isinstance(item, dict):
            continue
        home = resolve_team(item.get("homeTeam"))
        away = resolve_team(item.get("awayTeam"))
        pair = (home, away)
        if home not in TEAMS or away not in TEAMS or pair not in _BASE_FIXTURES:
            continue

        status = str(item.get("status") or "SCHEDULED").upper()
        score = item.get("score") or {}
        full_time = score.get("fullTime") or {}
        hg, ag = full_time.get("home"), full_time.get("away")
        if status in FINAL_STATUSES and isinstance(hg, int) and isinstance(ag, int):
            results[pair] = (hg, ag)

        if status in LIVE_STATUSES:
            current = score.get("fullTime") or score.get("halfTime") or {}
            api_by_pair[pair] = {
                "status": status,
                "score_home": current.get("home"),
                "score_away": current.get("away"),
                "utc_date": item.get("utcDate"),
            }
        else:
            api_by_pair[pair] = {"status": status, "utc_date": item.get("utcDate")}

    # On accepte également une réponse limitée à la journée courante, mais pas un flux
    # sans aucun match correspondant au calendrier étudié.
    if len(api_by_pair) != len(_BASE_FIXTURES):
        raise ValueError(
            f"Couverture API incomplète : {len(api_by_pair)} matchs reconnus sur "
            f"{len(_BASE_FIXTURES)}. Aucune mise à jour n'est appliquée pour éviter "
            "des projections fondées sur un calendrier incomplet. Vérifie la saison 2026 "
            "et les alias des clubs."
        )

    played: list[tuple[str, str, int, int]] = []
    remaining: list[tuple[str, str]] = []
    live: list[dict[str, Any]] = []
    for home, away in _BASE_FIXTURES:
        pair = (home, away)
        if pair in results:
            hg, ag = results[pair]
            played.append((home, away, hg, ag))
        else:
            remaining.append(pair)
            info = api_by_pair.get(pair, {})
            if info.get("status") in LIVE_STATUSES:
                live.append({"home": home, "away": away, **info})

    check(played=played, remaining=remaining)
    return {
        "played": played,
        "remaining": remaining,
        "live": live,
        "signature": _signature(played, remaining),
        "configured": True,
        "connected": True,
        "provider": "football-data.org",
        "last_checked_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "results_updated_at": None,
        "matched_fixtures": len(api_by_pair),
        "total_fixtures": len(_BASE_FIXTURES),
        "error": None,
        "has_external_data": True,
    }


def _save_state(state: dict[str, Any]) -> None:
    LIVE_MATCHES_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "played": [
            {"home": h, "away": a, "hg": hg, "ag": ag}
            for h, a, hg, ag in state["played"]
        ],
        "remaining": state["remaining"],
        "live": state["live"],
        "last_checked_at": state["last_checked_at"],
        "results_updated_at": state["results_updated_at"],
        "matched_fixtures": state["matched_fixtures"],
    }
    tmp = LIVE_MATCHES_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(LIVE_MATCHES_FILE)


def get_match_state(force: bool = False) -> dict[str, Any]:
    """Retourne l'état courant ; l'API est appelée au plus une fois par minute."""
    global _CACHE, _CACHE_MONOTONIC
    now = time.monotonic()
    if not force and _CACHE is not None and now - _CACHE_MONOTONIC < LIVE_MATCH_POLL_SECONDS:
        return dict(_CACHE)

    with _CACHE_LOCK:
        now = time.monotonic()
        if not force and _CACHE is not None and now - _CACHE_MONOTONIC < LIVE_MATCH_POLL_SECONDS:
            return dict(_CACHE)

        previous = _CACHE or _read_saved_state()
        if not FOOTBALL_DATA_API_TOKEN:
            state = previous or static_match_state()
            state = dict(state)
            state.update(
                configured=False,
                connected=False,
                error="Ajoute FOOTBALL_DATA_API_TOKEN pour activer la synchronisation automatique.",
            )
        else:
            try:
                state = build_match_state(_fetch_payload(), previous=previous)
                old_signature = previous.get("signature") if previous else static_match_state()["signature"]
                if state["signature"] == old_signature and previous:
                    state["results_updated_at"] = previous.get("results_updated_at")
                else:
                    state["results_updated_at"] = state["last_checked_at"]
                _save_state(state)
            except Exception as exc:
                state = dict(previous or static_match_state())
                state.update(
                    configured=True,
                    connected=False,
                    error=str(exc),
                )

        _CACHE = state
        _CACHE_MONOTONIC = time.monotonic()
        return dict(state)


def reset_cache_for_tests() -> None:
    """Réinitialise le cache mémoire (utilisé uniquement dans les tests)."""
    global _CACHE, _CACHE_MONOTONIC
    with _CACHE_LOCK:
        _CACHE = None
        _CACHE_MONOTONIC = 0.0
