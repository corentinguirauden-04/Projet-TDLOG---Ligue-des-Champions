"""Simulation Monte Carlo de la fin de la phase de ligue de la Ligue des Champions.

Rôle du fichier
---------------
Ce fichier est le moteur de simulation du projet : il simule plusieurs milliers
(ou centaines de milliers) de fins de phase de ligue possibles, à partir :
  - des équipes et des matchs déjà joués / restant à jouer, fournis par ldc_data.py ;
  - d'une note Elo de départ pour chaque équipe ;
  - d'un modèle de buts basé sur deux lois de Poisson.

Pour chaque simulation, le programme :
  1. génère un score pour chaque match restant ;
  2. met éventuellement à jour les notes Elo après chaque match simulé ;
  3. calcule les statistiques et le classement final des 36 équipes.

Les fonctions situées plus bas permettent ensuite d'exploiter les simulations :
probabilités de finir dans le top 8, entre les places 9 et 24, etc.

Important : cette version conserve les calculs du code d'origine. Les commentaires
expliquent le fonctionnement sans modifier les hypothèses mathématiques.
"""

import numpy as np

# Données du projet. Ce fichier ne construit pas lui-même le calendrier ni la
# liste des résultats : il les importe depuis ldc_data.py.
# ELO       : dictionnaire {nom_equipe: note_elo}
# PLAYED    : matchs déjà joués, sous la forme (domicile, extérieur, buts_dom., buts_ext.)
# REMAINING : matchs restant à jouer, sous la forme (domicile, extérieur)
# TEAMS     : liste des 36 équipes, dans l'ordre utilisé pour les tableaux NumPy
from ldc_data import ELO, PLAYED, REMAINING, TEAMS

# Nombre de points Elo ajoutés à l'équipe qui reçoit pour calculer sa probabilité
# attendue de victoire. Ce bonus intervient dans le calcul du match, pas dans le
# dictionnaire ELO importé.
HOME_BONUS = 100


# ----------------------------------------------------------------------------------------------
# 1. MODÈLE DE MATCH : Elo -> probabilité attendue -> buts attendus
# ----------------------------------------------------------------------------------------------

def win_exp(elo1: float, elo2: float) -> float:
    """Calcule la probabilité théorique de victoire de l'équipe 1.

    La formule Elo transforme l'écart de notes en probabilité :
      - si elo1 = elo2, la probabilité vaut 50 % ;
      - si elo1 est supérieur à elo2, elle dépasse 50 % ;
      - si elo1 est inférieur à elo2, elle est inférieure à 50 %.

    Cette probabilité est ensuite utilisée pour déterminer les buts attendus.
    """
    return 1 / (1 + 10 ** (-(elo1 - elo2) / 400))


def lam_home(W):
    """Renvoie le nombre moyen de buts attendus par l'équipe à domicile.

    W représente la probabilité attendue de victoire de l'équipe qui reçoit.
    Les deux polynômes sont des approximations ajustées dans le projet :
      - `low` est utilisé lorsque W <= 0.9 ;
      - `high` est utilisé lorsque W > 0.9.

    Le résultat est un lambda de Poisson : ce n'est pas un score garanti, mais
    une moyenne autour de laquelle les buts simulés vont varier.

    np.asarray permet à la fonction de recevoir soit un seul nombre, soit un
    tableau de probabilités (une probabilité par simulation Monte Carlo).
    """
    W = np.asarray(W, dtype=float)
    d = W - 0.9
    low = -5.42301 * W**4 + 15.49728 * W**3 - 12.6499 * W**2 + 5.36198 * W + 0.22863
    high = 231098.16153 * d**4 - 30953.10199 * d**3 + 1347.51495 * d**2 - 1.63074 * d + 2.54747
    return np.where(W <= 0.9, low, high)


def lam_away(W):  # W = probabilité attendue de victoire de l'équipe à domicile
    """Renvoie le nombre moyen de buts attendus par l'équipe à l'extérieur.

    Attention : l'argument W reste la probabilité de victoire attendue de
    l'équipe à domicile. Les polynômes ont été ajustés en conséquence :
      - `low` est utilisé lorsque W < 0.1 ;
      - `high` est utilisé lorsque W >= 0.1.

    Le résultat est le lambda de la loi de Poisson de l'équipe visiteuse.
    """
    W = np.asarray(W, dtype=float)
    d = W - 0.1
    low = 90173.57949 * d**4 + 10064.38612 * d**3 + 218.6628 * d**2 - 11.06198 * d + 2.28291
    high = -1.25010 * W**4 - 1.99984 * W**3 + 6.54946 * W**2 - 5.83979 * W + 2.80352
    return np.where(W < 0.1, low, high)


