"""
Visuels de la simulation (style "plateau télé" : fond sombre, gros chiffres, trois zones de couleur).
Zones : top 8 = qualifié direct, 9-24 = barrages, 25-36 = éliminé.
"""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Rectangle

import ldc_sim as s

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
    """Pourcentage lisible : '<1 %' pour les très faibles probabilités, '>99 %' pour les très fortes."""
    p = 100 * x
    if p < 0.5:
        return "<1 %" if p > 0 else "0 %"
    if p > 99.5:
        return ">99 %" if p < 100 else "100 %"
    return f"{p:.0f} %"


def team_card(team, sim, table, path, n_sims=None):
    """Carte d'une équipe : probabilité de finir à chaque place + 3 chiffres clés."""
    dist = s.rank_distribution(sim)[s.IDX[team]]
    q = s.qualification_probs(sim)[team]
    cur = next(r for r in table if r["team"] == team)
    n_sims = n_sims or sim["ranks"].shape[0]

    fig = _new_fig((12, 6.75))
    ax = fig.add_axes([0.07, 0.15, 0.88, 0.47], facecolor="none")

    places = np.arange(1, 37)
    ax.axvspan(0.5, 8.5, color=C_TOP8, alpha=0.10, lw=0)
    ax.axvspan(8.5, 24.5, color=C_PLAY, alpha=0.07, lw=0)
    ax.axvspan(24.5, 36.5, color=C_OUT, alpha=0.10, lw=0)
    ax.bar(places, 100 * dist, color=[_zone_color(p) for p in places], width=0.72, zorder=3)
    for p, v in zip(places, dist):
        if v >= 0.03:
            ax.text(p, 100 * v + 0.6, f"{100 * v:.0f}", ha="center", va="bottom", fontsize=9,
                    color=TXT, zorder=4)
    ax.set_xlim(0.5, 36.5)
    ax.set_ylim(0, max(100 * dist.max() * 1.25, 10))
    ax.set_xticks([1, 4, 8, 12, 16, 20, 24, 28, 32, 36])
    ax.set_yticks([])
    for sp in ("top", "right", "left"):
        ax.spines[sp].set_visible(False)
    ax.spines["bottom"].set_color(MUTED)
    ax.tick_params(axis="x", length=0, labelsize=10)
    ax.set_xlabel("Place finale au classement de la phase de ligue", fontsize=10, labelpad=8)

    # En-tête
    fig.text(0.07, 0.92, team.upper(), fontsize=30, fontweight="bold", color=TXT, va="center")
    fig.text(0.07, 0.855,
             f"Aujourd'hui : {cur['rank']}e  ·  {cur['pts']} pts  ·  diff. {cur['gd']:+d}   |   "
             f"Après la J4, avant la J5",
             fontsize=12, color=MUTED, va="center")

    # Trois indicateurs
    boxes = [("8es DE FINALE DIRECTS", "Top 8", q["top8"], C_TOP8),
             ("BARRAGES", "Places 9 à 24", q["playoff"], C_PLAY),
             ("ÉLIMINÉ", "Places 25 à 36", q["out"], C_OUT)]
    x0, w, gap = 0.07, 0.285, 0.0225
    for k, (title, sub, val, col) in enumerate(boxes):
        x = x0 + k * (w + gap)
        fig.patches.append(Rectangle((x, 0.67), w, 0.14, transform=fig.transFigure,
                                     facecolor=PANEL, edgecolor="none", zorder=1))
        fig.patches.append(Rectangle((x, 0.67), 0.006, 0.14, transform=fig.transFigure,
                                     facecolor=col, edgecolor="none", zorder=2))
        fig.text(x + 0.02, 0.785, title, fontsize=10, color=MUTED, fontweight="bold", va="center")
        fig.text(x + 0.02, 0.715, pct(val), fontsize=30, color=col, fontweight="bold", va="center")
        fig.text(x + w - 0.015, 0.70, sub, fontsize=10, color=MUTED, ha="right", va="center")

    fig.text(0.07, 0.035,
             f"Points finaux attendus : {q['exp_pts']:.1f}   ·   Simulation Monte Carlo ({n_sims:,} tirages), "
             f"Elo mis à jour après chaque match simulé + loi de Poisson".replace(",", " "),
             fontsize=9, color=MUTED, va="center")
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
        if a >= 0.06:
            ax.text(a / 2, yi, pct(a), ha="center", va="center", fontsize=9, color=INK, fontweight="bold")
        if b >= 0.08:
            ax.text(a + b / 2, yi, pct(b), ha="center", va="center", fontsize=9, color=INK, fontweight="bold")
        if c >= 0.06:
            ax.text(a + b + c / 2, yi, pct(c), ha="center", va="center", fontsize=9, color=TXT,
                    fontweight="bold")
        ax.text(-0.015, yi, t, ha="right", va="center", fontsize=11, color=TXT)
        ax.text(1.015, yi, f"{cur[t]['rank']}e · {cur[t]['pts']} pts", ha="left", va="center",
                fontsize=10, color=MUTED)
    ax.set_xlim(0, 1)
    ax.set_ylim(-0.7, len(order) - 0.3)
    ax.axis("off")

    fig.text(0.05, 0.955, "LIGUE DES CHAMPIONS 2026-27", fontsize=24, fontweight="bold", va="center")
    fig.text(0.05, 0.925, "Qui se qualifie ? Probabilités après la 4e journée", fontsize=13, color=MUTED,
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
    fig.text(0.07, 0.835, "Probabilité que chaque objectif soit atteint à la fin de la phase de ligue",
             fontsize=12, color=MUTED, va="center")
    fig.text(0.07, 0.04, "Simulation Monte Carlo, modèle Elo + loi de Poisson. 'Tous à la fois' "
             "tient compte du fait que les résultats des équipes s'influencent.", fontsize=9, color=MUTED)
    fig.savefig(path, dpi=130, facecolor=BG)
    plt.close(fig)
