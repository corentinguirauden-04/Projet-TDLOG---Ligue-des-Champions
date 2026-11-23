"""Serveur HTTP léger (bibliothèque standard Python) — couche Contrôleur web.

Routes exposées :
  - GET  /                    : page principale (`web/index.html`).
  - GET  /styles.css, /app.js : ressources statiques du frontend (`web/`).
  - GET  /outputs/<chemin>    : visuels PNG et CSV générés (protégé contre le path traversal).
  - GET  /api/state?source=   : état des sources, projections, calendrier, journée et Elo manuel.
  - POST /api/simulate        : relance la pipeline de simulation (verrouillée par mutex).
  - POST /api/reset-manual    : remet l'Elo personnalisé aux valeurs `DEFAULT_ELO`.
"""
from __future__ import annotations

import argparse
import csv
import json
import mimetypes
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from ldc import data as ldc_data
from ldc import pipeline
from ldc import simulation as ldc_sim
from ldc.config import (
    CUSTOM_ELO_FILE,
    DEFAULT_N_SIMS,
    MAX_N_SIMS,
    MIN_N_SIMS,
    OUTPUTS_DIR,
    SOURCE_LABELS,
    SOURCES,
    WEB_DIR,
)

# Sérialise les recalculs pour éviter les accès concurrents sur data/elo.json et outputs/.
_SIM_LOCK = threading.Lock()
_STATIC_ASSETS = {"/styles.css": "styles.css", "/app.js": "app.js"}


def _source_status() -> list[dict]:
    """Indique pour chaque source si ses projections sont déjà générées."""
    return [
        {
            "id": src,
            "label": SOURCE_LABELS[src],
            "available": (OUTPUTS_DIR / src / "probabilites_equipes.csv").is_file(),
            "folder": src,
        }
        for src in SOURCES
    ]


def _get_manual_elo() -> dict[str, int]:
    """Retourne l'Elo personnalisé courant (ou `DEFAULT_ELO` par défaut)."""
    if CUSTOM_ELO_FILE.is_file():
        try:
            raw = json.loads(CUSTOM_ELO_FILE.read_text(encoding="utf-8"))
            cleaned, err = ldc_data.validate_elo_map(raw)
            if not err and cleaned is not None:
                return cleaned
        except Exception:
            pass
    return dict(ldc_data.DEFAULT_ELO)


def _schedule_payload(
    source: str,
    played_src: list[tuple[str, str, int, int]] | None = None,
    remaining_src: list[tuple[str, str]] | None = None,
) -> dict:
    """Construit le calendrier (matchs joués + restants enrichis), y compris en cours de journée."""
    p = ldc_data.PLAYED if played_src is None else played_src
    r = ldc_data.REMAINING if remaining_src is None else remaining_src
    played = [
        {
            "matchday": ldc_data.matchday_for_played(idx),
            "home": h,
            "away": a,
            "hg": int(hg),
            "ag": int(ag),
            "winner": "home" if int(hg) > int(ag) else ("away" if int(ag) > int(hg) else "draw"),
        }
        for idx, (h, a, hg, ag) in enumerate(p)
    ]

    matches_json = OUTPUTS_DIR / source / "matchs_restants.json"
    remaining: list[dict] | None = None
    if matches_json.is_file():
        try:
            raw = json.loads(matches_json.read_text(encoding="utf-8"))
            if (
                isinstance(raw, list)
                and len(raw) == len(r)
                and all((item.get("home"), item.get("away")) == pair for item, pair in zip(raw, r))
            ):
                remaining = raw
        except Exception:
            remaining = None

    if remaining is None:
        remaining = [
            {"matchday": ldc_data.matchday_for_remaining(idx, n_played=len(p)), "home": h, "away": a}
            for idx, (h, a) in enumerate(r)
        ]

    return {"played": played, "remaining": remaining}


def _read_source_results(source: str) -> list[dict]:
    """Lit les probabilités CSV d'une source et les enrichit avec le classement réel."""
    csv_path = OUTPUTS_DIR / source / "probabilites_equipes.csv"
    if not csv_path.is_file():
        return []

    current_by_team = {row["team"]: row for row in ldc_sim.current_table()}
    rows: list[dict] = []

    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        for raw in csv.DictReader(f, delimiter=";"):
            team = raw["equipe"]
            rank_probs = [float(raw[f"probabilite_place_{p}"]) for p in range(1, 37)]
            cur = current_by_team.get(team, {"rank": 0, "played": 0, "pts": 0, "gd": 0, "gf": 0, "ga": 0})
            rows.append(
                {
                    "team": team,
                    "slug": pipeline.safe_filename(team),
                    "top1": rank_probs[0],
                    "top8": float(raw["probabilite_top8"]),
                    "top16": float(sum(rank_probs[:16])),
                    "top24": float(raw["probabilite_top24"]),
                    "top32": float(sum(rank_probs[:32])),
                    "playoff": float(raw["probabilite_barrages_9_24"]),
                    "out": float(raw["probabilite_elimination_25_36"]),
                    "exp_pts": float(raw["points_finaux_moyens"]),
                    "most_likely_rank": int(max(range(36), key=lambda i: rank_probs[i]) + 1),
                    "rank_probs": rank_probs,
                    "cur_rank": int(cur["rank"]),
                    "cur_played": int(cur.get("played", ldc_data.current_matchday())),
                    "cur_pts": int(cur["pts"]),
                    "cur_gd": int(cur["gd"]),
                    "cur_gf": int(cur["gf"]),
                    "cur_ga": int(cur["ga"]),
                }
            )

    rows.sort(key=lambda r: (-r["exp_pts"], -r["top8"], -r["top24"]))
    return rows


