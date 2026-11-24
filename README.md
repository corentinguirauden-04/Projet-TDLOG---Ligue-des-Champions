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
│   │   ├── equipes/<club>/{classement,points,seuils_points,matchs_cles,matchs_cles_top8,matchs_cles_top24}.png
│   │   ├── classements/{1..36}.png
│   │   ├── classement_global.png
│   │   ├── seuils_points_top_8_16_24.png
│   │   ├── probabilites_equipes.csv
│   │   └── matchs_restants.json
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

> **Variables d'environnement :** définir `BEYONDELO_API_KEY` pour utiliser beyondELO et `FOOTBALL_DATA_API_TOKEN` pour synchroniser les résultats. Les clés ne sont jamais stockées dans le code.

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

Par défaut, **250 000 simulations Monte Carlo** sont exécutées (`seed=42`) et produisent dans `outputs/<source>/` :
- `equipes/<club>/classement.png` : distribution des 36 places finales (36e à gauche → 1re à droite), encadrés alignés au-dessus de leurs zones (*Élimination* / *Barrages* / *Top 8*), rang moyen et points moyens (avec écarts-types) ;
- `equipes/<club>/points.png` : distribution des points finaux, moyenne (vert-cyan), écart-type, plage probable 80 % (jaune) et points actuels/max ;
- `equipes/<club>/seuils_points.png` : probabilités d'issue finale (Top 8 / barrages / éliminé) selon le total final de points atteignable par ce club (en tenant compte de sa différence de buts) ;
- `equipes/<club>/matchs_cles.png`, `matchs_cles_top8.png`, `matchs_cles_top24.png` : Top 10 des matchs restants les plus décisifs selon 3 indicateurs au choix — écart de classement moyen (en places), écart de probabilité de **Top 8** (%) et écart de probabilité de **Top 24** (%) ;
- `classements/1.png` à `36.png` : distribution du nombre de points du club terminant exactement à la place `x` (moyenne, écart-type, plage 80 %, score le plus fréquent) ;
- `classement_global.png` : vue globale des 36 clubs en barres empilées Top 8 / barrages / éliminé ;
- `seuils_points_top_8_16_24.png` : barres empilées à 100 % indiquant la probabilité d'issue finale selon le nombre de points (avec moyenne, écart-type et mode des seuils Top 8 / 16 / 24) ;
- `probabilites_equipes.csv` : tableau CSV complet des probabilités (y compris chacune des 36 places) ;
- `matchs_restants.json` : probabilités (1 / N / 2) et importance au classement final (en places) de chaque affiche restante pour les deux clubs.

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
- **Barre de contrôle :** choix de la source (**ClubElo**, **beyondELO**, **Personnalisé**), nombre de scénarios (`20 000` à `1 000 000`, `250 000` par défaut), recalcul à la volée, et éditeur des 36 notes en mode *Personnalisé* (entiers entre `500` et `3 000`, réinitialisation en un clic).
- **Accueil & Repères :** 4 paliers clés (grands favoris, bataille Top 8, cœur du peloton Top 16, fil du rasoir Top 24) + focus clubs français (PSG, Lille, Lens).
- **Explorateur par Club :** fiche complète, 6 graphiques interactifs (classement, points, seuils de points propres au club, matchs décisifs par classement / Top 8 / Top 24) avec zoom plein écran et onglet *Calendrier à venir*.
- **Classement & Seuils :** tableau triable/filtrable, vue globale graphique, seuils empilés par points et explorateur **Points par place (1re–36e)**.
- **Comparateur Face-à-Face :** comparaison directe de deux clubs côte à côte.
- **Calendrier & Scores :** sélecteur dynamique de journée (`J1`–`J8` + `Toutes`), filtre par club, tri par enjeux ou par équilibre, résultats officiels et cartes détaillées avec probabilités `1 / N / 2` et importance du match (en places) pour chacun des deux clubs.
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

## 5. Synchronisation automatique des résultats (football-data.org)

