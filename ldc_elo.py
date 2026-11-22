"""Récupère les notes Elo des 36 clubs de la phase de ligue.

Fonctionnement par défaut pour ClubElo (`--source clubelo`, source par défaut) :
1. Essaie d'abord l'API CSV ClubElo (`api.clubelo.com`).
2. Si l'API est indisponible (date du jour), bascule automatiquement sur la page
   HTML live https://clubelo.com/Ranking : télécharge la page à jour, remplace
   atomiquement `clubelo_ranking.html` après validation, puis extrait les notes
   depuis ce fichier HTML (et d'éventuels `clubelo_*.html` complémentaires).
3. En cas d'indisponibilité réseau totale, utilise le fichier `clubelo_ranking.html`
   déjà présent localement.

Exemples :
    python ldc_elo.py                       # ClubElo (API puis HTML auto) -> elo.json
    python ldc_elo.py --source clubelo      # idem
    python ldc_elo.py --no-download         # relit clubelo_ranking.html local sans appel réseau
    python ldc_elo.py --source beyondelo    # récupère les Elo via l'API beyondELO
    python ldc_elo.py clubelo_ranking.html  # lit explicitement un ou plusieurs fichiers HTML

Pour une date historique :
    python ldc_elo.py --source beyondelo 2026-10-01
    python ldc_elo.py --source clubelo 2026-09-07

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
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable
import urllib.error
import urllib.request

HERE = Path(__file__).resolve().parent
OUTPUT_FILE = HERE / "elo.json"
DEFAULT_HTML = HERE / "clubelo_ranking.html"
CLUBELO_RANKING_URL = "https://clubelo.com/Ranking"
BEYONDELO_API_KEY = "be_53JJFu4692fXmqaSUFz7ykzKlEOHrRlcDpUP3eZrj-s"

# Noms du projet -> variantes possibles des noms affichés par ClubElo.
# La correspondance est stricte après normalisation : pas de rapprochement
# approximatif, afin d'éviter d'attribuer l'Elo d'un mauvais club.
CLUBELO_NAMES = {
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
    """Normalise les noms de clubs et les en-têtes (accents/ponctuation ignorés)."""
    value = str(value)
    value = value.translate(str.maketrans({
        "ø": "o", "Ø": "O", "æ": "ae", "Æ": "AE",
        "œ": "oe", "Œ": "OE", "ł": "l", "Ł": "L", "ß": "ss",
    }))
    value = unicodedata.normalize("NFKD", value)
    value = "".join(c for c in value if not unicodedata.combining(c))
    return "".join(c.lower() for c in value if c.isalnum())


def _to_float(value: Any) -> float | None:
    """Convertit une valeur Elo en nombre, y compris si elle contient des espaces."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    text = str(value).strip().replace("\u00a0", "").replace(" ", "")
    if not text:
        return None
    # Enlève les éventuels séparateurs de milliers. ClubElo utilise généralement
    # un nombre simple (par exemple 1842.37), mais on tolère aussi 1,842.37.
    if "," in text and "." in text:
        text = text.replace(",", "")
    elif "," in text:
        # Une virgule suivie de trois chiffres est interprétée comme séparateur
        # de milliers ; sinon, comme séparateur décimal.
        text = text.replace(",", "") if re.search(r",\d{3}$", text) else text.replace(",", ".")
    try:
        number = float(text)
    except ValueError:
        return None
    # Plage volontairement large pour éviter de prendre un rang ou une année.
    if not 500 <= number <= 3000:
        return None
    return number


class _HTMLCollector(HTMLParser):
    """Collecte les lignes de tableaux et le contenu des balises script."""

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
        # Texte visible utile pour détecter une page Cloudflare.
        if not self._in_script and data.strip():
            self.page_text.append(data.strip())


def _row_from_dict(row: dict[str, Any]) -> tuple[str, float] | None:
    """Extrait (nom du club, Elo) d'un objet JSON / Vega."""
    values = {_norm(key): value for key, value in row.items()}
    name = next((values[k] for k in NAME_KEYS if k in values), None)
    elo_value = next((values[k] for k in ELO_KEYS if k in values), None)
    if name is None or elo_value is None:
        return None
    elo = _to_float(elo_value)
    name = str(name).strip()
    if not name or elo is None:
        return None
    return name, elo


