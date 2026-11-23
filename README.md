# Simulateur Monte Carlo — Ligue des Champions 2026-2027

Application Python + interface web interactive permettant d'estimer les probabilités de qualification des **36 clubs** de la phase de ligue de la Ligue des Champions, de générer les graphiques analytiques complets et de les explorer dans le navigateur.

Le projet combine :
- les résultats réels et le calendrier officiel de la phase de ligue (144 matchs, 8 journées) ;
- trois sources de notes Elo (**ClubElo** automatisé, **beyondELO** via API, **Personnalisé** manuel) ;
- un moteur Monte Carlo vectorisé NumPy (loi de Poisson avec Elo fixe tout au long de chaque simulation) ;
- une génération complète de visuels Matplotlib (fiches par club, distributions par place, vues globales, CSV) ;
- une interface web interactive (`web_app.py` / `web/`) sans framework externe.

---

## 1. Architecture & organisation du dépôt

Le dépôt suit une **architecture en couches** combinée à une **pipeline de traitement** (côté calcul batch) et un modèle **Client–Serveur / MVC** (côté web) :

- **Modèle & données (`src/ldc/config.py`, `data.py`, `elo.py`, `simulation.py`)** : configuration centralisée, invariants calendrier, ingestion Elo et moteur mathématique pur (aucune écriture disque ni affichage dans `simulation.py`).
- **Présentation & orchestration (`src/ldc/visualization.py`, `pipeline.py`)** : rendu Matplotlib factorisé et orchestration unique (`main.py`).
- **Contrôleur & Vue web (`src/ldc/web_server.py` + `web/{index.html,styles.css,app.js}`)** : API REST JSON légère, verrouillage thread-safe (`_SIM_LOCK`) et séparation stricte HTML / CSS / JS côté frontend.

```text
Projet-TDLOG---Ligue-des-Champions/
├── README.md
├── requirements.txt
├── .gitignore
├── main.py                              # Point d'entrée CLI de la pipeline
├── web_app.py                           # Point d'entrée du serveur web
├── src/
│   └── ldc/
│       ├── __init__.py
│       ├── config.py                    # Chemins et constantes centralisés
│       ├── data.py                      # Calendrier (PLAYED/REMAINING), DEFAULT_ELO, validation & I/O Elo
│       ├── elo.py                       # Ingestion ClubElo (API -> HTML auto) et beyondELO (API)
│       ├── simulation.py                # Moteur Monte Carlo vectorisé NumPy + indicateurs
│       ├── visualization.py             # Graphiques Matplotlib (style "plateau télé")
│       ├── pipeline.py                  # Orchestration complète + export CSV
│       └── web_server.py                # Serveur HTTP (stdlib) + API JSON REST
├── web/
│   ├── index.html                       # Structure HTML (SPA 6 onglets)
│   ├── styles.css                       # Identité visuelle et responsive CSS
│   └── app.js                           # État client, appels fetch et rendu dynamique
├── data/
│   ├── elo.json                         # Dernières notes Elo chargées par la simulation
│   └── clubelo_ranking.html             # Instantané HTML ClubElo mis à jour automatiquement
├── outputs/
│   ├── clubelo/
│   │   ├── equipes/<club>/{classement,points,matchs_cles}.png
│   │   ├── classements/{1..36}.png
│   │   ├── classement_global.png
│   │   ├── seuils_points_top_8_16_24.png
│   │   └── probabilites_equipes.csv
│   ├── beyondelo/
│   └── manual/
├── tests/
│   └── test_ldc.py                      # Tests unitaires et d'intégration (unittest)
└── scripts/
    └── prototype_match.py               # Prototype initial de calibration sur un match unique
```

---

## 2. Installation

Seuls **NumPy** et **Matplotlib** sont nécessaires (la CLI, le parsing HTML/HTTP, le serveur web et les tests reposent uniquement sur la bibliothèque standard Python).

```powershell
python -m pip install -r requirements.txt
```

> **Variable d'environnement optionnelle :** la clé API beyondELO peut être surchargée via `BEYONDELO_API_KEY` (une clé par défaut est définie dans `src/ldc/config.py`).

---

