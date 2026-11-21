"""
Visuels de la simulation (style "plateau télé" : fond sombre, gros chiffres, trois zones de couleur).
Zones : top 8 = qualifié direct, 9-24 = barrages, 25-36 = éliminé.
"""
import datetime as dt

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Rectangle

import ldc_data
import ldc_sim as s

_FR_MONTHS = (
    "",
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
)


def _format_fr_date(iso_date: str | None) -> str:
    """Formate une date ISO (AAAA-MM-JJ) en français (ex. '21 novembre 2026')."""
    if iso_date:
        try:
            d = dt.date.fromisoformat(iso_date)
        except ValueError:
            d = dt.date.today()
    else:
        d = dt.date.today()
    day_str = "1er" if d.day == 1 else str(d.day)
    return f"{day_str} {_FR_MONTHS[d.month]} {d.year}"


def _matchday_date_label() -> str:
    """Construit le repère temporel 'après la journée n, en date du xxx'."""
    matches_per_day = max(1, s.N_TEAMS // 2)
    journee = len(ldc_data.PLAYED) // matches_per_day
    date_label = _format_fr_date(getattr(ldc_data, "ELO_DATE", None))
    return f"après la journée {journee}, en date du {date_label}"

BG_TOP = "#14217a"    # bleu foncé (haut du dégradé)
BG = "#060b33"        # bleu nuit (bas du dégradé)
INK = "#060b33"       # texte sombre posé sur les barres claires
PANEL = "#ffffff16"   # panneaux translucides
TXT = "#ffffff"
MUTED = "#a9b7ee"
C_TOP8 = "#2de2c5"    # vert-cyan : 8es de finale directs
C_PLAY = "#ffc857"    # ambre : barrages
C_OUT = "#ff5d8f"     # rose-rouge : éliminé


def _new_fig(size):
    """Figure à fond dégradé bleu foncé."""
    fig = plt.figure(figsize=size, facecolor=BG)
    bg = fig.add_axes([0, 0, 1, 1], zorder=-10)
    from matplotlib.colors import LinearSegmentedColormap
    cmap = LinearSegmentedColormap.from_list("bg", [BG_TOP, BG])
    bg.imshow(np.linspace(0, 1, 256)[:, None], aspect="auto", cmap=cmap, extent=[0, 1, 0, 1])
    bg.axis("off")
    return fig

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "text.color": TXT, "axes.labelcolor": MUTED,
    "xtick.color": MUTED, "ytick.color": MUTED,
})


def _zone_color(place):
    return C_TOP8 if place <= 8 else (C_PLAY if place <= 24 else C_OUT)


def pct(x):
    """Pourcentage lisible à 1 décimale ('<0.1 %' / '>99.9 %' aux extrêmes)."""
    p = 100 * x
    if p == 0:
        return "0.0 %"
    if p < 0.05:
        return "<0.1 %"
    if p == 100:
        return "100.0 %"
    if p > 99.95:
        return ">99.9 %"
    return f"{p:.1f} %"


