"""Récupération et normalisation des notes Elo des 36 clubs (ClubElo et beyondELO).

Pipeline ClubElo (`--source clubelo`, défaut) :
1. Tente d'abord l'API CSV ClubElo (`api.clubelo.com`).
2. Si l'API échoue (date du jour), télécharge automatiquement https://clubelo.com/Ranking,
   valide les données extraites puis remplace atomiquement `data/clubelo_ranking.html`
   avant de parser le tableau JavaScript `eloData` (~1 750 clubs, 36/36 reconnus).
3. En cas d'absence de réseau, bascule sur le fichier `data/clubelo_ranking.html` local.

Dépendances : bibliothèque standard Python uniquement.
"""
from __future__ import annotations

import argparse
import ast
import csv
import datetime as dt
import html as html_lib
import io
import json
import re
import sys
import unicodedata
import urllib.error
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable

from ldc.config import (
    BEYONDELO_API_KEY,
    CLUBELO_HTML_FILE,
    CLUBELO_RANKING_URL,
    DATA_DIR,
    ELO_FILE,
    MAX_ELO,
    MIN_ELO,
    ROOT_DIR,
)
from ldc.data import DEFAULT_ELO, write_elo_json

# Noms du projet -> variantes possibles des noms affichés par ClubElo / beyondELO.
# Correspondance stricte après normalisation : évite d'attribuer l'Elo d'un mauvais club.
CLUBELO_NAMES: dict[str, list[str]] = {
    "AEK": ["AEK", "AEK Athens"],
    "Arsenal": ["Arsenal"],
    "Aston Villa": ["Aston Villa"],
    "Atletico": ["Atletico", "Atlético", "Atletico Madrid", "Atlético Madrid"],
    "Dortmund": ["Dortmund", "Borussia Dortmund"],
    "Barcelona": ["Barcelona", "FC Barcelona"],
    "Bayern": ["Bayern", "Bayern München", "Bayern Munich"],
    "Bodo/Glimt": ["Bodoe Glimt", "Bodo Glimt", "Bodo/Glimt", "Bodø/Glimt"],
    "Club Brugge": ["Brugge", "Club Brugge"],
    "Como": ["Como"],
    "Fenerbahce": ["Fenerbahce", "Fenerbahçe"],
    "Feyenoord": ["Feyenoord"],
    "Galatasaray": ["Galatasaray"],
    "Inter": ["Inter", "Internazionale"],
    "LASK": ["LASK", "LASK Linz"],
    "Leipzig": ["Leipzig", "RB Leipzig"],
    "Lens": ["Lens"],
    "Lille": ["Lille"],
    "Liverpool": ["Liverpool"],
    "Man City": ["Man City", "Manchester City"],
    "Man United": ["Man United", "Manchester United", "Man Utd"],
    "Napoli": ["Napoli"],
    "PSG": ["Paris SG", "PSG", "Paris Saint-Germain"],
    "Porto": ["Porto", "FC Porto"],
    "PSV": ["PSV", "PSV Eindhoven"],
    "Real Betis": ["Betis", "Real Betis"],
    "Real Madrid": ["Real Madrid"],
    "Roma": ["Roma", "AS Roma"],
    "Slovan Bratislava": ["Slovan", "Slovan Bratislava"],
    "Sabah": ["Sabah", "Sabah FK", "Sabah Baku"],
    "Shakhtar": ["Shakhtar", "Shakhtar Donetsk"],
    "Slavia Praha": ["Slavia Praha", "Slavia Prague"],
    "Sporting CP": ["Sporting", "Sporting CP", "Sporting Lisbon"],
    "Stuttgart": ["Stuttgart", "VfB Stuttgart"],
    "Viking": ["Viking", "Viking FK"],
    "Villarreal": ["Villarreal"],
}

# Noms de colonnes possibles dans les tableaux HTML / jeux de données Vega.
NAME_KEYS = ("club", "clubname", "team", "teamname", "name", "nom")
ELO_KEYS = ("elo", "clubelo", "elorating", "rating")


def _norm(value: Any) -> str:
    """Normalise un nom de club ou un en-tête (accents, casse et ponctuation ignorés)."""
    text = str(value).translate(str.maketrans({
        "ø": "o", "Ø": "O", "æ": "ae", "Æ": "AE",
        "œ": "oe", "Œ": "OE", "ł": "l", "Ł": "L", "ß": "ss",
    }))
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return "".join(c.lower() for c in text if c.isalnum())