## 3. Points d'entrée & utilisation

### Lancer la pipeline complète (`main.py`)

```powershell
python main.py                                    # mode interactif (clubelo par défaut)
python main.py --source clubelo                   # ClubElo : API -> repli HTML auto -> outputs/clubelo/
python main.py --source beyondelo                 # API beyondELO -> outputs/beyondelo/
python main.py --source manual                    # DEFAULT_ELO -> outputs/manual/
python main.py --source manual --elo-file f.json  # Elo personnalisé JSON -> outputs/manual/
python main.py --source beyondelo --n-sims 250000 # personnaliser le nombre de simulations
python main.py --source clubelo --no-refresh      # réutiliser data/clubelo_ranking.html hors-ligne
```

Par défaut, **100 000 simulations Monte Carlo** sont exécutées (`seed=42`) et produisent dans `outputs/<source>/` :
- `equipes/<club>/classement.png` : distribution des 36 places finales (36e à gauche → 1re à droite), encadrés alignés au-dessus de leurs zones (*Élimination* / *Barrages* / *Top 8*), rang moyen et points moyens (avec écarts-types) ;
- `equipes/<club>/points.png` : distribution des points finaux, moyenne (vert-cyan), écart-type, plage probable 80 % (jaune) et points actuels/max ;
- `equipes/<club>/matchs_cles.png` : Top 10 des matchs restants les plus décisifs (propres matchs et matchs des concurrents), classés par le plus grand écart de classement moyen (en places) entre les 3 issues (`1` / `N` / `2`) ;
- `classements/1.png` à `36.png` : distribution du nombre de points du club terminant exactement à la place `x` (moyenne, écart-type, plage 80 %, score le plus fréquent) ;
- `classement_global.png` : vue globale des 36 clubs en barres empilées Top 8 / barrages / éliminé ;
- `seuils_points_top_8_16_24.png` : barres empilées à 100 % indiquant la probabilité d'issue finale selon le nombre de points (avec moyenne, écart-type et mode des seuils Top 8 / 16 / 24) ;
- `probabilites_equipes.csv` : tableau CSV complet des probabilités (y compris chacune des 36 places).

Le sous-titre de l'ensemble des graphiques affiche dynamiquement la journée calculée depuis `data.PLAYED` et la date des notes Elo (`après la journée n, en date du xxx`).

### Lancer l'interface web interactive (`web_app.py`)

```powershell
python web_app.py
```

Puis ouvrir **`http://127.0.0.1:8000`**.

Pour accéder au site depuis un autre appareil du même réseau Wi-Fi (ex. un téléphone) :

```powershell
python web_app.py --host 0.0.0.0
```

Puis ouvrir `http://<IPv4-du-PC>:8000` (`ipconfig` sous Windows).

**Onglets disponibles dans l'interface :**
- **Barre de contrôle :** choix de la source (**ClubElo**, **beyondELO**, **Personnalisé**), nombre de scénarios (`20 000` à `1 000 000`, `100 000` par défaut), recalcul à la volée, et éditeur des 36 notes en mode *Personnalisé* (entiers entre `500` et `3 000`, réinitialisation en un clic).
- **Accueil & Repères :** 4 paliers clés (grands favoris, bataille Top 8, cœur du peloton Top 16, fil du rasoir Top 24) + focus clubs français (PSG, Lille, Lens).
- **Explorateur par Club :** fiche complète et 3 graphiques interactifs avec zoom plein écran.
- **Classement & Seuils :** tableau triable/filtrable, vue globale graphique, seuils empilés par points et explorateur **Points par place (1re–36e)**.
- **Comparateur Face-à-Face :** comparaison directe de deux clubs côte à côte.
- **Calendrier & Scores :** résultats joués et matchs à venir, filtrables par club.
- **Méthodologie & À propos :** explication accessible du format et du modèle.

### Exécuter la suite de tests automatisés

```powershell
python -m unittest discover -s tests -v
```

Valide les invariants du calendrier (`data.check()`), la validation des notes Elo, le parsing complet `36/36` de `data/clubelo_ranking.html`, les propriétés mathématiques et la reproductibilité du moteur Monte Carlo, le rendu des 7 types de graphiques, la protection *path traversal* et les routes HTTP de `web_server.py`.