def team_card(team, sim, table, path, n_sims=None, rank_dist=None, qualifications=None):
    """Enregistre la fiche graphique d'une équipe.

    `rank_dist` et `qualifications` sont facultatifs. Le script de génération
    les calcule une seule fois puis les transmet à chaque fiche, ce qui évite
    de refaire 36 fois les mêmes calculs.
    """
    if rank_dist is None:
        rank_dist = s.rank_distribution(sim)
    if qualifications is None:
        qualifications = s.qualification_probs(sim)

    dist = rank_dist[s.IDX[team]]
    q = qualifications[team]
    cur = next(r for r in table if r["team"] == team)
    n_sims = n_sims or sim["ranks"].shape[0]

    fig = _new_fig((12, 6.75))
    ax = fig.add_axes([0.07, 0.15, 0.88, 0.47], facecolor="none")

    places = np.arange(1, s.N_TEAMS + 1)
    # Zones de fond nettement différenciées + séparateurs verticaux aux frontières 24/25 et 8/9.
    ax.axvspan(s.N_TEAMS + 0.5, 24.5, color=C_OUT, alpha=0.17, lw=0, zorder=1)
    ax.axvspan(24.5, 8.5, color=C_PLAY, alpha=0.14, lw=0, zorder=1)
    ax.axvspan(8.5, 0.5, color=C_TOP8, alpha=0.17, lw=0, zorder=1)
    ax.axvline(24.5, color=C_OUT, linestyle="--", linewidth=1.1, alpha=0.70, zorder=2)
    ax.axvline(8.5, color=C_TOP8, linestyle="--", linewidth=1.1, alpha=0.70, zorder=2)

    ax.bar(places, 100 * dist, color=[_zone_color(p) for p in places], width=0.72, zorder=3)
    for p, v in zip(places, dist):
        if v >= 0.03:
            ax.text(p, 100 * v + 0.6, f"{100 * v:.1f}", ha="center", va="bottom", fontsize=7.5,
                    color=TXT, zorder=4)

    # Axe inversé : pires classements à gauche (36e), meilleurs classements à droite (1er).
    ax.set_xlim(s.N_TEAMS + 0.5, 0.5)
    y_max = max(100 * dist.max() * 1.32, 12)
    ax.set_ylim(0, y_max)
    ax.set_xticks([s.N_TEAMS, 32, 28, 24, 20, 16, 12, 8, 4, 1])

    # Repères discrets en haut de chaque zone pour identifier immédiatement les 3 paliers.
    label_y = y_max * 0.945
    ax.text(30.5, label_y, f"ÉLIMINATION (25-{s.N_TEAMS})", ha="center", va="top",
            fontsize=8.5, fontweight="bold", color=C_OUT, alpha=0.92, zorder=4)
    ax.text(16.5, label_y, "BARRAGES (9-24)", ha="center", va="top",
            fontsize=8.5, fontweight="bold", color=C_PLAY, alpha=0.92, zorder=4)
    ax.text(4.5, label_y, "TOP 8 (1-8)", ha="center", va="top",
            fontsize=8.5, fontweight="bold", color=C_TOP8, alpha=0.92, zorder=4)

    # L'axe vertical est en pourcentage : il permet de lire la hauteur de chaque barre.
    y_step = 5 if y_max <= 25 else 10
    y_ticks = np.arange(0, y_max + 0.001, y_step)
    ax.set_yticks(y_ticks)
    ax.set_yticklabels([f"{v:.0f} %" for v in y_ticks], fontsize=8)
    ax.grid(axis="y", color=TXT, alpha=0.12, linewidth=0.7, zorder=0)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    ax.spines["left"].set_color(MUTED)
    ax.spines["bottom"].set_color(MUTED)
    ax.tick_params(axis="x", length=0, labelsize=10)
    ax.tick_params(axis="y", length=0, colors=MUTED)
    ax.set_xlabel("Place finale au classement de la phase de ligue (de la 36e à la 1re)", fontsize=10, labelpad=8)
    ax.set_ylabel("Probabilité", fontsize=10, labelpad=8)

    # En-tête
    fig.text(0.07, 0.92, team.upper(), fontsize=30, fontweight="bold", color=TXT, va="center")
    fig.text(0.07, 0.855,
             f"Classement actuel : {cur['rank']}e  ·  {cur['pts']} pts  ·  diff {cur['gd']:+d}  ·  {_matchday_date_label().capitalize()}",
             fontsize=11.5, color=MUTED, va="center")

    # Trois indicateurs demandés : Top 8, Top 24 et élimination.
    # La probabilité de barrages (places 9 à 24) reste disponible dans le CSV
    # et peut se calculer comme Top 24 moins Top 8.
    boxes = [("QUALIFICATION DIRECTE", "Top 8", pct(q["top8"]), C_TOP8),
             ("QUALIFICATION", "Top 24", pct(q["top24"]), C_PLAY),
             ("ÉLIMINATION", f"Places 25 à {s.N_TEAMS}", pct(q["out"]), C_OUT)]
    _draw_kpi_boxes(fig, boxes)

    fig.text(0.07, 0.055,
             f"Points finaux moyens : {q['exp_pts']:.1f}   ·   Probabilité de barrages (9-{s.N_TEAMS if s.N_TEAMS < 24 else 24}) : {pct(q['playoff'])}",
             fontsize=9, color=MUTED, va="center")
    fig.text(0.07, 0.025,
             f"Monte Carlo : {n_sims:,} simulations · Modèle Elo + loi de Poisson".replace(",", " "),
             fontsize=8, color=MUTED, va="center")
    fig.savefig(path, dpi=130, facecolor=BG)
    plt.close(fig)