def _to_float(value: Any) -> float | None:
    """Convertit une valeur Elo en flottant valide dans [MIN_ELO, MAX_ELO]."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = float(value)
        return number if MIN_ELO <= number <= MAX_ELO else None
    text = str(value).strip().replace("\u00a0", "").replace(" ", "")
    if not text:
        return None
    if "," in text and "." in text:
        text = text.replace(",", "")
    elif "," in text:
        text = text.replace(",", "") if re.search(r",\d{3}$", text) else text.replace(",", ".")
    try:
        number = float(text)
    except ValueError:
        return None
    return number if MIN_ELO <= number <= MAX_ELO else None


class _HTMLCollector(HTMLParser):
    """Collecte les lignes de tableaux HTML et le contenu des balises `<script>`."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[str]]] = []
        self.scripts: list[str] = []
        self.title_parts: list[str] = []
        self.page_text: list[str] = []
        self._table: list[list[str]] | None = None
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self._in_script = False
        self._script_parts: list[str] = []
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag == "title":
            self._in_title = True
        elif tag == "script":
            self._in_script = True
            self._script_parts = []
        elif tag == "table":
            self._table = []
        elif tag == "tr" and self._table is not None:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "title":
            self._in_title = False
        elif tag == "script" and self._in_script:
            self.scripts.append("".join(self._script_parts))
            self._in_script = False
        elif tag in ("td", "th") and self._cell is not None and self._row is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None and self._table is not None:
            if self._row:
                self._table.append(self._row)
            self._row = None
        elif tag == "table" and self._table is not None:
            self.tables.append(self._table)
            self._table = None

    def handle_data(self, data: str) -> None:
        if self._in_script:
            self._script_parts.append(data)
        if self._in_title:
            self.title_parts.append(data)
        if self._cell is not None:
            self._cell.append(data)
        if not self._in_script and data.strip():
            self.page_text.append(data.strip())


def _row_from_dict(row: dict[str, Any]) -> tuple[str, float] | None:
    """Extrait `(nom_club, elo)` d'un objet JSON / Vega."""
    values = {_norm(key): value for key, value in row.items()}
    name = next((values[k] for k in NAME_KEYS if k in values), None)
    elo_value = next((values[k] for k in ELO_KEYS if k in values), None)
    if name is None or elo_value is None:
        return None
    elo = _to_float(elo_value)
    name = str(name).strip()
    return (name, elo) if name and elo is not None else None