---

## 4. Pipeline d'actualisation des notes Elo (`src/ldc/elo.py`)

### Source ClubElo (défaut)
1. Tente d'abord l'API CSV historique (`api.clubelo.com`).
2. Si l'API est indisponible (date du jour), télécharge automatiquement `https://clubelo.com/Ranking`, valide le contenu extrait, puis **remplace atomiquement `data/clubelo_ranking.html`** avant d'écrire `data/elo.json`.
3. Le parseur extrait en priorité le tableau JavaScript `const eloData = [...]` (classement mondial complet de ~1 750 clubs trié par Elo décroissant, reconnaissant les **36/36 clubs** sans collision d'homonymes), puis les tableaux HTML et JSON/Vega.
4. En cas d'absence de réseau, le fichier `data/clubelo_ranking.html` existant n'est pas écrasé et sert automatiquement de secours.

### Source beyondELO
Interroge l'API `public-api.beyondelo.com` (`--source beyondelo`, avec date historique optionnelle `--date AAAA-MM-JJ`). beyondELO fournit une note étendue intégrant l'importance des matchs, l'écart de buts et un avantage du terrain propre à chaque stade.

---

## 5. Modèle mathématique, hypothèses & limites (`src/ldc/simulation.py`)

### Modèle de match
La probabilité théorique de victoire de l'équipe à domicile inclut un bonus terrain de `HOME_BONUS = 100` points Elo :

$$
W = \frac{1}{1 + 10^{-((Elo_{\text{domicile}} + 100 - Elo_{\text{extérieur}}) / 400)}}
$$

Deux polynômes par morceaux (`lam_home(W)` et `lam_away(W)`) convertissent `W` en nombres moyens de buts attendus $(\lambda_{\text{dom}}, \lambda_{\text{ext}})$, puis les scores sont tirés selon deux lois de Poisson indépendantes.

### Indicateurs exposés par `src/ldc/simulation.py`

| Fonction | Rôle |
|---|---|
| `simulate(...)` | Simule `n_sims` fins de phase de ligue (vectorisé NumPy, Elo fixe par défaut tout au long de chaque simulation ; option `update_elo=True` disponible). |
| `current_table()` | Calcule le classement réel actuel à partir de `PLAYED`. |
| `rank_distribution(sim)` | Matrice `(36, 36)` de probabilité de chaque place finale par équipe. |
| `qualification_probs(sim)` | Probabilités Top 8, barrages (9e–24e), Top 24, élimination (25e–36e) et points moyens. |
| `points_by_position(sim)` | Matrice `(n_sims, 36)` des points du club classé à chaque position finale. |
| `points_thresholds(sim, positions)` | Distribution des points aux places seuils (8e, 16e, 24e, etc.). |
| `qualification_by_points(sim)` | Probabilité conditionnelle de finir Top 8 / barrages / éliminé selon le total final de points. |
| `match_importance(sim)` | Plus grand écart de classement moyen (en places) entre les 3 issues (`1` / `N` / `2`) de chaque match restant, par conditionnement *a posteriori*. |
| `prob_objectives(sim, objectives)` | Probabilité jointe qu'un ensemble d'objectifs soit atteint simultanément. |

### Limites assumées
- **Indépendance des buts :** les buts domicile et extérieur suivent deux lois de Poisson indépendantes (pas de correction de Dixon-Coles sur les petits scores).
- **Elo constant durant la simulation :** conserver l'Elo fixe évite tout biais lié à l'ordre des matchs simultanés d'une même journée, au prix de ne pas modéliser une éventuelle dynamique de forme en cours de fin de phase.
- **Départage :** points, différence de buts, buts marqués, buts à l'extérieur, victoires, victoires à l'extérieur puis tirage aléatoire (les critères UEFA secondaires comme les points des adversaires ou le fair-play ne sont pas modélisés).
- **Calendrier manuel :** après chaque nouvelle journée, actualiser `PLAYED` et `REMAINING` dans `src/ldc/data.py` puis vérifier avec `python -m unittest discover -s tests -v`.