Le serveur web peut synchroniser les résultats de la phase de ligue via l'API
football-data.org. La clé est utilisée uniquement côté Python : elle n'est jamais
envoyée au navigateur ni stockée dans le dépôt.

### Configuration

1. Créer un compte sur https://www.football-data.org/ et récupérer un jeton API.
2. Dans PowerShell, définir la variable avant de lancer le serveur :

```powershell
$env:FOOTBALL_DATA_API_TOKEN = "VOTRE_JETON_FOOTBALL_DATA"
python web_app.py
```

Pour la conserver entre les sessions, utiliser `setx FOOTBALL_DATA_API_TOKEN "VOTRE_JETON"`
puis ouvrir un nouveau terminal. Ne jamais ajouter le jeton à un fichier suivi par Git.

Pour utiliser aussi beyondELO, définir séparément `BEYONDELO_API_KEY` dans l'environnement.
Aucune clé API ne doit être inscrite en dur dans `src/ldc/config.py`. Si une ancienne clé a déjà été publiée dans Git, il faut la révoquer et en générer une nouvelle : supprimer le texte du dernier commit ne l'efface pas de l'historique Git.

### Fonctionnement

- Le serveur interroge football-data.org au plus une fois toutes les **5 minutes**, quel
  que soit le nombre de navigateurs connectés. Le navigateur recharge l'état à la même
  fréquence et ne contacte jamais directement le fournisseur.
- Il n'existe pas de tâche de polling en arrière-plan : les appels fournisseur sont
  déclenchés par les requêtes web `/api/state` ou `/api/simulate`. En pratique, le premier
  chargement de la page déclenche un contrôle, puis le navigateur en demande un nouveau
  toutes les 5 minutes tant que l'onglet est visible. Si aucun navigateur n'utilise le
  site, le serveur ne consomme pas de requêtes football-data.org. Un redémarrage du
  serveur suivi d'un chargement de la page déclenche un nouveau contrôle immédiat.
- Un match entre dans `PLAYED` seulement lorsqu'il possède le statut final
  `FINISHED` ou `AWARDED` et un score à temps réglementaire. Les matchs
  `IN_PLAY` / `PAUSED` restent dans `REMAINING` et peuvent afficher leur score en cours.
- Après un changement des résultats terminés, le serveur recalcule automatiquement
  les projections de la source Elo active avec **250 000 simulations** (valeur par défaut),
  en conservant les notes Elo fixes dans chaque simulation.
- Les résultats synchronisés sont mis en cache localement dans
  `data/live_matches.json` (fichier ignoré par Git). Si l'API est temporairement
  indisponible, le dernier état valide est conservé. Sans jeton, le projet utilise
  les résultats statiques de `src/ldc/data.py`.
- L'indicateur sous la barre de commande signale la connexion, l'heure du dernier
  contrôle et les éventuelles erreurs.

### Limite du forfait football-data.org

Le forfait gratuit annonce des scores et calendriers différés (10 requêtes/minute).
Un contrôle toutes les 5 minutes ne transforme donc pas ces données en véritables
livescores : il ne fait que détecter les mises à jour dès qu'elles sont publiées par
le fournisseur. Pour des scores réellement en direct pendant les matchs, football-data.org
propose le forfait « Free w Livescores » (12 €/mois affichés sur sa page tarifaire),
avec 20 requêtes/minute. Vérifier les conditions et le tarif au moment de l'inscription.

Références fournisseur :
- Tarifs et disponibilité des livescores : https://www.football-data.org/pricing
- Documentation API et statuts des matchs : https://www.football-data.org/documentation/api

---

## 6. Modèle mathématique, hypothèses & limites (`src/ldc/simulation.py`)

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
- **Mode sans fournisseur :** si aucune clé football-data.org n'est configurée, le projet conserve les listes statiques `PLAYED` et `REMAINING` de `src/ldc/data.py`. Avec le jeton, les scores terminés sont synchronisés automatiquement.