# ----------------------------------------------------------------------------------------------
# 2. MISE À JOUR DES NOTES ELO APRÈS UN MATCH SIMULÉ
# ----------------------------------------------------------------------------------------------

# Facteur K : contrôle l'ampleur de la variation Elo après un match.
# Un K plus élevé rend les notes plus réactives aux résultats.
K_ELO = 20


def elo_delta(W_home, hg, ag, k=K_ELO):
    """Calcule le changement Elo de l'équipe à domicile après un match.

    Paramètres
    ----------
    W_home : probabilité attendue de victoire du domicile (bonus domicile inclus)
    hg     : nombre de buts de l'équipe à domicile
    ag     : nombre de buts de l'équipe à l'extérieur
    k      : facteur de réactivité Elo (20 par défaut)

    Le résultat réel `r` vaut :
      - 1.0 en cas de victoire du domicile ;
      - 0.5 en cas de match nul ;
      - 0.0 en cas de défaite du domicile.

    La variation est k * g * (résultat réel - résultat attendu).
    `g` augmente lorsque l'écart de buts est important :
      - 0 ou 1 but d'écart : multiplicateur 1 ;
      - 2 buts d'écart : multiplicateur 1.5 ;
      - 3 buts ou plus : multiplicateur (11 + écart) / 8.

    La fonction renvoie un delta positif ou négatif pour le domicile. Dans
    `simulate`, ce même delta est soustrait à l'équipe visiteuse : le transfert
    de points Elo est donc à somme nulle entre les deux équipes.
    """
    n = np.abs(hg - ag)  # écart de buts, sans tenir compte du vainqueur

    # Multiplicateur qui tient compte de l'ampleur du score.
    g = np.where(n <= 1, 1.0, np.where(n == 2, 1.5, (11 + n) / 8))

    # Résultat observé du point de vue de l'équipe à domicile.
    r = np.where(hg > ag, 1.0, np.where(hg == ag, 0.5, 0.0))

    return k * g * (r - W_home)


def lambdas_home(home: str, away: str, elo=ELO):
    """Calcule les deux lambdas d'un match à partir des notes Elo.

    `home` et `away` sont les noms des équipes tels qu'ils apparaissent dans
    TEAMS et dans le dictionnaire ELO.

    Le bonus domicile est ajouté à la note de l'équipe qui reçoit uniquement
    pour calculer W, la probabilité attendue de victoire. Les deux polynômes
    convertissent ensuite W en buts attendus domicile / extérieur.
    """
    W = win_exp(elo[home] + HOME_BONUS, elo[away])
    return lam_home(W), lam_away(W)


# ----------------------------------------------------------------------------------------------
# 3. INDEXATION DES ÉQUIPES ET CONSTRUCTION DES STATISTIQUES
# ----------------------------------------------------------------------------------------------

# Pour les calculs NumPy, chaque équipe est représentée par un entier :
# IDX["PSG"] peut par exemple renvoyer 0, IDX["Arsenal"] 1, etc.
# L'ordre est déterminé par la liste TEAMS importée depuis ldc_data.py.
IDX = {t: i for i, t in enumerate(TEAMS)}
N_TEAMS = len(TEAMS)  # normalement 36 pour la phase de ligue de la LDC


def _table_from_matches(matches):
    """Calcule les statistiques de toutes les équipes pour toutes les simulations.

    `matches` est une liste de tuples :
        (home_idx, away_idx, hg, ag)

    home_idx / away_idx : indices des équipes dans TEAMS.
    hg / ag             : tableaux de scores, avec une valeur par simulation.

    Les statistiques sont stockées dans des matrices de forme (N, N_TEAMS) :
      - pts  : points (3 victoire, 1 nul, 0 défaite) ;
      - gf   : buts marqués ;
      - ga   : buts encaissés ;
      - agf  : buts marqués à l'extérieur ;
      - wins : nombre de victoires ;
      - awins: nombre de victoires à l'extérieur.

    N est le nombre de simulations Monte Carlo. La colonne correspond à une
    équipe et la ligne à une simulation.
    """
    N = matches[0][2].shape[0]  # nombre de scénarios simulés

    # Crée une matrice de zéros (N simulations x N_TEAMS équipes).
    z = lambda: np.zeros((N, N_TEAMS), dtype=np.int32)
    pts, gf, ga, agf, wins, awins = z(), z(), z(), z(), z(), z()

    for h, a, hg, ag in matches:
        # Points attribués au domicile et à l'extérieur, scénario par scénario.
        pts[:, h] += np.where(hg > ag, 3, np.where(hg == ag, 1, 0))
        pts[:, a] += np.where(ag > hg, 3, np.where(hg == ag, 1, 0))

        # Buts marqués et encaissés par chaque équipe.
        gf[:, h] += hg
        ga[:, h] += ag
        gf[:, a] += ag
        ga[:, a] += hg

        # Buts marqués à l'extérieur : seuls les buts de l'équipe visiteuse comptent.
        agf[:, a] += ag

        # Nombre de victoires, puis nombre de victoires à l'extérieur.
        wins[:, h] += hg > ag
        wins[:, a] += ag > hg
        awins[:, a] += ag > hg

    return dict(pts=pts, gf=gf, ga=ga, agf=agf, wins=wins, awins=awins)