def _walk_json(obj: Any) -> Iterable[tuple[str, float]]:
    """Parcourt récursivement une structure JSON pour trouver des couples Club/Elo."""
    if isinstance(obj, dict):
        record = _row_from_dict(obj)
        if record:
            yield record
        for value in obj.values():
            yield from _walk_json(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from _walk_json(value)


def _json_objects_from_script(script: str) -> Iterable[Any]:
    """Repère les objets JSON embarqués dans les scripts (dont `vegaJson`)."""
    decoder = json.JSONDecoder()
    starts: set[int] = set()
    for match in re.finditer(r"(?:vegaJson|vegaData|vegaSpec|spec|dataset|data)\s*[:=]\s*", script, re.I):
        pos = match.end()
        while pos < len(script) and script[pos].isspace():
            pos += 1
        if pos < len(script) and script[pos] in "{[":
            starts.add(pos)
    for match in re.finditer(r"vegaEmbed\s*\(", script, re.I):
        pos = match.end()
        valid = [x for x in (script.find("{", pos), script.find("[", pos)) if x >= 0]
        if valid:
            starts.add(min(valid))
    stripped = script.strip()
    if stripped.startswith(("{", "[")):
        starts.add(script.find(stripped))

    for start in sorted(starts):
        try:
            value, _ = decoder.raw_decode(script[start:])
        except json.JSONDecodeError:
            continue
        yield value


def _extract_elo_data_from_script(script: str) -> list[tuple[str, float]]:
    """Extrait le tableau JS `const eloData = [['<td...>...</td>', '2044', ...], ...]` de ClubElo.

    Sur https://clubelo.com/Ranking, le classement complet (~1 750 clubs, trié par Elo
    décroissant) est embarqué dans ce tableau JS à guillemets simples puis injecté dans
    le DOM par `JSSortableEloTable`.
    """
    match = re.search(r"(?:const|let|var)\s+eloData\s*=\s*(\[\[.*?\]\])\s*;", script, re.S)
    if not match:
        return []

    raw_rows: list[tuple[str, str]] = []
    try:
        parsed = ast.literal_eval(match.group(1))
        if isinstance(parsed, list):
            for row in parsed:
                if isinstance(row, (list, tuple)) and len(row) >= 2:
                    raw_rows.append((str(row[0]), str(row[1])))
    except (SyntaxError, ValueError):
        for cell_html, elo_str in re.findall(
            r"\[\s*'(<td\b.*?</td>)'\s*,\s*'([^']+)'", match.group(1), re.S
        ):
            raw_rows.append((cell_html, elo_str))

    records: list[tuple[str, float]] = []
    for cell_html, elo_str in raw_rows:
        elo = _to_float(elo_str)
        if elo is None:
            continue
        links = re.findall(r"<a\b[^>]*>(.*?)</a>", cell_html, re.S | re.I)
        if not links:
            continue
        # Le premier <a> contient le drapeau (<img>), le dernier contient le nom du club.
        name = html_lib.unescape(re.sub(r"<[^>]+>", "", links[-1])).strip()
        if name:
            records.append((name, elo))
    return records


def _extract_table_rows(tables: list[list[list[str]]]) -> list[tuple[str, float]]:
    """Lit les tableaux HTML ayant une ligne d'en-tête Club/Elo."""
    records: list[tuple[str, float]] = []
    for table in tables:
        for header_index, row in enumerate(table[:5]):
            headers = [_norm(cell) for cell in row]
            name_idx = next((i for i, h in enumerate(headers) if h in NAME_KEYS), None)
            elo_idx = next((i for i, h in enumerate(headers) if h in ELO_KEYS), None)
            if name_idx is None or elo_idx is None:
                continue
            for data_row in table[header_index + 1:]:
                if max(name_idx, elo_idx) >= len(data_row):
                    continue
                name = re.sub(r"^\d+\s+", "", data_row[name_idx].strip())
                elo = _to_float(data_row[elo_idx])
                if name and elo is not None:
                    records.append((name, elo))
            break
    return records


def extract_records_from_html(html: str) -> tuple[list[tuple[str, float]], str]:
    """Extrait les couples `(club, elo)` d'une page HTML ClubElo et renvoie un diagnostic.

    Priorité : tableau JS `eloData` (trié par Elo décroissant -> évite les collisions
    d'homonymes), puis tableaux HTML statiques, puis objets JSON/Vega.
    """
    collector = _HTMLCollector()
    collector.feed(html)
    title = " ".join("".join(collector.title_parts).split())
    visible_text = " ".join(collector.page_text).lower()

    challenge_markers = (
        "un instant", "just a moment", "checking your browser",
        "cf-chl-", "challenge-platform", "cloudflare",
    )
    if any(marker in title.lower() or marker in visible_text for marker in challenge_markers):
        raise ValueError(
            "Le fichier HTML contient une page de vérification Cloudflare, pas le classement."
        )

    records: list[tuple[str, float]] = []
    for script in collector.scripts:
        records.extend(_extract_elo_data_from_script(script))
    records.extend(_extract_table_rows(collector.tables))
    for script in collector.scripts:
        for obj in _json_objects_from_script(script):
            records.extend(_walk_json(obj))

    unique: dict[tuple[str, float], None] = {}
    for name, elo in records:
        unique[(name, round(float(elo), 3))] = None
    deduped = list(unique.keys())

    summary = (
        f"titre={title!r}, tableaux HTML={len(collector.tables)}, "
        f"scripts={len(collector.scripts)}, lignes Club/Elo={len(deduped)}"
    )
    return deduped, summary


def match_project_teams(records: Iterable[tuple[str, float]]) -> tuple[dict[str, int], list[str], list[str]]:
    """Associe les couples `(club, elo)` aux 36 clubs du projet via `CLUBELO_NAMES`."""
    by_name: dict[str, float] = {}
    for club_name, rating in records:
        key = _norm(club_name)
        if key:
            by_name.setdefault(key, float(rating))

    elo: dict[str, int] = {}
    missing: list[str] = []
    matched_names: list[str] = []

    for project_name, variants in CLUBELO_NAMES.items():
        found = None
        found_name = None
        for variant in variants:
            key = _norm(variant)
            if key in by_name:
                found = by_name[key]
                found_name = variant
                break
        if found is None:
            missing.append(project_name)
        else:
            elo[project_name] = round(found)
            matched_names.append(f"{project_name} <- {found_name} ({round(found)})")

    return elo, missing, matched_names


def _read_html_file(path: Path) -> str:
    """Lit un fichier HTML en essayant plusieurs encodages courants."""
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise UnicodeError(f"Impossible de décoder le fichier {path.name}")


def _find_local_html_files() -> list[Path]:
    """Trouve `data/clubelo_ranking.html` et d'éventuelles pages `clubelo_*.html` complémentaires."""
    candidates: list[Path] = []
    if CLUBELO_HTML_FILE.exists():
        candidates.append(CLUBELO_HTML_FILE)

    for folder in (DATA_DIR, ROOT_DIR):
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob("clubelo_*.htm*")):
            if "debug" in path.name.lower() or path in candidates:
                continue
            candidates.append(path)
    return candidates