def resolve_safe_output_path(relative_url_path: str) -> Path | None:
    """Résout un chemin dans `outputs/` tout en bloquant toute tentative de path traversal."""
    root = OUTPUTS_DIR.resolve()
    target = (OUTPUTS_DIR / unquote(relative_url_path)).resolve()
    if root not in target.parents and target != root:
        return None
    return target


class LdcRequestHandler(BaseHTTPRequestHandler):
    """Gestionnaire HTTP : fichiers statiques + routes API JSON."""

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        print(f"[HTTP] {self.address_string()} - {format % args}")

    def _send_json(self, payload: dict, status: int = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path) -> None:
        if not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND, "Fichier introuvable")
            return
        content_type, _ = mimetypes.guess_type(str(path))
        data = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/":
            self._send_file(WEB_DIR / "index.html")
            return

        if path in _STATIC_ASSETS:
            self._send_file(WEB_DIR / _STATIC_ASSETS[path])
            return

        if path.startswith("/outputs/"):
            target = resolve_safe_output_path(path[len("/outputs/"):])
            if target is None:
                self.send_error(HTTPStatus.FORBIDDEN, "Accès refusé")
                return
            self._send_file(target)
            return

        if path == "/api/state":
            params = parse_qs(parsed.query)
            sources = _source_status()
            available_ids = [s["id"] for s in sources if s["available"]]
            requested = params.get("source", [None])[0]
            active = requested if requested in SOURCES else (available_ids[0] if available_ids else "clubelo")
            teams = _read_source_results(active) if active in available_ids else []
            schedule = _schedule_payload(active)
            progress = ldc_data.matchday_progress()

            self._send_json(
                {
                    "sources": sources,
                    "active_source": active,
                    "output_folder": active,
                    "available": active in available_ids,
                    "matchday": progress["completed"],
                    "matchday_in_progress": progress["in_progress"],
                    "played_in_current_md": progress["played_in_current"],
                    "matches_per_day": progress["matches_per_day"],
                    "matchday_label": progress["label"],
                    "total_matchdays": progress["total"],
                    "teams": teams,
                    "played": schedule["played"],
                    "remaining": schedule["remaining"],
                    "default_elo": dict(ldc_data.DEFAULT_ELO),
                    "manual_elo": _get_manual_elo(),
                }
            )
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Route inconnue")

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path not in ("/api/simulate", "/api/reset-manual"):
            self.send_error(HTTPStatus.NOT_FOUND, "Route inconnue")
            return

        length = int(self.headers.get("Content-Length", "0"))
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8")) if length > 0 else {}
        except Exception:
            self._send_json({"ok": False, "error": "Requête invalide."}, status=HTTPStatus.BAD_REQUEST)
            return

        if parsed.path == "/api/reset-manual":
            if CUSTOM_ELO_FILE.is_file():
                CUSTOM_ELO_FILE.unlink()
            default_map = dict(ldc_data.DEFAULT_ELO)
            self._send_json({"ok": True, "manual_elo": default_map, "default_elo": default_map})
            return

        source = payload.get("source", "clubelo")
        try:
            n_sims = int(payload.get("n_sims", DEFAULT_N_SIMS))
        except (TypeError, ValueError):
            self._send_json({"ok": False, "error": "Nombre de simulations invalide."}, status=HTTPStatus.BAD_REQUEST)
            return

        if source not in SOURCES:
            self._send_json({"ok": False, "error": f"Modèle inconnu : {source}"}, status=HTTPStatus.BAD_REQUEST)
            return
        if not MIN_N_SIMS <= n_sims <= MAX_N_SIMS:
            self._send_json(
                {"ok": False, "error": f"Choisis entre {MIN_N_SIMS} et {MAX_N_SIMS:,} simulations.".replace(",", " ")},
                status=HTTPStatus.BAD_REQUEST,
            )
            return

        elo_file: Path | None = None
        if source == "manual":
            custom_elo = payload.get("custom_elo")
            if custom_elo is not None:
                cleaned, err = ldc_data.validate_elo_map(custom_elo)
                if err or cleaned is None:
                    self._send_json({"ok": False, "error": err}, status=HTTPStatus.BAD_REQUEST)
                    return
                CUSTOM_ELO_FILE.parent.mkdir(parents=True, exist_ok=True)
                CUSTOM_ELO_FILE.write_text(json.dumps(cleaned, indent=2, ensure_ascii=False), encoding="utf-8")
            if CUSTOM_ELO_FILE.is_file():
                elo_file = CUSTOM_ELO_FILE

        with _SIM_LOCK:
            code = pipeline.run_pipeline(source=source, n_sims=n_sims, elo_file=elo_file)

        if code != 0:
            self._send_json(
                {"ok": False, "error": "Impossible d'actualiser ce modèle pour le moment."},
                status=HTTPStatus.BAD_GATEWAY,
            )
            return

        self._send_json(
            {
                "ok": True,
                "source": source,
                "output_folder": source,
                "n_sims": n_sims,
                "sources": _source_status(),
                "teams": _read_source_results(source),
                "remaining": _schedule_payload(source)["remaining"],
                "manual_elo": _get_manual_elo(),
            }
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Lance l'interface web Ligue des Champions.")
    parser.add_argument("--host", default="127.0.0.1", help="Adresse d'écoute (défaut : 127.0.0.1).")
    parser.add_argument("--port", type=int, default=8000, help="Port HTTP (défaut : 8000).")
    args = parser.parse_args(argv)

    server = ThreadingHTTPServer((args.host, args.port), LdcRequestHandler)
    url = f"http://{args.host}:{args.port}"
    print(f"Interface Ligue des Champions disponible sur {url}")
    print("Appuie sur Ctrl+C pour arrêter.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nArrêt du serveur.")
    finally:
        server.server_close()
    return 0