def _rank(stats, rng):
    """Classe les 36 équipes dans chaque simulation.

    Critères approximés, dans l'ordre :
      1. points ;
      2. différence de buts ;
      3. buts marqués ;
      4. buts marqués à l'extérieur ;
      5. nombre de victoires ;
      6. nombre de victoires à l'extérieur ;
      7. tirage pseudo-aléatoire pour départager les égalités restantes.

    Les critères UEFA complets ne sont pas tous représentés dans ce code
    (par exemple les résultats des adversaires et le fair-play).

    Retour
    ------
    Matrice `ranks` de forme (N, 36). ranks[s, t] est la place de l'équipe t
    dans la simulation s, avec des places allant de 1 à 36.
    """
    N = stats["pts"].shape[0]
    gd = stats["gf"] - stats["ga"]  # goal difference = différence de buts

    # On construit une clé numérique qui encode les critères de classement.
    # Les multiplications successives donnent davantage de poids aux critères
    # prioritaires (points avant différence de buts, etc.).
    key = stats["pts"].astype(np.int64)
    key = key * 256 + (gd + 128)
    key = key * 256 + stats["gf"]
    key = key * 256 + stats["agf"]
    key = key * 16 + stats["wins"]
    key = key * 16 + stats["awins"]

    # Dernier départage aléatoire, pour éviter un ordre systématique en cas d'égalité.
    key = key * 1024 + rng.integers(0, 1024, size=(N, N_TEAMS))

    # Trie les clés de la plus grande à la plus petite.
    # order[s, k] contient l'indice de l'équipe classée k+1 dans la simulation s.
    order = np.argsort(-key, axis=1)

    # Transforme l'ordre de tri en rang par équipe.
    ranks = np.empty_like(order)
    rows = np.arange(N)[:, None]
    ranks[rows, order] = np.arange(1, N_TEAMS + 1)[None, :]
    return ranks


def current_table():
    """Construit le classement à l'instant présent à partir des matchs joués.

    Cette fonction n'effectue aucune simulation des matchs restants. Elle
    calcule uniquement les points, buts et rangs correspondant à PLAYED.
    """
    # Pour chaque résultat réel, on crée un tableau de score de taille 1
    # (une seule situation, puisqu'il n'y a pas de simulation ici).
    ms = [(IDX[h], IDX[a], np.array([hg]), np.array([ag])) for h, a, hg, ag in PLAYED]

    st = _table_from_matches(ms)
    ranks = _rank(st, np.random.default_rng(0))[0]

    rows = []
    for t in TEAMS:
        i = IDX[t]
        rows.append(dict(
            team=t,
            rank=int(ranks[i]),
            pts=int(st["pts"][0, i]),
            gf=int(st["gf"][0, i]),
            ga=int(st["ga"][0, i]),
            gd=int(st["gf"][0, i] - st["ga"][0, i])
        ))

    return sorted(rows, key=lambda r: r["rank"])


# ----------------------------------------------------------------------------------------------
# 4. SIMULATION MONTE CARLO DE TOUS LES MATCHS RESTANTS
# ----------------------------------------------------------------------------------------------

