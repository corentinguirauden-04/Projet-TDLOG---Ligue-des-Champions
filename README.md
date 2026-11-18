# Simulateur Monte Carlo — Ligue des champions 2026-2027

Ce dépôt contient les modules Python utilisés pour estimer les chances de qualification des 36 clubs de la phase de ligue de la Ligue des champions, puis produire des graphiques de synthèse.

Le projet combine :

- les données de la compétition (résultats et calendrier) ;
- les notes Elo des équipes (ClubElo, beyondELO ou Elo personnalisé manuel) ;
- un modèle de buts fondé sur deux lois de Poisson ;
- des simulations Monte Carlo de tous les matchs restants ;
- des indicateurs statistiques et des visualisations.

> **Périmètre :** ce README décrit l'ensemble des modules du projet ainsi que les scripts `main.py` et `generate_outputs.py` qui orchestrent la pipeline complète.

## 1. Organisation des fichiers

Les fichiers doivent être placés dans le même dossier et porter exactement ces noms :

```text
projet-ldc/
├── README.md
├── main.py
├── generate_outputs.py
├── ldc_data.py
├── ldc_elo.py
├── ldc_sim.py
├── ldc_viz.py
└── outputs/
    ├── clubelo/
    ├── beyondelo/
    └── manual/
```

| Fichier | Rôle |
|---|---|
| `main.py` | Point d'entrée unique : choisit la source Elo (`clubelo`, `beyondelo` ou `manual`), vérifie les données et lance la génération complète dans `outputs/<source>/`. |
| `generate_outputs.py` | Lance les simulations Monte Carlo, crée les fiches individuelles, la vue globale et le CSV des probabilités dans `outputs/<source>/`. |
| `ldc_data.py` | Contient les 36 équipes, les notes Elo manuelles de secours (`DEFAULT_ELO`), les résultats déjà joués et les matchs restants. Vérifie aussi la cohérence du calendrier. |
| `ldc_elo.py` | Récupère les notes Elo depuis ClubElo (HTML local ou API CSV) ou depuis l'API beyondELO (`--source beyondelo`), puis écrit `elo.json`. |
| `ldc_sim.py` | Cœur du moteur Monte Carlo : simule les scores, met à jour éventuellement les Elo, calcule les classements et estime les probabilités. |
| `ldc_viz.py` | Produit les graphiques : vue d'ensemble des 36 équipes, fiche d'une équipe et fiche d'un scénario d'objectifs. |

## 2. Installation

Le module de récupération Elo (`ldc_elo.py`) n'utilise que la bibliothèque standard de Python. Le moteur et les graphiques nécessitent NumPy et Matplotlib.

Dans l'environnement Python utilisé pour le projet :

```powershell
python -m pip install numpy matplotlib
```

Vérifier ensuite que les quatre fichiers sont dans le même dossier et que le terminal est positionné dans ce dossier.

## 3. Préparer les données de la compétition — `ldc_data.py`

Ce module est la source des données de la phase de ligue. Il définit :

- `ELO` : dictionnaire `{nom_equipe: note_elo}` ;
- `DEFAULT_ELO` : copie des notes Elo manuelles inscrites par défaut dans le fichier (utilisée par le mode `manual`) ;
- `PLAYED` : liste des matchs déjà joués, sous la forme `(domicile, extérieur, buts_domicile, buts_extérieur)` ;
- `REMAINING` : liste des matchs restant à jouer, sous la forme `(domicile, extérieur)` ;
- `TEAMS` : liste triée des noms des 36 équipes ;
- `ELO_DATE` : date présente dans `elo.json`, ou `None` si aucun fichier Elo n'a été chargé ;
- `check()` : contrôles de cohérence du calendrier.

Au chargement, `ldc_data.py` regarde si un fichier `elo.json` existe dans le même dossier. S'il existe et contient exactement les 36 noms attendus, il remplace le dictionnaire `ELO` intégré au fichier. Sinon, les valeurs de secours inscrites dans `ldc_data.py` restent utilisées.

Le contrôle `check()` vérifie notamment qu'il y a 72 matchs joués et 72 matchs restants, que les 36 équipes disputent huit matchs au total (quatre à domicile et quatre à l'extérieur) et qu'aucune affiche n'est dupliquée.

Lancer le contrôle :

```powershell
python ldc_data.py
```

Le code fourni indique que les résultats et le calendrier proviennent d'UEFA.com et que la liste a été mise à jour le **4 novembre 2026**. Il faut actualiser `PLAYED` et `REMAINING` après les journées suivantes avant de lancer une nouvelle projection. Le calendrier et les résultats sont saisis manuellement dans ce fichier.

> **Note sur les notes initiales :** la valeur de Stuttgart (1819) est explicitement signalée comme provisoire dans le code fourni. Elle est remplacée si `elo.json` est correctement généré.

