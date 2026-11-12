[README.md](https://github.com/user-attachments/files/34756474/README.md)
# Simulateur Monte Carlo — Ligue des champions 2026-2027

Ce dépôt contient les quatre modules Python utilisés pour estimer les chances de qualification des 36 clubs de la phase de ligue de la Ligue des champions, puis produire des graphiques de synthèse.

Le projet combine :

- les données de la compétition (résultats et calendrier) ;
- les notes Elo des équipes ;
- un modèle de buts fondé sur deux lois de Poisson ;
- des simulations Monte Carlo de tous les matchs restants ;
- des indicateurs statistiques et des visualisations.

> **Périmètre :** ce README décrit les quatre fichiers fournis. Il n'y a pas encore de script d'orchestration unique (`main.py`) dans ces fichiers. Les exemples ci-dessous montrent comment les appeler ensemble.

## 1. Organisation des fichiers

Les fichiers doivent être placés dans le même dossier et porter exactement ces noms :

```text
projet-ldc/
├── README.md
├── ldc_data.py
├── ldc_elo.py
├── ldc_sim.py
└── ldc_viz.py
```

| Fichier | Rôle |
|---|---|
| `ldc_data.py` | Contient les 36 équipes, les notes Elo de secours, les résultats déjà joués et les matchs restants. Vérifie aussi la cohérence du calendrier. |
| `ldc_elo.py` | Récupère les notes Elo depuis une page ClubElo enregistrée localement (ou tente l'ancienne API si aucun HTML local n'est présent), puis écrit `elo.json`. |
| `ldc_sim.py` | Cœur du moteur Monte Carlo : simule les scores, met à jour éventuellement les Elo, calcule les classements et estime les probabilités. |
| `ldc_viz.py` | Produit les graphiques : vue d'ensemble des 36 équipes, fiche d'une équipe et fiche d'un scénario d'objectifs. |

**Attention au nom du module de simulation :** le fichier reçu s'appelait `ldc_simulation_commentee(1).py`, mais `ldc_viz.py` contient `import ldc_sim as s`. Il faut donc le renommer en `ldc_sim.py` (ou modifier l'import dans `ldc_viz.py`). Le nom `ldc_sim.py` est celui utilisé dans le reste de cette documentation.

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

En l'absence de fichier HTML local, le script tente l'ancienne API CSV ClubElo. Cette API peut renvoyer une erreur 502. Une date historique peut être demandée avec `python ldc_elo.py AAAA-MM-JJ`, mais elle nécessite que l'API historique réponde : une page HTML actuelle ne permet pas de reconstruire un classement passé.

**Interprétation de la date dans `elo.json` :** avec la méthode HTML, la date enregistrée est la date à laquelle le script a été exécuté. Elle ne certifie pas à elle seule la date exacte de mise à jour du classement par ClubElo. Il faut donc télécharger une page fraîche avant chaque actualisation.

### Format de sortie

Le fichier généré garde le format attendu par `ldc_data.py` :

```json
{
  "date": "2026-11-12",
  "elo": {
    "AEK": 1695,
    "Arsenal": 2047
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

`ldc_viz.py` contient trois fonctions de visualisation. Elles reçoivent les résultats de `ldc_sim.py` et enregistrent les images au chemin fourni.

| Fonction | Fichier produit / contenu |
|---|---|
| `overview(sim, table, path)` | Vue globale des 36 équipes, avec les probabilités Top 8 / barrages / élimination. |
| `team_card(team, sim, table, path, n_sims=None)` | Fiche d'une équipe : distribution des 36 places possibles et trois indicateurs de qualification. |
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
2. Télécharger la dernière page ClubElo et l'enregistrer sous `clubelo_ranking.html`.
3. Exécuter `python ldc_elo.py` et vérifier que les 36 équipes sont reconnues.
4. Exécuter `python ldc_data.py` pour contrôler le calendrier.
5. Exécuter `python ldc_sim.py` ou utiliser le bloc d'orchestration ci-dessus pour lancer les simulations et générer les visuels.

## 9. Évolutions possibles

- Automatiser la récupération des notes Elo si un accès officiel et stable aux données devient disponible.
- Mettre à jour les Elo par journée plutôt que match par match pour les rencontres simultanées.
- Implémenter l'ensemble des critères de départage UEFA.
- Ajouter un script `main.py` qui enchaîne la vérification des données, la simulation et la génération des graphiques.
- Ajouter des tests automatiques pour valider les distributions de probabilités, les dimensions des matrices et la cohérence des classements.