def _walk_json(obj: Any) -> Iterable[tuple[str, float]]:
    """Parcourt récursivement un JSON pour retrouver des enregistrements Club/Elo."""
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
    """Repère les objets JSON embarqués dans les scripts (dont vegaJson)."""
    decoder = json.JSONDecoder()
    # Les pages Vega utilisent souvent `var vegaJson = {...};` ou des variables
    # équivalentes. On ajoute aussi les blocs JSON purs (type application/json).
    starts: set[int] = set()
    for match in re.finditer(r"(?:vegaJson|vegaData|vegaSpec|spec|dataset|data)\s*[:=]\s*", script, re.I):
        pos = match.end()
        while pos < len(script) and script[pos].isspace():
            pos += 1
        if pos < len(script) and script[pos] in "{[":
            starts.add(pos)
    # Cas où la spécification Vega est passée directement à vegaEmbed(...).
    for match in re.finditer(r"vegaEmbed\s*\(", script, re.I):
        pos = match.end()
        brace = script.find("{", pos)
        bracket = script.find("[", pos)
        valid = [x for x in (brace, bracket) if x >= 0]
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
    le DOM par `JSSortableEloTable`. Il échappe donc au parseur HTML statique et à JSON.
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
        # Le premier <a> contient le drapeau (<img> sans texte), le dernier contient le nom du club.
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
                # Retire un éventuel rang numérique en préfixe (ex. "117 Viking" dans un DOM sauvegardé).
                name = re.sub(r"^\d+\s+", "", data_row[name_idx].strip())
                elo = _to_float(data_row[elo_idx])
                if name and elo is not None:
                    records.append((name, elo))
            break
    return records


def extract_records_from_html(html: str) -> tuple[list[tuple[str, float]], str]:
    """Extrait les paires Club/Elo d'une page HTML téléchargée.

    Gère en priorité le tableau JS `eloData` (classement mondial complet trié par Elo),
    puis les tableaux HTML et les données JSON/Vega intégrées dans les scripts.
    Retourne aussi un résumé diagnostique de la page.
    """
    collector = _HTMLCollector()
    collector.feed(html)
    title = " ".join("".join(collector.title_parts).split())
    visible_text = " ".join(collector.page_text).lower()

    # Ne pas confondre une page de vérification Cloudflare avec un classement.
    challenge_markers = (
        "un instant", "just a moment", "checking your browser",
        "cf-chl-", "challenge-platform", "cloudflare",
    )
    if any(marker in title.lower() or marker in visible_text for marker in challenge_markers):
        # 
        raise ValueError(
            "Le fichier HTML contient une page de vérification Cloudflare, pas le classement. "
            "Ouvre ClubElo manuellement, attends la fin du chargement, puis enregistre à nouveau la page."
        )

    records: list[tuple[str, float]] = []
    for script in collector.scripts:
        records.extend(_extract_elo_data_from_script(script))
    records.extend(_extract_table_rows(collector.tables))
    for script in collector.scripts:
        for obj in _json_objects_from_script(script):
            records.extend(_walk_json(obj))

    # Déduplique les mêmes couples (nom, Elo) trouvés à la fois dans un tableau
    # et dans le JSON qui alimente le graphique.
    unique: dict[tuple[str, float], None] = {}
    for name, elo in records:
        unique[(name, round(float(elo), 3))] = None
    records = list(unique.keys())

    summary = (
        f"titre={title!r}, tableaux HTML={len(collector.tables)}, "
        f"scripts={len(collector.scripts)}, lignes Club/Elo={len(records)}"
    )
    return records, summary


def match_project_teams(records: Iterable[tuple[str, float]]) -> tuple[dict[str, int], list[str], list[str]]:
    """Fait correspondre les noms ClubElo avec les 36 noms utilisés dans le projet.

    Retourne :
      - le dictionnaire {équipe_du_projet: Elo_arrondi} ;
      - la liste des équipes manquantes ;
      - la liste des noms ClubElo effectivement reconnus.
    """
    by_name: dict[str, float] = {}
    for club_name, rating in records:
        key = _norm(club_name)
        if not key:
            continue
        # Si plusieurs pages contiennent le même club, on conserve la première
        # valeur rencontrée. Les classements nationaux doivent être téléchargés
        # le même jour pour rester cohérents.
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
    """Lit un fichier HTML avec quelques encodages courants."""
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise UnicodeError(f"Impossible de décoder le fichier {path.name}")


