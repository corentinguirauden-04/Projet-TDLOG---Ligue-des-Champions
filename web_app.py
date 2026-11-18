"""Serveur web léger (bibliothèque standard Python) pour l'interface Ligue des Champions.

Lancement :
    python web_app.py
    python web_app.py --port 8080

Rôle dans l'architecture :
    - Sert l'interface web interactive depuis web/index.html.
    - Sert les visuels PNG et CSV générés dans outputs/.
    - Expose les routes API JSON :
        * GET  /api/state?source=<src> : état des modèles, projections, calendrier et Elo manuel.
        * POST /api/simulate           : relance la simulation (avec Elo personnalisé optionnel).
        * POST /api/reset-manual       : remet l'Elo personnalisé aux valeurs par défaut (DEFAULT_ELO).
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

import generate_outputs
import ldc_data
import ldc_sim


BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "web"
OUTPUTS_DIR = BASE_DIR / "outputs"
CUSTOM_ELO_FILE = OUTPUTS_DIR / "manual" / "custom_elo.json"
SOURCES = ("clubelo", "beyondelo", "manual")
SOURCE_LABELS = {
    "clubelo": "ClubElo",
    "beyondelo": "beyondELO",
    "manual": "Personnalisé",
}

_SIM_LOCK = threading.Lock()


def _resolve_output_folder(source: str) -> str:
    """Retourne le dossier d'outputs effectif (clubelo utilise html en secours si besoin)."""
    if (OUTPUTS_DIR / source / "probabilites_equipes.csv").is_file():
        return source
    if source == "clubelo" and (OUTPUTS_DIR / "html" / "probabilites_equipes.csv").is_file():
        return "html"
    return source


def _source_status() -> list[dict]:
    """Indique pour chaque modèle si ses projections sont disponibles."""
    items = []
    for src in SOURCES:
        folder = _resolve_output_folder(src)
        csv_path = OUTPUTS_DIR / folder / "probabilites_equipes.csv"
        items.append(
            {
                "id": src,
                "label": SOURCE_LABELS[src],
                "available": csv_path.is_file(),
                "folder": folder,
            }
        )
    return items


def _get_manual_elo() -> dict[str, int]:
    """Retourne l'Elo personnalisé courant (ou DEFAULT_ELO par défaut)."""
    if CUSTOM_ELO_FILE.is_file():
        try:
            data = json.loads(CUSTOM_ELO_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict) and set(data) == set(ldc_data.DEFAULT_ELO):
                return {k: int(round(float(v))) for k, v in data.items()}
        except Exception:
            pass
    return {k: int(v) for k, v in ldc_data.DEFAULT_ELO.items()}


def _validate_custom_elo(raw_elo: object) -> tuple[dict[str, int] | None, str | None]:
    """Vérifie que les 36 équipes sont présentes avec des notes entre 500 et 3000."""
    if not isinstance(raw_elo, dict):
        return None, "Le format des notes personnalisées est invalide."
    expected_teams = set(ldc_data.DEFAULT_ELO)
    if set(raw_elo.keys()) != expected_teams:
        return None, "Les 36 équipes de la compétition doivent être renseignées."

    cleaned: dict[str, int] = {}
    for team, val in raw_elo.items():
        try:
            num = int(round(float(val)))
        except (TypeError, ValueError):
            return None, f"La note de {team} doit être un nombre entier."
        if not 500 <= num <= 3000:
            return None, f"La note de {team} ({num}) doit être comprise entre 500 et 3 000."
        cleaned[team] = num
    return cleaned, None


def _schedule_payload() -> dict:
    """Construit la liste des matchs joués (J1-J4) et à venir (J5-J8)."""
    played = [
        {
            "matchday": idx // 18 + 1,
            "home": h,
            "away": a,
            "hg": int(hg),
            "ag": int(ag),
        }
        for idx, (h, a, hg, ag) in enumerate(ldc_data.PLAYED)
    ]
    remaining = [
        {
            "matchday": idx // 18 + 5,
            "home": h,
            "away": a,
        }
        for idx, (h, a) in enumerate(ldc_data.REMAINING)
    ]
    return {"played": played, "remaining": remaining}