def overview(sim, table, path):
    """Vue d'ensemble : les 36 équipes, barre empilée top 8 / barrages / éliminé."""
    q = s.qualification_probs(sim)
    order = sorted(s.TEAMS, key=lambda t: (-(q[t]["top8"] * 2 + q[t]["playoff"]), -q[t]["exp_pts"]))
    cur = {r["team"]: r for r in table}

    fig = _new_fig((12, 13))
    ax = fig.add_axes([0.20, 0.05, 0.66, 0.84], facecolor="none")
    y = np.arange(len(order))[::-1]
    for yi, t in zip(y, order):
        a, b, c = q[t]["top8"], q[t]["playoff"], q[t]["out"]
        ax.barh(yi, a, color=C_TOP8, height=0.72)
        ax.barh(yi, b, left=a, color=C_PLAY, height=0.72)
        ax.barh(yi, c, left=a + b, color=C_OUT, height=0.72)
        if a >= 0.08:
            ax.text(a / 2, yi, pct(a), ha="center", va="center", fontsize=8, color=INK, fontweight="bold")
        if b >= 0.09:
            ax.text(a + b / 2, yi, pct(b), ha="center", va="center", fontsize=8, color=INK, fontweight="bold")
        if c >= 0.08:
            ax.text(a + b + c / 2, yi, pct(c), ha="center", va="center", fontsize=8, color=TXT,
                    fontweight="bold")
        ax.text(-0.015, yi, t, ha="right", va="center", fontsize=11, color=TXT)
        ax.text(1.015, yi, f"{cur[t]['rank']}e · {cur[t]['pts']} pts", ha="left", va="center",
                fontsize=10, color=MUTED)
    ax.set_xlim(0, 1)
    ax.set_ylim(-0.7, len(order) - 0.3)
    ax.axis("off")

    fig.text(0.05, 0.955, "LIGUE DES CHAMPIONS — SIMULATION", fontsize=24, fontweight="bold", va="center")
    fig.text(0.05, 0.925, f"Probabilités de qualification {_matchday_date_label()}", fontsize=13, color=MUTED,
             va="center")
    for k, (lab, col) in enumerate([("8es de finale directs (top 8)", C_TOP8),
                                    ("Barrages (9e-24e)", C_PLAY), ("Éliminé (25e-36e)", C_OUT)]):
        x = 0.20 + k * 0.23
        fig.patches.append(Rectangle((x, 0.893), 0.012, 0.011, transform=fig.transFigure, facecolor=col))
        fig.text(x + 0.018, 0.8985, lab, fontsize=10, color=TXT, va="center")
    fig.text(0.86, 0.905, "Classement actuel", fontsize=9, color=MUTED, ha="center")
    fig.text(0.05, 0.02, "Simulation Monte Carlo : Elo mis à jour après chaque match simulé + loi de Poisson.",
             fontsize=9, color=MUTED)
    fig.savefig(path, dpi=110, facecolor=BG)
    plt.close(fig)


def objectives_card(sim, objectives, path):
    """Carte "scénario" : probabilité de chaque objectif seul, et de TOUS ensemble."""
    labels, vals = [], []
    for team, r in objectives.items():
        txt = "dans le top 8" if r == 8 else f"dans le top {r}"
        labels.append(f"{team} {txt}")
        vals.append(s.prob_objectives(sim, {team: r}))
    joint = s.prob_objectives(sim, objectives)

    fig = _new_fig((12, 6.75))
    ax = fig.add_axes([0.30, 0.14, 0.60, 0.48], facecolor="none")
    all_labels = labels + ["Tous à la fois"]
    all_vals = vals + [joint]
    y = np.arange(len(all_labels))[::-1]
    cols = [C_TOP8] * len(vals) + [C_PLAY]
    ax.barh(y, all_vals, color=cols, height=0.55)
    for yi, v in zip(y, all_vals):
        ax.text(v + 0.015, yi, pct(v), va="center", fontsize=20, fontweight="bold", color=TXT)
    ax.set_xlim(0, 1.15)
    ax.set_yticks(y)
    ax.set_yticklabels(all_labels, fontsize=13, color=TXT)
    ax.set_xticks([])
    for sp in ax.spines.values():
        sp.set_visible(False)
    ax.tick_params(length=0)
    fig.text(0.07, 0.90, "LE SCÉNARIO", fontsize=30, fontweight="bold", va="center")
    fig.text(0.07, 0.835,
             f"Probabilité de chaque objectif en fin de phase de ligue  ·  {_matchday_date_label().capitalize()}",
             fontsize=11.5, color=MUTED, va="center")
    fig.text(0.07, 0.04, "Simulation Monte Carlo, modèle Elo + loi de Poisson. 'Tous à la fois' "
             "tient compte du fait que les résultats des équipes s'influencent.", fontsize=9, color=MUTED)
    fig.savefig(path, dpi=130, facecolor=BG)
    plt.close(fig)