def _download_clubelo_html(dest: Path = CLUBELO_HTML_FILE) -> str:
    """Télécharge https://clubelo.com/Ranking et remplace atomiquement `data/clubelo_ranking.html`."""
    request = urllib.request.Request(
        CLUBELO_RANKING_URL,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        raw = response.read()

    html = raw.decode("utf-8", errors="replace")
    records, summary = extract_records_from_html(html)
    if not records:
        raise ValueError(f"Aucune donnée Club/Elo extraite depuis {CLUBELO_RANKING_URL} ({summary})")

    dest.parent.mkdir(parents=True, exist_ok=True)
    temp_path = dest.with_suffix(".html.tmp")
    temp_path.write_bytes(raw)
    temp_path.replace(dest)
    return summary


def _fetch_api_clubelo(date: str) -> str:
    """Interroge l'API CSV historique ClubElo."""
    errors = []
    for scheme in ("https", "http"):
        url = f"{scheme}://api.clubelo.com/{date}"
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(request, timeout=4) as response:
                text = response.read().decode("utf-8-sig")
            first_line = text.splitlines()[0] if text else ""
            if "Club" not in first_line or "Elo" not in first_line:
                raise ValueError("La réponse ne ressemble pas au CSV ClubElo attendu")
            return text
        except Exception as exc:  # noqa: BLE001 - essaie le schéma suivant puis le HTML
            errors.append(f"{scheme}: {exc}")
    raise RuntimeError("API indisponible : " + " ; ".join(errors))


def _fetch_api_beyondelo(date: str) -> str:
    """Récupère les notes Elo depuis l'API beyondELO et les normalise au format CSV `(Club, Elo)`."""
    url = f"https://public-api.beyondelo.com/v1/rankings/clubs?date={date}"
    request = urllib.request.Request(
        url,
        headers={
            "X-API-Key": BEYONDELO_API_KEY,
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"API beyondELO HTTP {exc.code} : {body}") from exc
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"API beyondELO indisponible : {exc}") from exc

    clubs = payload.get("data")
    if not isinstance(clubs, list):
        raise ValueError("La réponse beyondELO ne contient pas la liste 'data' attendue")

    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["Club", "Elo"])
    for club in clubs:
        name, elo = club.get("name"), club.get("elo")
        if name is not None and elo is not None:
            writer.writerow([name, elo])
    return buffer.getvalue()


def _parse_csv(text: str) -> list[tuple[str, float]]:
    """Convertit un CSV `Club,Elo` en liste de couples `(club, elo)`."""
    rows: list[tuple[str, float]] = []
    for row in csv.DictReader(io.StringIO(text)):
        name = row.get("Club") or row.get("club") or row.get("Name")
        rating = _to_float(row.get("Elo") or row.get("elo"))
        if name and rating is not None:
            rows.append((name, rating))
    return rows


def _read_html_sources(paths: list[Path]) -> tuple[list[tuple[str, float]], str]:
    """Lit et agrège un ou plusieurs fichiers HTML ClubElo locaux."""
    collected: list[tuple[str, float]] = []
    print("Lecture des pages HTML ClubElo :")
    for path in paths:
        try:
            html = _read_html_file(path)
            page_records, summary = extract_records_from_html(html)
            collected.extend(page_records)
            print(f"  - {path.name} : {summary}")
        except Exception as exc:  # noqa: BLE001
            print(f"  - {path.name} : ERREUR : {exc}")
    return collected, ", ".join(path.name for path in paths)