def _read_source_results(source: str) -> list[dict]:
    """Lit les probabilités et enrichit chaque équipe avec son classement réel J4."""
    folder = _resolve_output_folder(source)
    csv_path = OUTPUTS_DIR / folder / "probabilites_equipes.csv"
    if not csv_path.is_file():
        return []

    current_by_team = {row["team"]: row for row in ldc_sim.current_table()}
    rows: list[dict] = []

    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        for raw in csv.DictReader(f, delimiter=";"):
            team = raw["equipe"]
            rank_probs = [float(raw[f"probabilite_place_{p}"]) for p in range(1, 37)]
            cur = current_by_team.get(team, {"rank": 0, "pts": 0, "gd": 0, "gf": 0, "ga": 0})
            rows.append(
                {
                    "team": team,
                    "slug": generate_outputs.safe_filename(team),
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
                    "cur_pts": int(cur["pts"]),
                    "cur_gd": int(cur["gd"]),
                    "cur_gf": int(cur["gf"]),
                    "cur_ga": int(cur["ga"]),
                }
            )

    rows.sort(key=lambda r: (-r["exp_pts"], -r["top8"], -r["top24"]))
    return rows


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

        if path.startswith("/outputs/"):
            rel = unquote(path[len("/outputs/"):])
            target = (OUTPUTS_DIR / rel).resolve()
            if OUTPUTS_DIR.resolve() not in target.parents and target != OUTPUTS_DIR.resolve():
                self.send_error(HTTPStatus.FORBIDDEN, "Accès refusé")
                return
            self._send_file(target)
            return

        if path == "/api/state":
            params = parse_qs(parsed.query)
            sources = _source_status()
            available_ids = [s["id"] for s in sources if s["available"]]
            requested = params.get("source", [None])[0]
            active = requested if requested in SOURCES else (available_ids[0] if available_ids else "beyondelo")
            folder = _resolve_output_folder(active)
            teams = _read_source_results(active) if active in available_ids else []
            schedule = _schedule_payload()

            self._send_json(
                {
                    "sources": sources,
                    "active_source": active,
                    "output_folder": folder,
                    "available": active in available_ids,
                    "teams": teams,
                    "played": schedule["played"],
                    "remaining": schedule["remaining"],
                    "default_elo": {k: int(v) for k, v in ldc_data.DEFAULT_ELO.items()},
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
            default_map = {k: int(v) for k, v in ldc_data.DEFAULT_ELO.items()}
            self._send_json({"ok": True, "manual_elo": default_map, "default_elo": default_map})
            return

        source = payload.get("source", "clubelo")
        try:
            n_sims = int(payload.get("n_sims", generate_outputs.DEFAULT_N_SIMS))
        except (TypeError, ValueError):
            self._send_json({"ok": False, "error": "Nombre de simulations invalide."}, status=HTTPStatus.BAD_REQUEST)
            return

        if source not in SOURCES:
            self._send_json({"ok": False, "error": f"Modèle inconnu : {source}"}, status=HTTPStatus.BAD_REQUEST)
            return
        if not 100 <= n_sims <= 500_000:
            self._send_json(
                {"ok": False, "error": "Choisis entre 100 et 500 000 simulations."},
                status=HTTPStatus.BAD_REQUEST,
            )
            return

        args = [str(n_sims), "--source", source]
        if source == "manual":
            custom_elo = payload.get("custom_elo")
            if custom_elo is not None:
                cleaned, err = _validate_custom_elo(custom_elo)
                if err:
                    self._send_json({"ok": False, "error": err}, status=HTTPStatus.BAD_REQUEST)
                    return
                CUSTOM_ELO_FILE.parent.mkdir(parents=True, exist_ok=True)
                CUSTOM_ELO_FILE.write_text(json.dumps(cleaned, indent=2, ensure_ascii=False), encoding="utf-8")
            if CUSTOM_ELO_FILE.is_file():
                args.extend(["--elo-file", str(CUSTOM_ELO_FILE)])
        else:
            args.append("--refresh")

        with _SIM_LOCK:
            code = generate_outputs.main(args)

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
                "output_folder": _resolve_output_folder(source),
                "n_sims": n_sims,
                "sources": _source_status(),
                "teams": _read_source_results(source),
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


if __name__ == "__main__":
    raise SystemExit(main())
