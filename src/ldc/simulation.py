"""Moteur de simulation Monte Carlo vectorisé (NumPy) de la phase de ligue LDC.

Ce module est une couche métier pure (aucune écriture disque ni rendu graphique) :
  - Modèle de match : écart Elo (+ bonus domicile) -> probabilité attendue W ->
    lambdas de Poisson -> tirages de buts -> mise à jour Elo optionnelle.
  - Indicateurs statistiques : distribution des rangs, probabilités Top 8 / barrages /
    élimination, distribution des points par position (1re à 36e), seuils conditionnels
    par total de points, et importance des matchs restants.
"""
from __future__ import annotations

import numpy as np

from ldc.config import DEFAULT_N_SIMS, DEFAULT_SEED, HOME_BONUS, K_ELO
from ldc.data import PLAYED, REMAINING, TEAMS, load_elo

# Indexation canonique des équipes pour les tableaux NumPy (colonnes 0..35).
IDX: dict[str, int] = {team: i for i, team in enumerate(TEAMS)}
N_TEAMS: int = len(TEAMS)


# ----------------------------------------------------------------------------------------------
# 1. MODÈLE DE MATCH : Elo -> probabilité attendue -> buts attendus (loi de Poisson)
# ----------------------------------------------------------------------------------------------

def win_exp(elo1, elo2):
    """Calcule la probabilité théorique de victoire de l'équipe 1 à partir de l'écart Elo."""
    return 1.0 / (1.0 + 10.0 ** (-(elo1 - elo2) / 400.0))


def lam_home(W):
    """Renvoie le nombre moyen de buts attendus par l'équipe à domicile (lambda de Poisson).

    Polynômes par morceaux ajustés dans le projet (seuil W = 0.9), vectorisés NumPy.
    """
    W = np.asarray(W, dtype=float)
    d = W - 0.9
    low = -5.42301 * W**4 + 15.49728 * W**3 - 12.6499 * W**2 + 5.36198 * W + 0.22863
    high = 231098.16153 * d**4 - 30953.10199 * d**3 + 1347.51495 * d**2 - 1.63074 * d + 2.54747
    return np.where(W <= 0.9, low, high)


def lam_away(W):
    """Renvoie le nombre moyen de buts attendus par l'équipe à l'extérieur (lambda de Poisson).

    Attention : W reste la probabilité attendue de victoire de l'équipe à domicile.
    """
    W = np.asarray(W, dtype=float)
    d = W - 0.1
    low = 90173.57949 * d**4 + 10064.38612 * d**3 + 218.6628 * d**2 - 11.06198 * d + 2.28291
    high = -1.25010 * W**4 - 1.99984 * W**3 + 6.54946 * W**2 - 5.83979 * W + 2.80352
    return np.where(W < 0.1, low, high)


def elo_delta(W_home, hg, ag, k=K_ELO):
    """Variation Elo à somme nulle de l'équipe à domicile après un match simulé.

    Formule : `k * g * (r - W_home)` où `g` pondère l'écart de buts
    (1 pour 0-1 but, 1.5 pour 2 buts, (11 + écart)/8 au-delà).
    """
    margin = np.abs(hg - ag)
    g = np.where(margin <= 1, 1.0, np.where(margin == 2, 1.5, (11 + margin) / 8))
    result = np.where(hg > ag, 1.0, np.where(hg == ag, 0.5, 0.0))
    return k * g * (result - W_home)


def lambdas_home(home: str, away: str, elo: dict[str, int] | None = None):
    """Calcule `(lambda_domicile, lambda_exterieur)` d'un match donné."""
    ratings = elo if elo is not None else load_elo()[0]
    W = win_exp(ratings[home] + HOME_BONUS, ratings[away])
    return lam_home(W), lam_away(W)


# ----------------------------------------------------------------------------------------------
# 2. CONSTRUCTION DES STATISTIQUES ET CLASSEMENT
# ----------------------------------------------------------------------------------------------

def _table_from_matches(matches):
    """Cumule points, buts et victoires de toutes les équipes sur l'ensemble des scénarios."""
    n_sims = matches[0][2].shape[0]
    zeros = lambda: np.zeros((n_sims, N_TEAMS), dtype=np.int32)
    pts, gf, ga, agf, wins, awins = zeros(), zeros(), zeros(), zeros(), zeros(), zeros()

    for h, a, hg, ag in matches:
        pts[:, h] += np.where(hg > ag, 3, np.where(hg == ag, 1, 0))
        pts[:, a] += np.where(ag > hg, 3, np.where(hg == ag, 1, 0))
        gf[:, h] += hg
        ga[:, h] += ag
        gf[:, a] += ag
        ga[:, a] += hg
        agf[:, a] += ag
        wins[:, h] += hg > ag
        wins[:, a] += ag > hg
        awins[:, a] += ag > hg

    return dict(pts=pts, gf=gf, ga=ga, agf=agf, wins=wins, awins=awins)