def fetch_and_save_elo(
    source: str = "clubelo",
    date: str | None = None,
    no_download: bool = False,
    html_files: list[Path] | None = None,
) -> int:
    """Récupère les notes Elo selon la source choisie et écrit `data/elo.json`."""
    today_iso = dt.date.today().isoformat()
    requested_date = date or today_iso

    if html_files:
        records, origin_label = _read_html_sources(html_files)
        data_date = today_iso
    elif source == "clubelo" and no_download:
        local_files = _find_local_html_files()
        if not local_files:
            print("Aucun fichier HTML local trouvé dans data/ (clubelo_ranking.html).", file=sys.stderr)
            return 1
        records, origin_label = _read_html_sources(local_files)
        data_date = today_iso
    else:
        api_sources = {
            "clubelo": ("API ClubElo", _fetch_api_clubelo),
            "beyondelo": ("API beyondELO", _fetch_api_beyondelo),
        }
        api_label, fetch_fn = api_sources[source]
        try:
            if requested_date == today_iso:
                print(f"Tentative de {api_label}...")
            else:
                print(f"Tentative de {api_label} historique du {requested_date}...")
            csv_text = fetch_fn(requested_date)
            records = _parse_csv(csv_text)
            origin_label = api_label
            data_date = requested_date
        except Exception as exc:
            print(f"{api_label} indisponible : {exc}", file=sys.stderr)
            if source == "clubelo" and requested_date == today_iso:
                print(f"Bascule sur le téléchargement HTML automatique ({CLUBELO_RANKING_URL})...")
                try:
                    summary = _download_clubelo_html(CLUBELO_HTML_FILE)
                    print(f"  OK  {CLUBELO_HTML_FILE.name} mis à jour ({summary})")
                except Exception as dl_exc:  # noqa: BLE001
                    print(
                        f"  Avertissement : téléchargement HTML impossible ({dl_exc}). "
                        "Utilisation du fichier local existant.",
                        file=sys.stderr,
                    )
                local_files = _find_local_html_files()
                if not local_files:
                    print("Aucun fichier HTML ClubElo disponible.", file=sys.stderr)
                    return 1
                records, origin_label = _read_html_sources(local_files)
                data_date = today_iso
            else:
                if requested_date != today_iso:
                    print("Une page HTML actuelle ne peut pas remplacer un classement historique.", file=sys.stderr)
                return 1

    elo, missing, matched = match_project_teams(records)
    print(f"\nÉquipes reconnues : {len(elo)}/{len(CLUBELO_NAMES)}")
    for line in matched:
        print("  OK  " + line)

    if not elo:
        print("\nAucune équipe reconnue : elo.json n'a PAS été modifié.", file=sys.stderr)
        return 1

    if missing:
        print("\nÉquipes introuvables (remplacement par DEFAULT_ELO) :")
        for team in missing:
            default_val = int(DEFAULT_ELO[team])
            elo[team] = default_val
            print(f"  DEFAULT  {team} <- {default_val}")

    write_elo_json(elo, data_date, source=source, path=ELO_FILE)
    print(f"\nelo.json mis à jour : {len(elo)} équipes, date d'enregistrement {data_date}.")
    print(f"Source : {origin_label}")
    print(f"Fichier créé : {ELO_FILE}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Récupère les notes Elo des 36 clubs de la phase de ligue."
    )
    parser.add_argument(
        "-s",
        "--source",
        choices=("clubelo", "beyondelo"),
        default="clubelo",
        help="Source : clubelo (API avec repli HTML automatique, défaut) ou beyondelo (API).",
    )
    parser.add_argument(
        "--no-download",
        action="store_true",
        help="Pour clubelo : réutilise directement data/clubelo_ranking.html sans appel réseau.",
    )
    parser.add_argument(
        "targets",
        nargs="*",
        metavar="AAAA-MM-JJ | fichier.html",
        help="Date historique (AAAA-MM-JJ) ou fichier(s) HTML ClubElo.",
    )
    parsed = parser.parse_args(argv)
    targets: list[str] = parsed.targets

    html_args = [Path(arg).expanduser() for arg in targets if arg.lower().endswith((".html", ".htm"))]
    if html_args:
        if parsed.source == "beyondelo":
            print("L'option --source beyondelo ne s'utilise pas avec des fichiers HTML.", file=sys.stderr)
            return 2
        resolved_files: list[Path] = []
        for path in html_args:
            candidate = path if path.is_absolute() or path.is_file() else (DATA_DIR / path)
            if not candidate.is_file():
                candidate = ROOT_DIR / path
            if not candidate.is_file():
                print(f"Fichier HTML introuvable : {path}", file=sys.stderr)
                return 1
            resolved_files.append(candidate.resolve())
        return fetch_and_save_elo(source=parsed.source, html_files=resolved_files)

    if len(targets) > 1:
        parser.print_usage(sys.stderr)
        return 2

    requested_date = targets[0] if targets else None
    if requested_date is not None:
        try:
            dt.date.fromisoformat(requested_date)
        except ValueError:
            parser.print_usage(sys.stderr)
            return 2

    return fetch_and_save_elo(
        source=parsed.source,
        date=requested_date,
        no_download=parsed.no_download,
    )


if __name__ == "__main__":
    raise SystemExit(main())