## 4. Actualiser les notes Elo — `ldc_elo.py`

### Méthode actuelle : fichier HTML téléchargé

L'accès automatisé à ClubElo peut être refusé par son service anti-bot. La méthode de secours retenue pour le projet est donc de télécharger la page dans un navigateur, puis de laisser Python en extraire les notes.

1. Ouvrir [ClubElo — Ranking](https://clubelo.com/Ranking) dans un navigateur.
2. Attendre que la page et son classement aient fini de charger.
3. Enregistrer la page avec `Ctrl + S`, en choisissant **Page Web, HTML uniquement**.
4. Placer le fichier dans le même dossier que `ldc_elo.py` et le nommer `clubelo_ranking.html`.
5. Exécuter :

```powershell
python ldc_elo.py
```

Le script lit en priorité `clubelo_ranking.html`. Il sait chercher les paires Club/Elo dans les tableaux HTML et dans les objets JSON/Vega intégrés aux balises `<script>`. Il normalise les noms (accents, casse et ponctuation) et utilise les variantes définies dans `CLUBELO_NAMES`.

Si la page générale ne contient pas tous les clubs, télécharger également les pages nationales nécessaires et les enregistrer dans le même dossier avec des noms commençant par `clubelo_`, par exemple :

```text
clubelo_ranking.html
clubelo_ENG.html
clubelo_FRA.html
clubelo_GER.html
clubelo_ITA.html
```

Le script agrège ces fichiers. Il n'écrit `elo.json` que lorsque les 36 équipes ont été reconnues. Si des clubs manquent, il affiche leur liste et conserve l'ancien `elo.json` sans l'écraser.

On peut aussi indiquer explicitement le ou les fichiers à lire :

```powershell
python ldc_elo.py clubelo_ranking.html
python ldc_elo.py clubelo_ENG.html clubelo_FRA.html clubelo_GER.html
```

En l'absence de fichier HTML local, le script tente l'ancienne API CSV ClubElo (ou l'API beyondELO si `--source beyondelo` est indiqué). L'API ClubElo peut renvoyer une erreur 502. Une date historique peut être demandée avec `python ldc_elo.py AAAA-MM-JJ` ou `python ldc_elo.py --source beyondelo AAAA-MM-JJ`, mais elle nécessite que l'API correspondante réponde : une page HTML actuelle ne permet pas de reconstruire un classement passé.

### Source alternative : API beyondELO

Il est aussi possible de récupérer directement les notes Elo depuis l'API beyondELO (`_fetch_api_beyondelo`), au même format de sortie :

```powershell
python ldc_elo.py --source beyondelo
python ldc_elo.py --source beyondelo 2026-10-01
```

**Interprétation de la date dans `elo.json` :** avec la méthode HTML, la date enregistrée est la date à laquelle le script a été exécuté. Elle ne certifie pas à elle seule la date exacte de mise à jour du classement par ClubElo. Il faut donc télécharger une page fraîche avant chaque actualisation.

### Format de sortie

Le fichier généré garde le format attendu par `ldc_data.py`, avec l'indication de la source :

```json
{
  "date": "2026-11-16",
  "source": "beyondelo",
  "elo": {
    "AEK": 1685,
    "Arsenal": 2161
  }
}
```

L'exemple est tronqué : le fichier réel contient les 36 équipes.

## 5. Simuler la fin de la phase de ligue — `ldc_sim.py`

Le module `ldc_sim.py` importe `ELO`, `PLAYED`, `REMAINING` et `TEAMS` depuis `ldc_data.py`.

### Modèle de match

La probabilité théorique de victoire de l'équipe à domicile est calculée à partir de l'écart Elo, avec un bonus de 100 points pour l'équipe qui reçoit :

\[
W = \frac{1}{1 + 10^{-((Elo_{domicile}+100-Elo_{extérieur})/400)}}
\]

Deux polynômes ajustés dans le projet convertissent ensuite `W` en buts moyens attendus :

- `lam_home(W)` : lambda de l'équipe à domicile ;
- `lam_away(W)` : lambda de l'équipe à l'extérieur.

Les scores sont tirés aléatoirement :

```python
hg = rng.poisson(lam_home(W))
ag = rng.poisson(lam_away(W))
```

Chaque score est donc une réalisation possible autour d'un nombre moyen de buts, pas une prédiction certaine.

### Déroulement d'une simulation

La fonction principale est `simulate()` (100 000 scénarios par défaut). Pour chaque scénario, elle :

1. reprend les résultats réels de `PLAYED` ;
2. génère les scores des matchs de `REMAINING` ;
3. met à jour les notes Elo après chaque match si `update_elo=True` ;
4. cumule les points, buts et autres statistiques ;
5. calcule le classement final des 36 clubs.

La vectorisation NumPy permet de traiter de nombreux scénarios dans des tableaux plutôt que de lancer une boucle Python indépendante pour chaque scénario.

### Fonctions principales

| Fonction | Rôle |
|---|---|
| `win_exp(elo1, elo2)` | Transforme un écart Elo en probabilité théorique de victoire. |
| `lam_home(W)` / `lam_away(W)` | Convertissent la probabilité attendue en buts moyens pour chaque équipe. |
| `elo_delta(W_home, hg, ag, k)` | Calcule la variation Elo après un résultat simulé. |
| `lambdas_home(home, away, elo)` | Calcule les deux lambdas d'un match donné. |
| `_table_from_matches(matches)` | Cumule les statistiques des équipes dans tous les scénarios. |
| `_rank(stats, rng)` | Classe les 36 équipes dans chaque scénario. |
| `current_table()` | Construit le classement actuel à partir des seuls matchs réellement joués. |
| `simulate(...)` | Génère les scénarios de fin de phase de ligue. |
| `rank_distribution(sim)` | Calcule la distribution des places finales de chaque équipe. |
| `qualification_probs(sim)` | Calcule les probabilités Top 8, barrages, Top 24, élimination et les points moyens. |
| `prob_objectives(sim, objectives)` | Calcule la probabilité que plusieurs objectifs soient atteints simultanément. |
| `points_thresholds(sim, positions)` | Calcule la distribution des points du club qui finit à certaines places (8e, 9e, 16e, etc.). |
| `match_importance(sim)` | Mesure pour chaque équipe l'impact de chaque match restant sur ses chances de Top 8 ou Top 24 selon les 3 issues possibles (`1` / `N` / `2`). |

Exécuter directement le module lance un exemple de 20 000 simulations et affiche les dix équipes avec la plus forte probabilité de finir dans le Top 8 :

```powershell
python ldc_sim.py
```

Pour contrôler le nombre de simulations ou la graine aléatoire, importer le module et appeler `simulate` :

```python
import ldc_sim as sim

resultats = sim.simulate(n_sims=100_000, seed=42)
probabilites = sim.qualification_probs(resultats)

for club, valeurs in sorted(
    probabilites.items(),
    key=lambda item: -item[1]["top8"]
):
    print(club, valeurs)
```

## 6. Produire les graphiques — `ldc_viz.py`

`ldc_viz.py` contient les fonctions de visualisation. Elles reçoivent les résultats de `ldc_sim.py` et enregistrent les images au chemin fourni.

| Fonction | Fichier produit / contenu |
|---|---|
| `overview(sim, table, path)` | Vue globale des 36 équipes, avec les probabilités Top 8 / barrages / élimination. |
| `points_thresholds_card(sim, path, n_sims=None)` | Vue globale des seuils : distribution du nombre de points nécessaires pour finir Top 8, Top 16 et Top 24. |
| `team_card(team, sim, table, path, n_sims=None)` | Fiche d'une équipe : distribution des 36 places possibles et trois indicateurs de qualification. |
| `team_points_card(team, sim, table, path, n_sims=None)` | Fiche d'une équipe : distribution des points finaux, moyenne, plage probable (10e–90e percentile) et points actuels/max. |
| `team_important_matches_card(team, sim, table, path, n_sims=None)` | Fiche d'une équipe : Top 10 des matchs restants les plus décisifs (les siens et ceux des concurrents), avec l'écart de probabilité (en %) entre le pire et le meilleur résultat (`1` / `N` / `2`) pour le Top 8 ou le Top 24. |
| `objectives_card(sim, objectives, path)` | Fiche de scénario : probabilité de chaque objectif et probabilité jointe que tous soient atteints. |

Exemple d'utilisation pour générer trois images :

```python
import ldc_sim as sim
import ldc_viz as viz

# 1. Construire le classement réel et lancer les simulations.
table = sim.current_table()
resultats = sim.simulate(n_sims=100_000, seed=42)

# 2. Générer la vue globale.
viz.overview(resultats, table, "classement_global.png")

# 3. Générer une fiche pour le PSG.
viz.team_card("PSG", resultats, table, "fiche_psg.png")

# 4. Étudier un scénario combiné.
objectifs = {"PSG": 8, "Lens": 24, "Lille": 24}
viz.objectives_card(resultats, objectifs, "scenario.png")
```

Les textes de `ldc_viz.py` sont actuellement spécifiques à la saison 2026-2027 et à une situation « après la J4, avant la J5 ». Il faudra les actualiser dans le code lorsque le calendrier ou la journée de référence changera.

## 7. Hypothèses et limites du modèle

Les probabilités produites sont des estimations conditionnelles aux données et hypothèses du programme. Elles ne sont pas des probabilités officielles UEFA.

- **Modèle de buts :** les buts domicile et extérieur sont tirés séparément selon deux lois de Poisson. Les polynômes de conversion Elo → lambdas sont des ajustements propres au projet.
- **Elo :** le bonus domicile est fixé à 100 points. Le facteur `K_ELO` vaut 20 par défaut. Les notes sont mises à jour après chaque match simulé si `update_elo=True`.
- **Ordre des matchs :** quand les Elo sont mis à jour, l'ordre de `REMAINING` a un effet sur les matchs simulés ultérieurs. Le fichier de données doit donc conserver les rencontres dans l'ordre chronologique attendu. Pour des matchs réellement simultanés, une mise à jour groupée par journée serait une amélioration possible.
- **Départage :** le code utilise points, différence de buts, buts marqués, buts marqués à l'extérieur, victoires et victoires à l'extérieur, puis un tirage pseudo-aléatoire. Il ne modélise pas tous les critères UEFA.
- **Résultats historiques :** ils sont considérés comme fixes et ne provoquent pas de mise à jour Elo dans `simulate`. Les Elo de départ sont supposés déjà tenir compte des matchs réels.
- **Aléa Monte Carlo :** `seed=42` permet de reproduire une exécution. Augmenter `n_sims` réduit généralement le bruit statistique, au prix d'un temps de calcul plus élevé.
- **Calendrier :** le contrôle fourni vérifie la structure des 144 matchs, mais il ne vérifie pas automatiquement que les scores ou les affiches correspondent toujours au calendrier officiel le plus récent.

## 8. Ordre de travail recommandé

Avant une nouvelle projection :

1. Mettre à jour les résultats joués et les matchs restants dans `ldc_data.py`.
2. Choisir la source Elo et exécuter la pipeline complète via `main.py` :
   - `python main.py --source beyondelo` (API beyondELO) ;
   - `python main.py --source clubelo` (API ClubElo, ou `python ldc_elo.py clubelo_ranking.html` puis `python main.py --source clubelo --no-refresh` avec un HTML local) ;
   - `python main.py --source manual` (notes `DEFAULT_ELO` de `ldc_data.py`, ou `--elo-file mon_elo.json` pour un Elo personnalisé).

## 9. Évolutions possibles

- Mettre à jour les Elo par journée plutôt que match par match pour les rencontres simultanées.
- Implémenter l'ensemble des critères de départage UEFA.
- Ajouter des tests automatiques pour valider les distributions de probabilités, les dimensions des matrices et la cohérence des classements.

## Générer les visualisations pour toutes les équipes

Depuis le dossier contenant les fichiers Python, activez votre environnement virtuel puis exécutez `main.py` (ou directement `generate_outputs.py`) :

```powershell
python main.py --source clubelo
python main.py --source beyondelo
python main.py --source manual
python main.py --source manual --elo-file mon_elo.json
```

Par défaut, le script réalise **20 000 simulations Monte Carlo** (graine aléatoire fixe : 42) et range tous les résultats dans `outputs/<source>/` (`outputs/clubelo/`, `outputs/beyondelo/` ou `outputs/manual/`) :

- `outputs/<source>/equipes/<equipe>.png` : distribution des places finales (1re à 36e) et probabilités Top 8 / Top 24 / élimination pour chaque équipe ;
- `outputs/<source>/equipes_points/<equipe>.png` : distribution du nombre de points finaux pour chaque équipe ;
- `outputs/<source>/equipes_matchs/<equipe>.png` : Top 10 des matchs restants les plus importants pour chaque équipe (avec l'écart en % entre le pire et le meilleur scénario) ;
- `outputs/<source>/classement_global.png` : vue générale des probabilités de qualification des 36 équipes ;
- `outputs/<source>/seuils_points_top_8_16_24.png` : distribution globale du nombre de points nécessaires pour finir dans le Top 8, le Top 16 et le Top 24 ;
- `outputs/<source>/probabilites_equipes.csv` : tableau des probabilités Top 8, Top 24, barrages, élimination, points moyens et probabilité de chacune des 36 places.

Pour augmenter le nombre de simulations, indiquez-le avec `--n-sims` (ou en argument de `generate_outputs.py`) :

```powershell
python main.py --source beyondelo --n-sims 100000
python generate_outputs.py --source beyondelo 100000
```

Le nombre d'équipes est lu automatiquement dans `ldc_data.py`. Dans la version actuelle, le projet contient **36 équipes** (et non 32). Le nombre de graphiques s'adapte donc à la liste réellement chargée.

Les probabilités Top 8 et Top 24 sont estimées comme la fréquence observée sur les simulations. La probabilité de barrages correspond aux places 9 à 24 ; la probabilité d'élimination correspond aux places 25 à 36. Les valeurs exactes pour chacune des places figurent dans le CSV.