def simulate(n_sims=100_000, seed=42, elo=ELO, played=PLAYED, remaining=REMAINING,
             update_elo=True, k=K_ELO):
    """Simule plusieurs fins possibles de la phase de ligue.

    Paramètres
    ----------
    n_sims     : nombre de scénarios Monte Carlo à générer (100 000 par défaut).
    seed       : graine aléatoire. La même graine permet de reproduire le tirage.
    elo        : dictionnaire des notes Elo initiales ; par défaut ELO de ldc_data.py.
    played     : résultats réels déjà joués ; par défaut PLAYED de ldc_data.py.
    remaining  : liste des matchs à simuler ; par défaut REMAINING de ldc_data.py.
    update_elo : si True, met à jour l'Elo après chaque match restant simulé.
    k          : facteur K de mise à jour Elo.

    Pour chaque scénario, le programme simule tous les matchs de `remaining`.
    Chaque match reçoit un score aléatoire : les buts à domicile et à l'extérieur
    sont tirés séparément selon leurs lois de Poisson respectives.

    Si `update_elo=True`, les notes Elo évoluent après chaque match simulé. Le
    match suivant utilise donc les notes mises à jour. L'ordre de `remaining`
    a alors une importance : le code suppose que la liste est ordonnée selon
    la chronologie des matchs (par exemple journées 5, puis 6, puis 7, puis 8).

    Les résultats réels de `played` sont ajoutés tels quels au classement. Ils
    ne sont pas rejoués et ne déclenchent pas de mise à jour Elo dans cette
    fonction : les notes de départ `elo` sont supposées déjà tenir compte de
    ces matchs réels.

    Retour
    ------
    Dictionnaire contenant :
      - ranks : rang final de chaque équipe, forme (n_sims, 36) ;
      - pts   : points finaux, forme (n_sims, 36) ;
      - gd    : différences de buts finales, forme (n_sims, 36) ;
      - elo   : notes Elo finales, forme (n_sims, 36) ;
      - teams : noms des équipes, dans l'ordre des colonnes.
    """
    rng = np.random.default_rng(seed)

    # Les matchs déjà joués sont fixes : on répète leur score dans les n_sims
    # scénarios pour que les statistiques finales incluent les résultats réels.
    matches = [
        (IDX[h], IDX[a], np.full(n_sims, hg), np.full(n_sims, ag))
        for h, a, hg, ag in played
    ]

    # Une ligne par simulation, une colonne par équipe. Au départ, tous les
    # scénarios ont les mêmes notes Elo importées depuis ldc_data.py.
    elo_now = np.tile(np.array([elo[t] for t in TEAMS], dtype=float), (n_sims, 1))
    remaining_list = list(remaining)
    match_outcomes = np.empty((n_sims, len(remaining_list)), dtype=np.int8)

    # On simule les matchs restants un par un.
    for m_idx, (h, a) in enumerate(remaining_list):
        ih, ia = IDX[h], IDX[a]  # indices du domicile et de l'extérieur

        # Probabilité attendue de victoire du domicile, bonus terrain inclus.
        # Cette opération est vectorisée : elle calcule W pour les n_sims scénarios.
        W = 1 / (1 + 10 ** (-(elo_now[:, ih] + HOME_BONUS - elo_now[:, ia]) / 400))

        # Tirage des buts : un tirage de Poisson par équipe et par scénario.
        # hg et ag sont donc des tableaux de longueur n_sims.
        hg = rng.poisson(lam_home(W))
        ag = rng.poisson(lam_away(W))

        # Stocke l'issue du match (0 = victoire ext., 1 = nul, 2 = victoire dom.).
        match_outcomes[:, m_idx] = np.where(hg > ag, 2, np.where(hg == ag, 1, 0))

        # On conserve les scores du match pour calculer le classement final.
        matches.append((ih, ia, hg, ag))

        if update_elo:
            # Calcule le delta Elo du domicile dans chaque scénario.
            delta = elo_delta(W, hg, ag, k)

            # Mise à jour à somme nulle : le domicile gagne/perd delta,
            # l'extérieur perd/gagne exactement la même quantité.
            elo_now[:, ih] += delta
            elo_now[:, ia] -= delta

    # Une fois tous les scores simulés, on calcule les statistiques cumulées
    # (matchs réels + matchs simulés), puis le classement de chaque scénario.
    stats = _table_from_matches(matches)
    ranks = _rank(stats, rng)

    return dict(
        ranks=ranks,
        pts=stats["pts"],
        gd=stats["gf"] - stats["ga"],
        elo=elo_now.astype(np.float32),
        teams=TEAMS,
        remaining=remaining_list,
        match_outcomes=match_outcomes,
    )


# ----------------------------------------------------------------------------------------------
# 5. INDICATEURS CALCULÉS À PARTIR DES SIMULATIONS
# ----------------------------------------------------------------------------------------------