def _find_local_html_files() -> list[Path]:
    """Trouve la page principale et les éventuelles pages nationales locales."""
    candidates: list[Path] = []
    if DEFAULT_HTML.exists():
        candidates.append(DEFAULT_HTML)

    # Permet aussi d'agréger plusieurs pages téléchargées, par exemple
    # clubelo_ENG.html, clubelo_FRA.html, etc. La page de debug est exclue.
    for path in sorted(HERE.glob("clubelo_*.htm*")):
        if path == DEFAULT_HTML or "debug" in path.name.lower():
            continue
        if path not in candidates:
            candidates.append(path)
    return candidates


def _download_clubelo_html(dest: Path = DEFAULT_HTML) -> str:
    """Télécharge https://clubelo.com/Ranking et remplace atomiquement clubelo_ranking.html.

    Le contenu est validé via extract_records_from_html() avant tout remplacement,
    afin de ne jamais écraser un fichier local valide par une page d'erreur.
    """
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

    temp_path = dest.with_suffix(".html.tmp")
    temp_path.write_bytes(raw)
    temp_path.replace(dest)
    return summary


def _fetch_api_clubelo(date: str) -> str:
    """Essaie l'ancienne API CSV (utile si ClubElo la remet en service)."""
    errors = []
    for scheme in ("https", "http"):
        url = f"{scheme}://api.clubelo.com/{date}"
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(request, timeout=4) as response:
                text = response.read().decode("utf-8-sig")
            if "Club" not in text.splitlines()[0] or "Elo" not in text.splitlines()[0]:
                raise ValueError("La réponse ne ressemble pas au CSV ClubElo attendu")
            return text
        except Exception as exc:  # noqa: BLE001 - on essaie ensuite l'autre URL / le HTML local
            errors.append(f"{scheme}: {exc}")
    raise RuntimeError("API indisponible : " + " ; ".join(errors))


def _fetch_api_beyondelo(date: str) -> str:
    """Récupère les notes Elo depuis l'API beyondELO et les formate en CSV (Club,Elo)."""
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
        name = club.get("name")
        elo = club.get("elo")
        if name is not None and elo is not None:
            writer.writerow([name, elo])
    return buffer.getvalue()


def _parse_csv(text: str) -> list[tuple[str, float]]:
    """Convertit le CSV historique ClubElo en paires (club, Elo)."""
    rows: list[tuple[str, float]] = []
    for row in csv.DictReader(io.StringIO(text)):
        name = row.get("Club") or row.get("club") or row.get("Name")
        rating = _to_float(row.get("Elo") or row.get("elo"))
        if name and rating is not None:
            rows.append((name, rating))
    return rows