def _rank(stats, rng):
    """Classe les 36 équipes dans chaque simulation (1 = premier, 36 = dernier).

    Critères par ordre de priorité : points, différence de buts, buts marqués,
    buts à l'extérieur, victoires, victoires à l'extérieur, puis départage aléatoire.
    """
    n_sims = stats["pts"].shape[0]
    gd = stats["gf"] - stats["ga"]

    key = stats["pts"].astype(np.int64)
    key = key * 256 + (gd + 128)
    key = key * 256 + stats["gf"]
    key = key * 256 + stats["agf"]
    key = key * 16 + stats["wins"]
    key = key * 16 + stats["awins"]
    key = key * 1024 + rng.integers(0, 1024, size=(n_sims, N_TEAMS))

    order = np.argsort(-key, axis=1)
    ranks = np.empty_like(order)
    rows = np.arange(n_sims)[:, None]
    ranks[rows, order] = np.arange(1, N_TEAMS + 1)[None, :]
    return ranks


def current_table(played=PLAYED) -> list[dict]:
    """Construit le classement réel actuel à partir des seuls matchs déjà joués."""
    matches = [(IDX[h], IDX[a], np.array([hg]), np.array([ag])) for h, a, hg, ag in played]
    stats = _table_from_matches(matches)
    ranks = _rank(stats, np.random.default_rng(0))[0]

    rows = [
        dict(
            team=team,
            rank=int(ranks[IDX[team]]),
            pts=int(stats["pts"][0, IDX[team]]),
            gf=int(stats["gf"][0, IDX[team]]),
            ga=int(stats["ga"][0, IDX[team]]),
            gd=int(stats["gf"][0, IDX[team]] - stats["ga"][0, IDX[team]]),
        )
        for team in TEAMS
    ]
    return sorted(rows, key=lambda r: r["rank"])


# ----------------------------------------------------------------------------------------------
# 3. SIMULATION MONTE CARLO
# ----------------------------------------------------------------------------------------------

def simulate(
    n_sims: int = DEFAULT_N_SIMS,
    seed: int = DEFAULT_SEED,
    elo: dict[str, int] | None = None,
    elo_date: str | None = None,
    played=PLAYED,
    remaining=REMAINING,
    update_elo: bool = True,
    k: float = K_ELO,
) -> dict:
    """Simule `n_sims` fins possibles de la phase de ligue (résultats fixes + matchs restants)."""
    if elo is None:
        elo, loaded_date = load_elo()
        elo_date = elo_date or loaded_date

    rng = np.random.default_rng(seed)

    matches = [
        (IDX[h], IDX[a], np.full(n_sims, hg), np.full(n_sims, ag))
        for h, a, hg, ag in played
    ]

    elo_now = np.tile(np.array([elo[t] for t in TEAMS], dtype=float), (n_sims, 1))
    remaining_list = list(remaining)
    match_outcomes = np.empty((n_sims, len(remaining_list)), dtype=np.int8)

    for m_idx, (h, a) in enumerate(remaining_list):
        ih, ia = IDX[h], IDX[a]
        W = win_exp(elo_now[:, ih] + HOME_BONUS, elo_now[:, ia])
        hg = rng.poisson(lam_home(W))
        ag = rng.poisson(lam_away(W))

        # 0 = victoire extérieur, 1 = nul, 2 = victoire domicile.
        match_outcomes[:, m_idx] = np.where(hg > ag, 2, np.where(hg == ag, 1, 0))
        matches.append((ih, ia, hg, ag))

        if update_elo:
            delta = elo_delta(W, hg, ag, k)
            elo_now[:, ih] += delta
            elo_now[:, ia] -= delta

    stats = _table_from_matches(matches)
    ranks = _rank(stats, rng)

    return dict(
        ranks=ranks,
        pts=stats["pts"],
        gd=stats["gf"] - stats["ga"],
        elo=elo_now.astype(np.float32),
        elo_date=elo_date,
        teams=TEAMS,
        remaining=remaining_list,
        match_outcomes=match_outcomes,
    )


# ----------------------------------------------------------------------------------------------
# 4. INDICATEURS STATISTIQUES
# ----------------------------------------------------------------------------------------------