def _draw_kpi_boxes(fig, boxes):
    """Dessine la rangée de 3 panneaux KPI dans le style plateau télé."""
    x0, w, gap = 0.07, 0.285, 0.0225
    for k, (title, sub, val_text, col) in enumerate(boxes):
        x = x0 + k * (w + gap)
        fig.patches.append(Rectangle((x, 0.67), w, 0.14, transform=fig.transFigure,
                                     facecolor=PANEL, edgecolor="none", zorder=1))
        fig.patches.append(Rectangle((x, 0.67), 0.006, 0.14, transform=fig.transFigure,
                                     facecolor=col, edgecolor="none", zorder=2))
        title_size = 10 if len(title) <= 22 else 8.5
        val_size = 24 if len(val_text) <= 8 else 19
        sub_size = 7.3 if len(sub) > 30 else 8.5
        fig.text(x + 0.02, 0.785, title, fontsize=title_size, color=MUTED, fontweight="bold", va="center")
        fig.text(x + 0.02, 0.732, val_text, fontsize=val_size, color=col, fontweight="bold", va="center")
        if sub:
            fig.text(x + w - 0.014, 0.688, sub, fontsize=sub_size, color=MUTED, ha="right", va="center")


def _style_bar_axes(ax):
    """Applique le style des axes (grille horizontale discrète, épines épurées)."""
    ax.grid(axis="y", color=TXT, alpha=0.12, linewidth=0.7, zorder=0)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    ax.spines["left"].set_color(MUTED)
    ax.spines["bottom"].set_color(MUTED)
    ax.tick_params(axis="x", length=0, labelsize=10)
    ax.tick_params(axis="y", length=0, colors=MUTED)