def _write_elo_json(elo: dict[str, int], date: str, source: str = "clubelo") -> None:
    """Écrit elo.json de façon atomique, sans écraser un ancien fichier si erreur."""
    payload = {"date": date, "source": source, "elo": elo}
    temp_path = OUTPUT_FILE.with_suffix(".json.tmp")
    temp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    temp_path.replace(OUTPUT_FILE)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Récupère les notes Elo des 36 clubs de la phase de ligue."
    )
    parser.add_argument(
        "-s",
        "--source",
        choices=("clubelo", "beyondelo"),
        default="clubelo",
        help="Source à utiliser : clubelo (API avec repli HTML automatique, défaut) ou beyondelo (API).",
    )
    parser.add_argument(
        "--no-download",
        action="store_true",
        help="Pour clubelo : n'appelle pas le réseau et réutilise directement clubelo_ranking.html local.",
    )
    parser.add_argument(
        "targets",
        nargs="*",
        metavar="AAAA-MM-JJ | fichier.html",
        help="Date historique (AAAA-MM-JJ) ou fichier(s) HTML ClubElo.",
    )
    parsed = parser.parse_args(argv)
    targets: list[str] = parsed.targets
    today_iso = dt.date.today().isoformat()

    def _read_html_sources(paths: list[Path]) -> tuple[list[tuple[str, float]], str]:
        collected: list[tuple[str, float]] = []
        print("Lecture des pages HTML ClubElo :")
        for path in paths:
            try:
                html = _read_html_file(path)
                page_records, summary = extract_records_from_html(html)
                collected.extend(page_records)
                print(f"  - {path.name} : {summary}")
            except Exception as exc:  # noqa: BLE001 - diagnostic de chaque fichier local
                print(f"  - {path.name} : ERREUR : {exc}")
        return collected, ", ".join(path.name for path in paths)

    # Argument(s) HTML explicite(s) : le script lit exactement les fichiers fournis sans appel réseau.
    html_args = [Path(arg).expanduser() for arg in targets if arg.lower().endswith((".html", ".htm"))]
    if html_args:
        if parsed.source == "beyondelo":
            print("L'option --source beyondelo ne s'utilise pas avec des fichiers HTML.", file=sys.stderr)
            return 2
        html_args = [p if p.is_absolute() or p.is_file() else HERE / p for p in html_args]
        missing_files = [str(p) for p in html_args if not p.is_file()]
        if missing_files:
            print("Fichier(s) HTML introuvable(s) : " + ", ".join(missing_files), file=sys.stderr)
            return 1
        records, source = _read_html_sources([p.resolve() for p in html_args])
        data_date = today_iso
    else:
        if len(targets) > 1:
            parser.print_usage(sys.stderr)
            return 2
        requested_date = targets[0] if targets else today_iso
        try:
            dt.date.fromisoformat(requested_date)
        except ValueError:
            parser.print_usage(sys.stderr)
            return 2

        if parsed.source == "clubelo" and parsed.no_download:
            html_files = _find_local_html_files()
            if not html_files:
                print(
                    "Aucun fichier HTML local trouvé (clubelo_ranking.html ou clubelo_*.html).",
                    file=sys.stderr,
                )
                return 1
            records, source = _read_html_sources(html_files)
            data_date = today_iso
        else:
            api_sources = {
                "clubelo": ("API ClubElo", _fetch_api_clubelo),
                "beyondelo": ("API beyondELO", _fetch_api_beyondelo),
            }
            api_label, fetch_fn = api_sources[parsed.source]
            try:
                if requested_date == today_iso:
                    print(f"Tentative de {api_label}...")
                else:
                    print(f"Tentative de {api_label} historique du {requested_date}...")
                csv_text = fetch_fn(requested_date)
                records = _parse_csv(csv_text)
                source = api_label
                data_date = requested_date
            except Exception as exc:
                print(f"{api_label} indisponible : {exc}", file=sys.stderr)
                if parsed.source == "clubelo" and requested_date == today_iso:
                    # Repli intégré à la pipeline ClubElo : télécharge le HTML à jour puis parse localement.
                    print(f"Bascule sur le téléchargement HTML automatique ({CLUBELO_RANKING_URL})...")
                    try:
                        summary = _download_clubelo_html(DEFAULT_HTML)
                        print(f"  OK  {DEFAULT_HTML.name} mis à jour ({summary})")
                    except Exception as dl_exc:  # noqa: BLE001 - repli sur le HTML local existant
                        print(
                            f"  Avertissement : téléchargement HTML impossible ({dl_exc}). "
                            "Utilisation du fichier local existant.",
                            file=sys.stderr,
                        )
                    html_files = _find_local_html_files()
                    if not html_files:
                        print(
                            "Aucun fichier HTML ClubElo disponible (téléchargement échoué et aucun fichier local).",
                            file=sys.stderr,
                        )
                        return 1
                    records, source = _read_html_sources(html_files)
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
        import ldc_data

        print("\nÉquipes introuvables (remplacement par DEFAULT_ELO de ldc_data.py) :")
        for team in missing:
            default_val = int(ldc_data.DEFAULT_ELO[team])
            elo[team] = default_val
            print(f"  DEFAULT  {team} <- {default_val}")

    _write_elo_json(elo, data_date, source=parsed.source)
    print(f"\nelo.json mis à jour : {len(elo)} équipes, date d'enregistrement {data_date}.")
    print(f"Source : {source}")
    print(f"Fichier créé : {OUTPUT_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