def rank_distribution(sim: dict) -> np.ndarray:
    """Matrice `(36, 36)` : probabilité que l'équipe `t` finisse à la place `p + 1`."""
    ranks = sim["ranks"]
    n_sims = ranks.shape[0]
    out = np.zeros((N_TEAMS, N_TEAMS))
    for t in range(N_TEAMS):
        out[t] = np.bincount(ranks[:, t] - 1, minlength=N_TEAMS) / n_sims
    return out


def qualification_probs(sim: dict, rank_dist: np.ndarray | None = None) -> dict[str, dict[str, float]]:
    """Probabilités Top 8 / barrages (9-24) / Top 24 / élimination (25-36) et points moyens."""
    dist = rank_dist if rank_dist is not None else rank_distribution(sim)
    res: dict[str, dict[str, float]] = {}
    for t, name in enumerate(sim["teams"]):
        row = dist[t]
        res[name] = dict(
            top8=float(row[:8].sum()),
            playoff=float(row[8:24].sum()),
            top24=float(row[:24].sum()),
            out=float(row[24:].sum()),
            exp_pts=float(sim["pts"][:, t].mean()),
        )
    return res


def prob_objectives(sim: dict, objectives: dict[str, int]) -> float:
    """Probabilité jointe que chaque équipe atteigne au moins son rang maximal cible."""
    ok = np.ones(sim["ranks"].shape[0], dtype=bool)
    for team, max_rank in objectives.items():
        ok &= sim["ranks"][:, IDX[team]] <= max_rank
    return float(ok.mean())


def points_by_position(sim: dict) -> np.ndarray:
    """Matrice `(n_sims, 36)` des points du club classé à chaque position finale (colonne x-1 = place x)."""
    order = np.argsort(sim["ranks"], axis=1)
    return np.take_along_axis(sim["pts"], order, axis=1)


def points_thresholds(
    sim: dict,
    positions: tuple[int, ...] = (8, 9, 16, 17, 24, 25),
    pts_by_rank: np.ndarray | None = None,
) -> dict[int, np.ndarray]:
    """Distribution du nombre de points du club classé à chacune des positions demandées."""
    matrix = pts_by_rank if pts_by_rank is not None else points_by_position(sim)
    n_sims = matrix.shape[0]
    return {
        pos: np.bincount(matrix[:, pos - 1], minlength=25) / n_sims
        for pos in positions
    }


def qualification_by_points(sim: dict) -> dict[str, np.ndarray]:
    """Probabilité d'issue finale (Top 8 / Barrages / Éliminé) conditionnelle au total de points (0..24)."""
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


def match_importance(sim: dict) -> dict[str, list[dict]]:
    """Calcule l'importance de chaque match restant pour chaque équipe.

    Pour un match `m` et une équipe `t`, calcule le classement final moyen de `t`
    conditionnellement à chacune des 3 issues possibles du match (1 / N / 2).
    Le score d'importance est le plus grand écart de classement moyen (en places)
    entre deux issues : `max(r) - min(r)`.
    """
    ranks = sim["ranks"].astype(float)
    outcomes = sim["match_outcomes"]
    remaining = sim["remaining"]
    teams = sim["teams"]
    n_sims = ranks.shape[0]
    min_samples = max(30, int(0.01 * n_sims))

    n_matches = len(remaining)
    n_teams = len(teams)
    imp_score = np.zeros((n_matches, n_teams), dtype=float)
    imp_best_rank = np.zeros((n_matches, n_teams), dtype=float)
    imp_worst_rank = np.zeros((n_matches, n_teams), dtype=float)

    for m_idx in range(n_matches):
        mean_rank_by_o = []
        for outcome in (0, 1, 2):
            mask = outcomes[:, m_idx] == outcome
            if int(mask.sum()) >= min_samples:
                mean_rank_by_o.append(ranks[mask].mean(axis=0))

        if len(mean_rank_by_o) < 2:
            continue

        best_r = np.min(mean_rank_by_o, axis=0)
        worst_r = np.max(mean_rank_by_o, axis=0)
        imp_score[m_idx] = worst_r - best_r
        imp_best_rank[m_idx] = best_r
        imp_worst_rank[m_idx] = worst_r

    result: dict[str, list[dict]] = {}
    for t_idx, team in enumerate(teams):
        entries = [
            dict(
                home=home,
                away=away,
                is_own=(team == home or team == away),
                importance=float(imp_score[m_idx, t_idx]),
                best_rank=float(imp_best_rank[m_idx, t_idx]),
                worst_rank=float(imp_worst_rank[m_idx, t_idx]),
            )
            for m_idx, (home, away) in enumerate(remaining)
        ]
        entries.sort(key=lambda item: (-item["importance"], not item["is_own"]))
        result[team] = entries

    return result