def rank_distribution(sim):
    """Calcule la distribution des places finales de chaque équipe.

    Résultat : matrice de forme (36, 36).
      - une ligne = une équipe ;
      - une colonne = une place (colonne 0 = 1re place, colonne 35 = 36e place).

    Chaque cellule contient la fréquence/probabilité de cette équipe à cette place.
    """
    ranks = sim["ranks"]
    n = ranks.shape[0]  # nombre de scénarios
    out = np.zeros((N_TEAMS, N_TEAMS))

    for t in range(N_TEAMS):
        # ranks[:, t] contient les places de l'équipe t dans tous les scénarios.
        # np.bincount compte combien de fois chaque place apparaît.
        out[t] = np.bincount(ranks[:, t] - 1, minlength=N_TEAMS) / n

    return out


def qualification_probs(sim):
    """Calcule les probabilités de qualification et les points moyens par équipe.

    Pour chaque équipe :
      - top8    : probabilité de finir de la 1re à la 8e place (qualification directe) ;
      - playoff : probabilité de finir de la 9e à la 24e place (barrages) ;
      - top24   : probabilité de finir de la 1re à la 24e place ;
      - out     : probabilité de finir de la 25e à la 36e place (élimination) ;
      - exp_pts : nombre moyen de points à la fin de la phase de ligue.
    """
    d = rank_distribution(sim)
    res = {}

    for t, name in enumerate(sim["teams"]):
        res[name] = dict(
            top8=d[t, :8].sum(),       # indices 0 à 7 = places 1 à 8
            playoff=d[t, 8:24].sum(), # indices 8 à 23 = places 9 à 24
            top24=d[t, :24].sum(),    # indices 0 à 23 = places 1 à 24
            out=d[t, 24:].sum(),      # indices 24 à 35 = places 25 à 36
            exp_pts=float(sim["pts"][:, t].mean())
        )

    return res


def prob_objectives(sim, objectives):
    """Probabilité que toutes les équipes atteignent simultanément leur objectif.

    Exemple :
        {"PSG": 8, "Lens": 24, "Lille": 24}

    signifie : PSG finit dans le top 8 ET Lens dans le top 24 ET Lille dans le
    top 24. On calcule une probabilité JOINTE : les objectifs doivent être
    réalisés dans un même scénario, pas seulement chacun séparément.

    `max_rank` est la place maximale autorisée (place <= max_rank).
    """
    # Au départ, tous les scénarios sont considérés comme réussis.
    ok = np.ones(sim["ranks"].shape[0], dtype=bool)

    for team, max_rank in objectives.items():
        # Pour chaque équipe demandée, on conserve les scénarios où elle atteint
        # son objectif. Les conditions successives sont combinées par ET logique.
        ok &= sim["ranks"][:, IDX[team]] <= max_rank

    return float(ok.mean())  # proportion de scénarios où tous les objectifs sont atteints


def points_thresholds(sim, positions=(8, 9, 16, 17, 24, 25)):
    """Distribution des points obtenus par l'équipe qui finit à certaines places.

    Par défaut, on étudie les points du 8e, 9e, 16e, 17e, 24e et 25e : ce sont
    des seuils utiles pour analyser les zones de qualification et d'élimination.

    Pour chaque place `p`, le résultat est un tableau : l'indice correspond au
    nombre de points et la valeur à la fréquence de ce nombre de points.
    """
    ranks, pts = sim["ranks"], sim["pts"]
    out = {}

    for p in positions:
        # Trouve, pour chaque scénario, l'indice de l'équipe classée à la place p.
        who = np.argmax(ranks == p, axis=1)

        # Récupère les points de cette équipe dans chaque scénario.
        v = pts[np.arange(ranks.shape[0]), who]

        # Compte les fréquences de chaque total de points et divise par le nombre
        # de scénarios pour obtenir une distribution de probabilités.
        out[p] = np.bincount(v, minlength=25) / len(v)

    return out