def team_points_card(team, sim, table, path, n_sims=None, qualifications=None):
    """Enregistre la distribution des points finaux d'une équipe."""
    if qualifications is None:
        qualifications = s.qualification_probs(sim)

    team_pts = sim["pts"][:, s.IDX[team]]
    n_sims = n_sims or sim["ranks"].shape[0]
    q = qualifications[team]
    cur = next(r for r in table if r["team"] == team)
    max_possible = cur["pts"] + 3 * sum(1 for h, a in sim["remaining"] if team in (h, a))

    dist = np.bincount(team_pts, minlength=25) / n_sims
    nonzero = np.where(dist > 0)[0]
    p_min = max(0, int(nonzero[0]) - 1) if len(nonzero) else 0
    p_max = min(24, int(nonzero[-1]) + 1) if len(nonzero) else 24
    pts_range = np.arange(p_min, p_max + 1)
    vals = 100 * dist[p_min:p_max + 1]

    p10, p90 = np.percentile(team_pts, [10, 90])

    # Couleurs cohérentes avec les encadrés KPI :
    # - vert-cyan (C_TOP8) = moyenne attendue (encadré + trait pointillé vertical) ;
    # - ambre (C_PLAY) = plage probable 80 % (encadré + zone et barres dans [p10, p90]) ;
    # - bleu-indigo doux = scénarios extrêmes hors de la plage probable.
    c_tail = "#5d73cc"
    c_neutral = "#8da4ff"
    bar_colors = [C_PLAY if (p10 <= p <= p90) else c_tail for p in pts_range]

    fig = _new_fig((12, 6.75))
    ax = fig.add_axes([0.07, 0.15, 0.88, 0.45], facecolor="none")

    ax.axvspan(p10 - 0.45, p90 + 0.45, color=C_PLAY, alpha=0.11, lw=0, zorder=1)
    ax.bar(pts_range, vals, color=bar_colors, width=0.72, zorder=3)
    ax.axvline(q["exp_pts"], color=C_TOP8, linestyle="--", linewidth=2.0, zorder=4)
    for p, v in zip(pts_range, vals):
        if v >= 2.5:
            ax.text(p, v + 0.6, f"{v:.1f}", ha="center", va="bottom", fontsize=8.5, color=TXT, zorder=5)

    ax.set_xlim(p_min - 0.6, p_max + 0.6)
    y_max = max(vals.max() * 1.25, 10)
    ax.set_ylim(0, y_max)
    ax.set_xticks(pts_range)
    y_step = 5 if y_max <= 25 else 10
    y_ticks = np.arange(0, y_max + 0.001, y_step)
    ax.set_yticks(y_ticks)
    ax.set_yticklabels([f"{v:.0f} %" for v in y_ticks], fontsize=8)
    _style_bar_axes(ax)
    ax.set_xlabel("Nombre de points en fin de phase de ligue", fontsize=10, labelpad=8)
    ax.set_ylabel("Probabilité", fontsize=10, labelpad=8)

    fig.text(0.07, 0.92, f"{team.upper()} — POINTS", fontsize=28, fontweight="bold", color=TXT, va="center")
    fig.text(
        0.07,
        0.855,
        f"Classement actuel : {cur['rank']}e  ·  {cur['pts']} pts  ·  diff {cur['gd']:+d}  ·  {_matchday_date_label().capitalize()}",
        fontsize=11.5,
        color=MUTED,
        va="center",
    )

    boxes = [
        ("POINTS MOYENS", f"Max : {max_possible} pts", f"{q['exp_pts']:.1f} pts", C_TOP8),
        ("PLAGE PROBABLE (80 % DES SCÉNARIOS)", "", f"{p10:.0f} - {p90:.0f} pts", C_PLAY),
        ("POINTS ACTUELS", "", f"{cur['pts']} pts", c_neutral),
    ]
    _draw_kpi_boxes(fig, boxes)

    # Légende alignée entre les encadrés KPI et le graphe pour lever toute ambiguïté visuelle.
    fig.lines.append(
        plt.Line2D([0.07, 0.095], [0.630, 0.630], transform=fig.transFigure,
                   color=C_TOP8, linestyle="--", linewidth=2.0)
    )
    fig.text(0.102, 0.630, f"Moyenne attendue ({q['exp_pts']:.1f} pts)", fontsize=9, color=TXT, va="center")
    fig.patches.append(Rectangle((0.365, 0.623), 0.012, 0.014, transform=fig.transFigure, facecolor=C_PLAY))
    fig.text(0.383, 0.630, f"Plage probable 80 % ({p10:.0f}-{p90:.0f} pts)", fontsize=9, color=TXT, va="center")
    fig.patches.append(Rectangle((0.685, 0.623), 0.012, 0.014, transform=fig.transFigure, facecolor=c_tail))
    fig.text(0.703, 0.630, "Scénarios extrêmes (20 %)", fontsize=9, color=TXT, va="center")

    fig.text(
        0.07,
        0.055,
        f"Top 8 : {pct(q['top8'])}   ·   Top 24 : {pct(q['top24'])}   ·   Élimination : {pct(q['out'])}",
        fontsize=9,
        color=MUTED,
        va="center",
    )
    fig.text(
        0.07,
        0.025,
        f"Monte Carlo : {n_sims:,} simulations · Modèle Elo + loi de Poisson".replace(",", " "),
        fontsize=8,
        color=MUTED,
        va="center",
    )
    fig.savefig(path, dpi=130, facecolor=BG)
    plt.close(fig)


