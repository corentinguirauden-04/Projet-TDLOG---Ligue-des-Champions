"""Moteur de simulation Monte Carlo vectorisé (NumPy) de la phase de ligue LDC.

Ce module est une couche métier pure (aucune écriture disque ni rendu graphique) :
  - Modèle de match : écart Elo fixe (+ bonus domicile) -> probabilité attendue W ->
    lambdas de Poisson -> tirages de buts.
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

def _table_from_matches(matches, n_sims: int | None = None):
    """Cumule points, buts et victoires de toutes les équipes sur l'ensemble des scénarios."""
    count = n_sims if n_sims is not None else (matches[0][2].shape[0] if matches else 1)
    zeros = lambda: np.zeros((count, N_TEAMS), dtype=np.int32)
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
    stats = _table_from_matches(matches, n_sims=1)
    ranks = _rank(stats, np.random.default_rng(0))[0]
    played_counts = {team: 0 for team in TEAMS}
    for h, a, _, _ in played:
        played_counts[h] += 1
        played_counts[a] += 1

    rows = [
        dict(
            team=team,
            rank=int(ranks[IDX[team]]),
            played=played_counts[team],
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
    update_elo: bool = False,
    k: float = K_ELO,
) -> dict:
    """Simule `n_sims` fins possibles de la phase de ligue (résultats fixes + matchs restants).

    Par défaut (`update_elo=False`), les notes Elo restent fixes tout au long de
    chaque simulation : l'ordre des matchs restants n'introduit ainsi aucun biais
    séquentiel entre rencontres d'une même journée.
    """
    if elo is None:
        elo, loaded_date = load_elo()
        elo_date = elo_date or loaded_date

    rng = np.random.default_rng(seed)

    # Cumule d'abord les matchs déjà joués sur un vecteur 1D (36 équipes) puis diffuse sur n_sims :
    # évite d'allouer des dizaines de matrices (n_sims,) constantes à 500 000+ simulations.
    base_pts = np.zeros(N_TEAMS, dtype=np.int32)
    base_gf = np.zeros(N_TEAMS, dtype=np.int32)
    base_ga = np.zeros(N_TEAMS, dtype=np.int32)
    base_agf = np.zeros(N_TEAMS, dtype=np.int32)
    base_wins = np.zeros(N_TEAMS, dtype=np.int32)
    base_awins = np.zeros(N_TEAMS, dtype=np.int32)
    for h, a, hg_i, ag_i in played:
        ih, ia = IDX[h], IDX[a]
        base_pts[ih] += 3 if hg_i > ag_i else (1 if hg_i == ag_i else 0)
        base_pts[ia] += 3 if ag_i > hg_i else (1 if hg_i == ag_i else 0)
        base_gf[ih] += hg_i
        base_ga[ih] += ag_i
        base_gf[ia] += ag_i
        base_ga[ia] += hg_i
        base_agf[ia] += ag_i
        if hg_i > ag_i:
            base_wins[ih] += 1
        elif ag_i > hg_i:
            base_wins[ia] += 1
            base_awins[ia] += 1

    pts = np.broadcast_to(base_pts, (n_sims, N_TEAMS)).copy()
    gf = np.broadcast_to(base_gf, (n_sims, N_TEAMS)).copy()
    ga = np.broadcast_to(base_ga, (n_sims, N_TEAMS)).copy()
    agf = np.broadcast_to(base_agf, (n_sims, N_TEAMS)).copy()
    wins = np.broadcast_to(base_wins, (n_sims, N_TEAMS)).copy()
    awins = np.broadcast_to(base_awins, (n_sims, N_TEAMS)).copy()

    base_elo = np.array([elo[t] for t in TEAMS], dtype=float)
    elo_now = np.tile(base_elo, (n_sims, 1)) if update_elo else None
    remaining_list = list(remaining)
    match_outcomes = np.empty((n_sims, len(remaining_list)), dtype=np.int8)

    for m_idx, (h, a) in enumerate(remaining_list):
        ih, ia = IDX[h], IDX[a]
        if update_elo and elo_now is not None:
            W = win_exp(elo_now[:, ih] + HOME_BONUS, elo_now[:, ia])
            hg = rng.poisson(lam_home(W)).astype(np.int32)
            ag = rng.poisson(lam_away(W)).astype(np.int32)
            delta = elo_delta(W, hg, ag, k)
            elo_now[:, ih] += delta
            elo_now[:, ia] -= delta
        else:
            # Elo constant : W et les lambdas sont scalaires, tirage direct sur n_sims.
            W = win_exp(base_elo[ih] + HOME_BONUS, base_elo[ia])
            hg = rng.poisson(float(lam_home(W)), size=n_sims).astype(np.int32)
            ag = rng.poisson(float(lam_away(W)), size=n_sims).astype(np.int32)

        home_win = hg > ag
        away_win = ag > hg
        draw = hg == ag
        # 0 = victoire extérieur, 1 = nul, 2 = victoire domicile.
        match_outcomes[:, m_idx] = np.where(home_win, 2, np.where(draw, 1, 0))

        pts[:, ih] += home_win * 3 + draw
        pts[:, ia] += away_win * 3 + draw
        gf[:, ih] += hg
        ga[:, ih] += ag
        gf[:, ia] += ag
        ga[:, ia] += hg
        agf[:, ia] += ag
        wins[:, ih] += home_win
        wins[:, ia] += away_win
        awins[:, ia] += away_win

    stats = dict(pts=pts, gf=gf, ga=ga, agf=agf, wins=wins, awins=awins)
    ranks = _rank(stats, rng)

    final_elo = elo_now.astype(np.float32) if elo_now is not None else base_elo.astype(np.float32)
    return dict(
        ranks=ranks,
        pts=stats["pts"],
        gd=stats["gf"] - stats["ga"],
        elo=final_elo,
        elo_date=elo_date,
        teams=TEAMS,
        n_played=len(played),
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


def _qualification_by_points_arrays(pts: np.ndarray, ranks: np.ndarray) -> dict[str, np.ndarray]:
    """Calcule la probabilité conditionnelle d'issue finale pour chaque total de points (0..24)."""
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


def qualification_by_points(sim: dict) -> dict[str, np.ndarray]:
    """Probabilité d'issue finale (Top 8 / Barrages / Éliminé) conditionnelle au total de points (0..24)."""
    return _qualification_by_points_arrays(sim["pts"].ravel(), sim["ranks"].ravel())


def team_qualification_by_points(sim: dict, team: str) -> dict[str, np.ndarray]:
    """Probabilité d'issue finale d'une équipe donnée conditionnelle à son total final de points (0..24)."""
    t_idx = IDX[team]
    return _qualification_by_points_arrays(sim["pts"][:, t_idx], sim["ranks"][:, t_idx])


def match_importance(sim: dict) -> dict[str, list[dict]]:
    """Mesure l'effet de chaque résultat possible sur le classement final d'une équipe.

    Pour chaque match restant et chaque équipe, conserve :
      - le rang final moyen conditionnel à victoire domicile / nul / victoire extérieur ;
      - les probabilités conditionnelles de Top 8 et de Top 24 pour ces trois issues ;
      - les amplitudes (max - min) utilisées pour classer les matchs clés.

    Une issue est considérée exploitable à partir de max(30, 1 % des simulations).
    Les calculs sont vectorisés par blocs pour maîtriser la mémoire.
    """
    ranks = sim["ranks"]
    outcomes = sim["match_outcomes"]
    remaining = sim["remaining"]
    teams = sim["teams"]
    n_sims = ranks.shape[0]
    min_samples = max(30, int(0.01 * n_sims))

    n_matches = len(remaining)
    n_teams = len(teams)
    # Convention outcome : 0 = victoire extérieur, 1 = nul, 2 = victoire domicile.
    counts = np.zeros((3, n_matches), dtype=np.int64)
    sum_rank = np.zeros((3, n_matches, n_teams), dtype=np.float64)
    sum_top8 = np.zeros((3, n_matches, n_teams), dtype=np.float64)
    sum_top24 = np.zeros((3, n_matches, n_teams), dtype=np.float64)

    chunk_size = 100_000
    for start in range(0, n_sims, chunk_size):
        end = min(start + chunk_size, n_sims)
        r_blk = ranks[start:end]
        o_blk = outcomes[start:end]
        r_f = r_blk.astype(np.float32)
        t8_f = (r_blk <= 8).astype(np.float32)
        t24_f = (r_blk <= 24).astype(np.float32)
        for o in (0, 1, 2):
            mask = (o_blk == o).astype(np.float32)
            counts[o] += mask.sum(axis=0, dtype=np.int64)
            sum_rank[o] += (mask.T @ r_f).astype(np.float64)
            sum_top8[o] += (mask.T @ t8_f).astype(np.float64)
            sum_top24[o] += (mask.T @ t24_f).astype(np.float64)

    # NaN permet de distinguer une issue insuffisamment représentée d'une vraie probabilité nulle.
    rank_by_outcome = np.full((3, n_matches, n_teams), np.nan, dtype=np.float64)
    top8_by_outcome = np.full((3, n_matches, n_teams), np.nan, dtype=np.float64)
    top24_by_outcome = np.full((3, n_matches, n_teams), np.nan, dtype=np.float64)

    # Valeurs de repli non conditionnelles : les champs historiques best/worst/min/max
    # doivent toujours rester numériques (export JSON et consommateurs existants).
    # Les trois champs conditionnels par issue restent à None lorsqu'une issue est rare.
    baseline_rank = ranks.mean(axis=0, dtype=np.float64)
    baseline_top8 = (ranks <= 8).mean(axis=0, dtype=np.float64)
    baseline_top24 = (ranks <= 24).mean(axis=0, dtype=np.float64)

    imp_rank = np.zeros((n_matches, n_teams), dtype=float)
    best_rank = np.broadcast_to(baseline_rank, (n_matches, n_teams)).copy()
    worst_rank = np.broadcast_to(baseline_rank, (n_matches, n_teams)).copy()
    imp_top8 = np.zeros((n_matches, n_teams), dtype=float)
    top8_min = np.broadcast_to(baseline_top8, (n_matches, n_teams)).copy()
    top8_max = np.broadcast_to(baseline_top8, (n_matches, n_teams)).copy()
    imp_top24 = np.zeros((n_matches, n_teams), dtype=float)
    top24_min = np.broadcast_to(baseline_top24, (n_matches, n_teams)).copy()
    top24_max = np.broadcast_to(baseline_top24, (n_matches, n_teams)).copy()

    for m_idx in range(n_matches):
        valid_o = [o for o in (0, 1, 2) if int(counts[o, m_idx]) >= min_samples]
        if len(valid_o) < 2:
            continue

        for o in valid_o:
            denominator = float(counts[o, m_idx])
            rank_by_outcome[o, m_idx] = sum_rank[o, m_idx] / denominator
            top8_by_outcome[o, m_idx] = sum_top8[o, m_idx] / denominator
            top24_by_outcome[o, m_idx] = sum_top24[o, m_idx] / denominator

        rank_values = np.stack([rank_by_outcome[o, m_idx] for o in valid_o])
        top8_values = np.stack([top8_by_outcome[o, m_idx] for o in valid_o])
        top24_values = np.stack([top24_by_outcome[o, m_idx] for o in valid_o])

        best_rank[m_idx] = np.min(rank_values, axis=0)
        worst_rank[m_idx] = np.max(rank_values, axis=0)
        imp_rank[m_idx] = worst_rank[m_idx] - best_rank[m_idx]

        top8_min[m_idx] = np.min(top8_values, axis=0)
        top8_max[m_idx] = np.max(top8_values, axis=0)
        imp_top8[m_idx] = top8_max[m_idx] - top8_min[m_idx]

        top24_min[m_idx] = np.min(top24_values, axis=0)
        top24_max[m_idx] = np.max(top24_values, axis=0)
        imp_top24[m_idx] = top24_max[m_idx] - top24_min[m_idx]

    def maybe_float(array: np.ndarray, outcome: int, m_idx: int, t_idx: int):
        value = array[outcome, m_idx, t_idx]
        return float(value) if np.isfinite(value) else None

    result: dict[str, list[dict]] = {}
    for t_idx, team in enumerate(teams):
        entries = []
        for m_idx, (home, away) in enumerate(remaining):
            entries.append({
                "home": home,
                "away": away,
                "is_own": team == home or team == away,
                "importance": float(imp_rank[m_idx, t_idx]),
                "best_rank": float(best_rank[m_idx, t_idx]) if np.isfinite(best_rank[m_idx, t_idx]) else None,
                "worst_rank": float(worst_rank[m_idx, t_idx]) if np.isfinite(worst_rank[m_idx, t_idx]) else None,
                "top8_importance": float(imp_top8[m_idx, t_idx]),
                "top8_min": float(top8_min[m_idx, t_idx]) if np.isfinite(top8_min[m_idx, t_idx]) else None,
                "top8_max": float(top8_max[m_idx, t_idx]) if np.isfinite(top8_max[m_idx, t_idx]) else None,
                "top24_importance": float(imp_top24[m_idx, t_idx]),
                "top24_min": float(top24_min[m_idx, t_idx]) if np.isfinite(top24_min[m_idx, t_idx]) else None,
                "top24_max": float(top24_max[m_idx, t_idx]) if np.isfinite(top24_max[m_idx, t_idx]) else None,
                # Valeurs du point de vue du match : home_win / draw / away_win.
                "rank_home_win": maybe_float(rank_by_outcome, 2, m_idx, t_idx),
                "rank_draw": maybe_float(rank_by_outcome, 1, m_idx, t_idx),
                "rank_away_win": maybe_float(rank_by_outcome, 0, m_idx, t_idx),
                "top8_home_win": maybe_float(top8_by_outcome, 2, m_idx, t_idx),
                "top8_draw": maybe_float(top8_by_outcome, 1, m_idx, t_idx),
                "top8_away_win": maybe_float(top8_by_outcome, 0, m_idx, t_idx),
                "top24_home_win": maybe_float(top24_by_outcome, 2, m_idx, t_idx),
                "top24_draw": maybe_float(top24_by_outcome, 1, m_idx, t_idx),
                "top24_away_win": maybe_float(top24_by_outcome, 0, m_idx, t_idx),
                "home_win_n": int(counts[2, m_idx]),
                "draw_n": int(counts[1, m_idx]),
                "away_win_n": int(counts[0, m_idx]),
            })
        entries.sort(key=lambda item: (-item["importance"], not item["is_own"]))
        result[team] = entries

    return result