def qualification_by_points(sim):
    """Probabilité d'issue finale (Top 8 / Barrages / Éliminé) selon le total de points.

    Pour chaque nombre de points p (0 à 24), calcule la proportion d'équipes
    finissant avec exactement p points qui terminent :
      - dans le Top 8 (qualification directe) ;
      - entre la 9e et la 24e place (barrages) ;
      - entre la 25e et la 36e place (élimination).
    """
    pts = sim["pts"].ravel()
    ranks = sim["ranks"].ravel()
    total = np.bincount(pts, minlength=25).astype(float)
    top8 = np.bincount(pts[ranks <= 8], minlength=25).astype(float)
    playoff = np.bincount(pts[(ranks >= 9) & (ranks <= 24)], minlength=25).astype(float)
    out = np.bincount(pts[ranks >= 25], minlength=25).astype(float)

    valid = total > 0
    p_top8 = np.zeros(25, dtype=float)
    p_play = np.zeros(25, dtype=float)
    p_out = np.zeros(25, dtype=float)
    p_top8[valid] = top8[valid] / total[valid]
    p_play[valid] = playoff[valid] / total[valid]
    p_out[valid] = out[valid] / total[valid]
    return dict(total=total, top8=p_top8, playoff=p_play, out=p_out)


def match_importance(sim):
    """Calcule l'importance de chaque match restant pour chaque équipe.

    Pour un match m = (domicile, extérieur) et une équipe t, l'importance
    mesure l'écart maximal (entre 0 et 1) des chances de finir dans le Top 8
    ou le Top 24 selon les 3 issues possibles du match (victoire domicile,
    match nul, victoire extérieur).

    Retour : dict {team: liste de dicts triés par importance décroissante}.
    """
    ranks = sim["ranks"]
    outcomes = sim["match_outcomes"]
    remaining = sim["remaining"]
    teams = sim["teams"]
    n_sims = ranks.shape[0]
    min_samples = max(30, int(0.01 * n_sims))

    is_top8 = (ranks <= 8).astype(float)
    is_top24 = (ranks <= 24).astype(float)

    n_matches = len(remaining)
    n_teams = len(teams)
    imp_score = np.zeros((n_matches, n_teams), dtype=float)
    imp_min = np.zeros((n_matches, n_teams), dtype=float)
    imp_max = np.zeros((n_matches, n_teams), dtype=float)
    imp_zone = np.empty((n_matches, n_teams), dtype=object)

    for m_idx in range(n_matches):
        p8_by_o, p24_by_o = [], []
        for o in (0, 1, 2):
            mask = outcomes[:, m_idx] == o
            if int(mask.sum()) >= min_samples:
                p8_by_o.append(is_top8[mask].mean(axis=0))
                p24_by_o.append(is_top24[mask].mean(axis=0))

        if len(p8_by_o) < 2:
            imp_zone[m_idx, :] = "Top 24"
            continue

        min8, max8 = np.min(p8_by_o, axis=0), np.max(p8_by_o, axis=0)
        min24, max24 = np.min(p24_by_o, axis=0), np.max(p24_by_o, axis=0)
        s8 = max8 - min8
        s24 = max24 - min24

        use_top8 = s8 >= s24
        imp_score[m_idx] = np.where(use_top8, s8, s24)
        imp_min[m_idx] = np.where(use_top8, min8, min24)
        imp_max[m_idx] = np.where(use_top8, max8, max24)
        imp_zone[m_idx] = np.where(use_top8, "Top 8", "Top 24")

    result = {}
    for t_idx, team in enumerate(teams):
        entries = []
        for m_idx, (home, away) in enumerate(remaining):
            entries.append(
                dict(
                    home=home,
                    away=away,
                    is_own=(team == home or team == away),
                    importance=float(imp_score[m_idx, t_idx]),
                    min_prob=float(imp_min[m_idx, t_idx]),
                    max_prob=float(imp_max[m_idx, t_idx]),
                    zone=str(imp_zone[m_idx, t_idx]),
                )
            )
        entries.sort(key=lambda item: (-item["importance"], not item["is_own"]))
        result[team] = entries

    return result


# ----------------------------------------------------------------------------------------------
# 6. EXÉCUTION DIRECTE : PETIT EXEMPLE DE RÉSULTAT DANS LE TERMINAL
# ----------------------------------------------------------------------------------------------

if __name__ == "__main__":
    # Ce bloc ne s'exécute que si ce fichier est lancé directement avec Python.
    # Il ne s'exécute PAS lorsque le fichier est simplement importé par un autre module.
    # Ici, on lance 20 000 scénarios pour afficher les 10 équipes ayant la plus
    # forte probabilité de terminer dans le top 8.
    sim = simulate(20_000)
    q = qualification_probs(sim)

    for name, r in sorted(q.items(), key=lambda kv: -kv[1]["top8"])[:10]:
        print(
            f"{name:18s} top8={r['top8']:.3f} "
            f"barrages={r['playoff']:.3f} out={r['out']:.3f}"
        )