def team_important_matches_card(team, sim, table, path, n_sims=None, importance=None):
    """Enregistre le Top 10 des matchs les plus importants pour une équipe."""
    if importance is None:
        importance = s.match_importance(sim)

    top_matches = importance[team][:10]
    cur = next(r for r in table if r["team"] == team)
    n_sims = n_sims or sim["ranks"].shape[0]

    ordered = list(reversed(top_matches))
    labels = [f"{m['home']} - {m['away']}" for m in ordered]
    vals = [m["importance"] for m in ordered]
    cols = [C_TOP8 if m["is_own"] else C_PLAY for m in ordered]

    fig = _new_fig((12, 6.75))
    ax = fig.add_axes([0.27, 0.14, 0.42, 0.63], facecolor="none")
    y = np.arange(len(labels))
    ax.barh(y, vals, color=cols, height=0.62, zorder=3)

    x_max = max(max(vals, default=1.0) * 1.08, 1.0)
    for yi, m, v in zip(y, ordered, vals):
        unit = "place" if round(v, 1) <= 1.0 else "places"
        txt = f"{v:.1f} {unit} (rang moyen : {m['worst_rank']:.1f}e → {m['best_rank']:.1f}e)"
        ax.text(v + x_max * 0.025, yi, txt, va="center", fontsize=9, color=TXT, fontweight="bold")

    ax.set_xlim(0, x_max)
    ax.set_ylim(-0.6, len(labels) - 0.4)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=10.5, color=TXT)
    ax.set_xticks([])
    for sp in ax.spines.values():
        sp.set_visible(False)
    ax.tick_params(length=0)

    fig.text(0.07, 0.92, f"{team.upper()} — MATCHS CLÉS", fontsize=26, fontweight="bold", color=TXT, va="center")
    fig.text(
        0.07,
        0.86,
        f"Top 10 des matchs décisifs  ·  Actuel : {cur['rank']}e ({cur['pts']} pts)  ·  {_matchday_date_label().capitalize()}",
        fontsize=11.5,
        color=MUTED,
        va="center",
    )

    for k, (lab, col) in enumerate([("Match de l'équipe", C_TOP8), ("Match d'autres équipes", C_PLAY)]):
        x = 0.27 + k * 0.25
        fig.patches.append(Rectangle((x, 0.795), 0.014, 0.016, transform=fig.transFigure, facecolor=col))
        fig.text(x + 0.02, 0.803, lab, fontsize=10, color=TXT, va="center")

    fig.text(
        0.07,
        0.055,
        "Plus grand écart de classement final moyen (en places) entre les 3 issues possibles du match (1 / N / 2).",
        fontsize=9,
        color=MUTED,
        va="center",
    )
    fig.text(
        0.07,
        0.025,
        f"Monte Carlo : {n_sims:,} simulations · Modèle Elo + loi de Poisson".replace(",", " "),
        fontsize=8,
        color=MUTED,
        va="center",
    )
    fig.savefig(path, dpi=130, facecolor=BG)
    plt.close(fig)


def points_thresholds_card(sim, path, n_sims=None):
    """Graphe global : probabilité de qualification (Top 8 / Barrages / Éliminé) selon le nombre de points."""
    n_sims = n_sims or sim["ranks"].shape[0]
    thresholds = s.points_thresholds(sim, positions=(8, 16, 24))
    by_pts = s.qualification_by_points(sim)
    pts_axis = np.arange(len(by_pts["total"]))

    # Fenêtre d'affichage centrée sur les totaux de points où les zones basculent,
    # encadrée par quelques barres sûres à 100 % éliminé à gauche et 100 % Top 8 à droite.
    valid = by_pts["total"] > 0
    mixed = valid & (
        ((by_pts["top8"] > 0.005) & (by_pts["top8"] < 0.995))
        | ((by_pts["playoff"] > 0.005) & (by_pts["playoff"] < 0.995))
        | ((by_pts["out"] > 0.005) & (by_pts["out"] < 0.995))
    )
    mixed_idx = np.where(mixed)[0]
    valid_idx = np.where(valid)[0]
    if len(mixed_idx):
        p_min = max(int(valid_idx[0]), int(mixed_idx[0]) - 2)
        p_max = min(int(valid_idx[-1]), int(mixed_idx[-1]) + 3)
    else:
        p_min, p_max = 6, 19
    x = np.arange(p_min, p_max + 1)

    p_top8 = 100.0 * by_pts["top8"][p_min:p_max + 1]
    p_play = 100.0 * by_pts["playoff"][p_min:p_max + 1]
    p_out = 100.0 * by_pts["out"][p_min:p_max + 1]

    fig = _new_fig((12, 6.75))
    ax = fig.add_axes([0.07, 0.14, 0.88, 0.45], facecolor="none")

    bar_w = 0.76
    ax.bar(x, p_top8, width=bar_w, color=C_TOP8, edgecolor=BG, linewidth=0.8, zorder=3)
    ax.bar(x, p_play, bottom=p_top8, width=bar_w, color=C_PLAY, edgecolor=BG, linewidth=0.8, zorder=3)
    ax.bar(x, p_out, bottom=p_top8 + p_play, width=bar_w, color=C_OUT, edgecolor=BG, linewidth=0.8, zorder=3)

    # Affiche les pourcentages (1 décimale) uniquement sur les segments intermédiaires lisibles.
    for xi, a, b, c in zip(x, p_top8, p_play, p_out):
        for val, bottom, text_col in (
            (a, 0.0, INK),
            (b, a, INK),
            (c, a + b, TXT),
        ):
            if 4.0 <= val <= 98.5:
                fs = 7.5 if val < 6.5 else 8.5
                ax.text(
                    xi,
                    bottom + val / 2.0,
                    f"{val:.1f}",
                    ha="center",
                    va="center",
                    fontsize=fs,
                    fontweight="bold",
                    color=text_col,
                    zorder=4,
                )

    ax.set_xlim(p_min - 0.65, p_max + 0.65)
    ax.set_ylim(0, 100)
    ax.set_xticks(x)
    y_ticks = np.arange(0, 101, 20)
    ax.set_yticks(y_ticks)
    ax.set_yticklabels([f"{v:.0f} %" for v in y_ticks], fontsize=8.5)
    _style_bar_axes(ax)
    ax.set_xlabel("Nombre de points en fin de phase de ligue", fontsize=10, labelpad=8)
    ax.set_ylabel("Probabilité (%)", fontsize=10, labelpad=8)

    fig.text(0.07, 0.92, "SEUILS DE QUALIFICATION — PROBABILITÉ PAR POINTS", fontsize=24, fontweight="bold", color=TXT, va="center")
    fig.text(
        0.07,
        0.855,
        f"Issue finale selon le nombre de points  ·  {_matchday_date_label().capitalize()}",
        fontsize=12,
        color=MUTED,
        va="center",
    )

    kpis = []
    for pos, label, col in (
        (8, "TOP 8 (8E PLACE)", C_TOP8),
        (16, "TOP 16 (16E PLACE)", C_PLAY),
        (24, "TOP 24 (24E PLACE)", C_OUT),
    ):
        dist = thresholds[pos]
        mean_p = float(np.sum(pts_axis * dist))
        mode_p = int(np.argmax(dist))
        kpis.append((label, f"Seuil le plus fréquent : {mode_p} pts", f"{mean_p:.1f} pts", col))
    _draw_kpi_boxes(fig, kpis)

    legend_items = [
        ("Qualification directe (Top 8)", C_TOP8),
        ("Barrages (9e-24e)", C_PLAY),
        ("Éliminé (25e-36e)", C_OUT),
    ]
    for k, (label, col) in enumerate(legend_items):
        lx = 0.07 + k * 0.28
        fig.patches.append(Rectangle((lx, 0.622), 0.012, 0.014, transform=fig.transFigure, facecolor=col))
        fig.text(lx + 0.018, 0.629, label, fontsize=9.5, color=TXT, va="center")

    fig.text(
        0.07,
        0.025,
        f"Monte Carlo : {n_sims:,} simulations · Modèle Elo + loi de Poisson".replace(",", " "),
        fontsize=8,
        color=MUTED,
        va="center",
    )
    fig.savefig(path, dpi=130, facecolor=BG)
    plt.close(fig)


def position_points_card(position, sim, path, n_sims=None, pts_by_rank=None):
    """Enregistre la distribution du nombre de points du club classé à la place `position` (1..36)."""
    if pts_by_rank is None:
        pts_by_rank = s.points_by_position(sim)

    pos_pts = pts_by_rank[:, position - 1]
    n_sims = n_sims or sim["ranks"].shape[0]
    dist = np.bincount(pos_pts, minlength=25) / n_sims

    nonzero = np.where(dist > 0)[0]
    p_min = max(0, int(nonzero[0]) - 1) if len(nonzero) else 0
    p_max = min(24, int(nonzero[-1]) + 1) if len(nonzero) else 24
    pts_range = np.arange(p_min, p_max + 1)
    vals = 100.0 * dist[p_min:p_max + 1]

    mean_p = float(np.mean(pos_pts))
    mode_p = int(np.argmax(dist))
    p10, p90 = np.percentile(pos_pts, [10, 90])

    pos_label = "1re" if position == 1 else f"{position}e"
    pos_title = "1RE" if position == 1 else f"{position}E"
    if position <= 8:
        zone_label = "Qualification directe (Top 8)"
    elif position <= 16:
        zone_label = "Barrages — Tête de série (9e-16e)"
    elif position <= 24:
        zone_label = "Barrages — Non tête de série (17e-24e)"
    else:
        zone_label = f"Élimination (25e-{s.N_TEAMS}e)"

    # Même code couleur cohérent que team_points_card :
    # vert-cyan = moyenne, ambre = plage probable 80 %, bleu-indigo doux = extrêmes 20 %.
    c_tail = "#5d73cc"
    bar_colors = [C_PLAY if (p10 <= p <= p90) else c_tail for p in pts_range]

    fig = _new_fig((12, 6.75))
    ax = fig.add_axes([0.07, 0.15, 0.88, 0.45], facecolor="none")

    ax.axvspan(p10 - 0.45, p90 + 0.45, color=C_PLAY, alpha=0.11, lw=0, zorder=1)
    ax.bar(pts_range, vals, color=bar_colors, width=0.72, zorder=3)
    ax.axvline(mean_p, color=C_TOP8, linestyle="--", linewidth=2.0, zorder=4)
    for p, v in zip(pts_range, vals):
        if v >= 2.5:
            ax.text(p, v + 0.6, f"{v:.1f}", ha="center", va="bottom", fontsize=8.5, color=TXT, zorder=5)

    ax.set_xlim(p_min - 0.6, p_max + 0.6)
    y_max = max(vals.max() * 1.25, 10)
    ax.set_ylim(0, y_max)
    ax.set_xticks(pts_range)
    y_step = 5 if y_max <= 25 else 10
    y_ticks = np.arange(0, y_max + 0.001, y_step)
    ax.set_yticks(y_ticks)
    ax.set_yticklabels([f"{v:.0f} %" for v in y_ticks], fontsize=8)
    _style_bar_axes(ax)
    ax.set_xlabel(f"Nombre de points du club classé {pos_label} en fin de phase de ligue", fontsize=10, labelpad=8)
    ax.set_ylabel("Probabilité", fontsize=10, labelpad=8)

    fig.text(0.07, 0.92, f"{pos_title} PLACE — DISTRIBUTION DES POINTS", fontsize=25, fontweight="bold", color=TXT, va="center")
    fig.text(
        0.07,
        0.855,
        f"{zone_label}  ·  {_matchday_date_label().capitalize()}",
        fontsize=12,
        color=MUTED,
        va="center",
    )

    boxes = [
        ("POINTS MOYENS", f"Place n°{position} / {s.N_TEAMS}", f"{mean_p:.1f} pts", C_TOP8),
        ("PLAGE PROBABLE (80 % DES SCÉNARIOS)", "", f"{p10:.0f} - {p90:.0f} pts", C_PLAY),
        ("SCORE LE PLUS FRÉQUENT", f"Probabilité : {pct(dist[mode_p])}", f"{mode_p} pts", _zone_color(position)),
    ]
    _draw_kpi_boxes(fig, boxes)

    fig.lines.append(
        plt.Line2D([0.07, 0.095], [0.630, 0.630], transform=fig.transFigure,
                   color=C_TOP8, linestyle="--", linewidth=2.0)
    )
    fig.text(0.102, 0.630, f"Moyenne attendue ({mean_p:.1f} pts)", fontsize=9, color=TXT, va="center")
    fig.patches.append(Rectangle((0.365, 0.623), 0.012, 0.014, transform=fig.transFigure, facecolor=C_PLAY))
    fig.text(0.383, 0.630, f"Plage probable 80 % ({p10:.0f}-{p90:.0f} pts)", fontsize=9, color=TXT, va="center")
    fig.patches.append(Rectangle((0.685, 0.623), 0.012, 0.014, transform=fig.transFigure, facecolor=c_tail))
    fig.text(0.703, 0.630, "Scénarios extrêmes (20 %)", fontsize=9, color=TXT, va="center")

    fig.text(
        0.07,
        0.025,
        f"Monte Carlo : {n_sims:,} simulations · Modèle Elo + loi de Poisson".replace(",", " "),
        fontsize=8,
        color=MUTED,
        va="center",
    )
    fig.savefig(path, dpi=130, facecolor=BG)
    plt.close(fig)
