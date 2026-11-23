const state = {
  sources: [],
  activeSource: "clubelo",
  outputFolder: "clubelo",
  available: true,
  matchday: 4,
  totalMatchdays: 8,
  teams: [],
  played: [],
  remaining: [],
  defaultElo: {},
  manualElo: {},
  selectedTeam: "PSG",
  selectedRankPos: 8,
  duelA: "PSG",
  duelB: "Bayern",
  activeChart: "classement",
  tableFilter: "all",
  sortKey: "exp_pts",
  sortDesc: true,
  calMode: "remaining",
  calClub: "",
  cacheBust: Date.now(),
};

const frenchClubs = new Set(["PSG", "Lille", "Lens"]);

const chartDescriptions = {
  classement: "Probabilité pour le club de terminer à chacune des 36 places finales, de la 36e place à gauche jusqu'à la 1re place à droite (rose : élimination, jaune : barrages, vert : Top 8 direct).",
  points: "Distribution du total de points en fin de phase de ligue. Le trait pointillé vert indique la moyenne attendue et les barres jaunes représentent la plage probable (80 % des scénarios).",
  matchs_cles: "Les 10 rencontres à venir (parmi tous les matchs de la compétition) qui créent le plus grand écart de classement final moyen pour le club selon leur issue (1 / N / 2).",
  all: "Vue complète réunissant les trois graphiques du club côte à côte.",
};

function pct(val) {
  const p = val * 100;
  if (p === 0) return "0.0 %";
  if (p < 0.05) return "<0.1 %";
  if (p === 100) return "100.0 %";
  if (p > 99.95) return ">99.9 %";
  return `${p.toFixed(1)} %`;
}

function setStatus(msg, kind = "") {
  const el = document.getElementById("status-bar");
  el.textContent = msg;
  el.className = "toast-status" + (kind ? ` ${kind}` : "");
}

function openLightbox(src) {
  const lb = document.getElementById("lightbox");
  document.getElementById("lightbox-img").src = src;
  lb.classList.add("open");
}

function navigateTo(pageId) {
  document.querySelectorAll("#main-nav .nav-tab").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.page === pageId);
  });
  document.querySelectorAll(".page-view").forEach(sec => {
    sec.classList.toggle("active", sec.id === pageId);
  });
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function selectClubAndOpen(teamName) {
  state.selectedTeam = teamName;
  renderClubExplorer();
  navigateTo("page-club");
}

async function loadState(source = null) {
  const query = source ? `?source=${encodeURIComponent(source)}` : "";
  const res = await fetch(`/api/state${query}`);
  const data = await res.json();

  state.sources = data.sources;
  state.activeSource = data.active_source;
  state.outputFolder = data.output_folder;
  state.available = data.available;
  state.matchday = data.matchday ?? 4;
  state.totalMatchdays = data.total_matchdays ?? 8;
  state.teams = data.teams || [];

  const brandSub = document.getElementById("brand-matchday-sub");
  if (brandSub) {
    brandSub.textContent = `Saison 2026-2027 · Projections après la ${state.matchday}e journée`;
  }
  const thRank = document.getElementById("th-cur-rank");
  if (thRank) {
    thRank.textContent = `Rang J${state.matchday}`;
  }
  state.played = data.played || [];
  state.remaining = data.remaining || [];
  state.defaultElo = data.default_elo || {};
  state.manualElo = { ...(data.manual_elo || {}) };

  if (state.teams.length > 0 && !state.teams.some(t => t.team === state.selectedTeam)) {
    state.selectedTeam = state.teams[0].team;
  }

  const toggleBtn = document.getElementById("toggle-manual-editor");
  const drawer = document.getElementById("manual-editor-drawer");
  if (state.activeSource === "manual") {
    toggleBtn.style.display = "inline-block";
  } else {
    toggleBtn.style.display = "none";
    drawer.classList.remove("open");
  }

  renderSourceButtons();
  renderManualEditor();
  renderHomeTiers();
  renderFrenchFocus();
  renderClubExplorer();
  renderStandingsPage();
  renderDuelSelectors();
  renderDuelPage();
  renderCalendarFilter();
  renderCalendar();
}

function renderSourceButtons() {
  const box = document.getElementById("source-buttons");
  box.innerHTML = "";
  for (const src of state.sources) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "pill-btn" + (src.id === state.activeSource ? " active" : "");
    btn.textContent = src.label;
    btn.onclick = () => {
      setStatus("");
      loadState(src.id);
    };
    box.appendChild(btn);
  }
}

function renderManualEditor() {
  const grid = document.getElementById("elo-inputs-grid");
  const filter = (document.getElementById("elo-editor-search").value || "").toLowerCase();
  const clubs = Object.keys(state.defaultElo).sort((a, b) => a.localeCompare(b, "fr"));

  grid.innerHTML = clubs
    .filter(c => c.toLowerCase().includes(filter))
    .map(club => {
      const val = state.manualElo[club] ?? state.defaultElo[club];
      const isMod = val !== state.defaultElo[club];
      return `
        <div class="elo-input-item ${isMod ? "modified" : ""}" data-club-box="${club}">
          <label title="${club} (Défaut : ${state.defaultElo[club]})">${club}</label>
          <input type="number" min="500" max="3000" step="1" value="${val}" data-club-elo="${club}">
        </div>
      `;
    })
    .join("");

  grid.querySelectorAll("input[data-club-elo]").forEach(inp => {
    inp.oninput = () => {
      const club = inp.dataset.clubElo;
      const num = parseInt(inp.value, 10);
      if (!Number.isNaN(num)) {
        state.manualElo[club] = num;
      }
      const box = inp.closest(".elo-input-item");
      box.classList.toggle("modified", num !== state.defaultElo[club]);
    };
  });
}

function renderHomeTiers() {
  const box = document.getElementById("tiers-container");
  if (!state.available || state.teams.length === 0) {
    box.innerHTML = "";
    return;
  }

  const byTop1 = [...state.teams].sort((a, b) => b.top1 - a.top1).slice(0, 3);
  const byTop8Border = [...state.teams]
    .sort((a, b) => Math.abs(a.top8 - 0.5) - Math.abs(b.top8 - 0.5))
    .slice(0, 3);
  const byTop16Border = [...state.teams]
    .sort((a, b) => Math.abs(a.top16 - 0.5) - Math.abs(b.top16 - 0.5))
    .slice(0, 3);
  const byTop24Border = [...state.teams]
    .sort((a, b) => Math.abs(a.top24 - 0.5) - Math.abs(b.top24 - 0.5))
    .slice(0, 3);

  const cards = [
    {
      cls: "",
      badge: "1re place",
      title: "Les grands favoris",
      explain: "Les clubs ayant la plus forte probabilité de terminer en tête de la phase de ligue.",
      items: byTop1.map(t => ({
        team: t.team,
        meta: `Actuel : ${t.cur_rank}e (${t.cur_pts} pts) · Proj. : ${t.exp_pts.toFixed(1)} pts`,
        stat: pct(t.top1),
      })),
    },
    {
      cls: "",
      badge: "Top 8 — Qualification directe",
      title: "La bataille pour le Top 8",
      explain: "Les équipes au coude-à-coude autour de la 8e place qualificative directe (~16 pts).",
      items: byTop8Border.map(t => ({
        team: t.team,
        meta: `Actuel : ${t.cur_rank}e (${t.cur_pts} pts) · Proj. : ${t.exp_pts.toFixed(1)} pts`,
        stat: pct(t.top8),
      })),
    },
    {
      cls: "play",
      badge: "Top 16 — Milieu de tableau",
      title: "Au cœur du peloton",
      explain: "Les équipes à la lutte autour de la 16e place (~12 pts).",
      items: byTop16Border.map(t => ({
        team: t.team,
        meta: `Actuel : ${t.cur_rank}e (${t.cur_pts} pts) · Proj. : ${t.exp_pts.toFixed(1)} pts`,
        stat: pct(t.top16),
      })),
    },
    {
      cls: "out",
      badge: "Top 24 — Qualification aux barrages",
      title: "Sur le fil du rasoir",
      explain: "Les clubs dont le destin bascule entre la qualification en barrages (24e) et l'élimination (~9 pts).",
      items: byTop24Border.map(t => ({
        team: t.team,
        meta: `Actuel : ${t.cur_rank}e (${t.cur_pts} pts) · Proj. : ${t.exp_pts.toFixed(1)} pts`,
        stat: pct(t.top24),
      })),
    },
  ];

  box.innerHTML = cards
    .map(c => `
      <div class="tier-card ${c.cls}">
        <div class="tier-head">
          <span class="tier-badge">${c.badge}</span>
          <div class="tier-title">${c.title}</div>
        </div>
        <p class="tier-explain">${c.explain}</p>
        <div class="club-mini-list">
          ${c.items
            .map(it => `
              <button type="button" class="club-mini-item" data-team="${it.team}">
                <div>
                  <div class="club-mini-name">${it.team}</div>
                  <div class="club-mini-meta">${it.meta}</div>
                </div>
                <div class="club-mini-stat">${it.stat}</div>
              </button>
            `)
            .join("")}
        </div>
      </div>
    `)
    .join("");

  box.querySelectorAll(".club-mini-item").forEach(btn => {
    btn.onclick = () => selectClubAndOpen(btn.dataset.team);
  });
}

function renderFrenchFocus() {
  const box = document.getElementById("french-container");
  const frTeams = state.teams.filter(t => frenchClubs.has(t.team));
  box.innerHTML = frTeams
    .map(t => `
      <div class="fr-card" data-team="${t.team}">
        <div class="fr-card-top">
          <div>
            <div class="fr-club-name">${t.team}</div>
            <div class="club-mini-meta">Classement J${state.matchday} : ${t.cur_rank}e (${t.cur_pts} pts, diff. ${t.cur_gd >= 0 ? "+" : ""}${t.cur_gd})</div>
          </div>
          <span class="tier-badge">${t.exp_pts.toFixed(1)} pts attendus</span>
        </div>
        <div class="fr-kpis">
          <div>
            <div class="fr-kpi-val" style="color: var(--top8);">${pct(t.top8)}</div>
            <div class="fr-kpi-lab">Top 8 direct</div>
          </div>
          <div>
            <div class="fr-kpi-val" style="color: var(--play);">${pct(t.playoff)}</div>
            <div class="fr-kpi-lab">Barrages</div>
          </div>
          <div>
            <div class="fr-kpi-val" style="color: var(--out);">${pct(t.out)}</div>
            <div class="fr-kpi-lab">Élimination</div>
          </div>
        </div>
      </div>
    `)
    .join("");

  box.querySelectorAll(".fr-card").forEach(card => {
    card.onclick = () => selectClubAndOpen(card.dataset.team);
  });
}

function renderClubExplorer() {
  const searchVal = (document.getElementById("club-search").value || "").toLowerCase();
  const sideList = document.getElementById("club-sidebar-list");

  const visibleTeams = state.teams.filter(t => t.team.toLowerCase().includes(searchVal));
  sideList.innerHTML = visibleTeams
    .map(t => `
      <button type="button" class="club-side-btn ${t.team === state.selectedTeam ? "active" : ""}" data-team="${t.team}">
        <span>${t.team}</span>
        <span style="opacity: 0.78; font-size: 0.8rem;">${t.exp_pts.toFixed(1)} pts</span>
      </button>
    `)
    .join("");

  sideList.querySelectorAll(".club-side-btn").forEach(btn => {
    btn.onclick = () => {
      state.selectedTeam = btn.dataset.team;
      renderClubExplorer();
    };
  });

  const club = state.teams.find(t => t.team === state.selectedTeam) || state.teams[0];
  if (!club) return;

  document.getElementById("club-title").textContent = club.team;
  const gdSign = club.cur_gd >= 0 ? "+" : "";
  document.getElementById("club-subtitle").textContent =
    `Situation après ${state.matchday} journées : ${club.cur_rank}e place · ${club.cur_pts} points · Différence de buts ${gdSign}${club.cur_gd} (${club.cur_gf} BP, ${club.cur_ga} BC)`;

  document.getElementById("club-kpis").innerHTML = `
    <div class="stat-tile">
      <div class="stat-tile-label">8es de finale directs (Top 8)</div>
      <div class="stat-tile-val" style="color: var(--top8);">${pct(club.top8)}</div>
    </div>
    <div class="stat-tile play">
      <div class="stat-tile-label">Barrages (Places 9 à 24)</div>
      <div class="stat-tile-val" style="color: var(--play);">${pct(club.playoff)}</div>
    </div>
    <div class="stat-tile out">
      <div class="stat-tile-label">Élimination (25e à 36e)</div>
      <div class="stat-tile-val" style="color: var(--out);">${pct(club.out)}</div>
    </div>
    <div class="stat-tile">
      <div class="stat-tile-label">Total de points projeté</div>
      <div class="stat-tile-val">${club.exp_pts.toFixed(1)} pts</div>
    </div>
  `;

  document.getElementById("club-chart-caption").textContent = chartDescriptions[state.activeChart];

  const base = `/outputs/${state.outputFolder}/equipes/${club.slug}`;
  const q = `?t=${state.cacheBust}`;
  const display = document.getElementById("club-chart-display");

  if (state.activeChart === "all") {
    display.innerHTML = `
      <div class="triple-chart-grid">
        <img src="${base}/classement.png${q}" alt="Classement ${club.team}" onclick="openLightbox(this.src)">
        <img src="${base}/points.png${q}" alt="Points ${club.team}" onclick="openLightbox(this.src)">
        <img src="${base}/matchs_cles.png${q}" alt="Matchs clés ${club.team}" onclick="openLightbox(this.src)">
      </div>
    `;
  } else {
    const src = `${base}/${state.activeChart}.png${q}`;
    display.innerHTML = `
      <div class="single-chart-wrap">
        <img src="${src}" alt="${state.activeChart} ${club.team}" onclick="openLightbox(this.src)">
      </div>
    `;
  }
}

function renderRankPointsChart() {
  const sel = document.getElementById("rank-pos-select");
  if (sel && sel.options.length === 0) {
    sel.innerHTML = Array.from({ length: 36 }, (_, i) => {
      const p = i + 1;
      const label = p === 1 ? "1re place" : `${p}e place`;
      return `<option value="${p}">${label}</option>`;
    }).join("");
  }
  if (sel) sel.value = String(state.selectedRankPos);

  document.querySelectorAll("#rank-pos-shortcuts [data-rank-pos]").forEach(btn => {
    btn.classList.toggle("active", parseInt(btn.dataset.rankPos, 10) === state.selectedRankPos);
  });

  const img = document.getElementById("img-rank-points");
  if (img) {
    img.src = `/outputs/${state.outputFolder}/classements/${state.selectedRankPos}.png?t=${state.cacheBust}`;
    img.onclick = () => openLightbox(img.src);
  }
}

function renderStandingsPage() {
  const q = `?t=${state.cacheBust}`;
  const ovImg = document.getElementById("img-global-overview");
  const thImg = document.getElementById("img-global-thresholds");
  ovImg.src = `/outputs/${state.outputFolder}/classement_global.png${q}`;
  thImg.src = `/outputs/${state.outputFolder}/seuils_points_top_8_16_24.png${q}`;
  ovImg.onclick = () => openLightbox(ovImg.src);
  thImg.onclick = () => openLightbox(thImg.src);
  renderRankPointsChart();

  const filtered = state.teams.filter(t => {
    if (state.tableFilter === "top8") return t.top8 >= 0.5;
    if (state.tableFilter === "playoff") return t.playoff >= 0.4;
    if (state.tableFilter === "out") return t.out >= 0.4;
    if (state.tableFilter === "fr") return frenchClubs.has(t.team);
    return true;
  });

  const key = state.sortKey;
  const mult = state.sortDesc ? -1 : 1;
  filtered.sort((a, b) => {
    if (key === "team") return mult * a.team.localeCompare(b.team, "fr");
    return mult * ((a[key] || 0) - (b[key] || 0));
  });

  const tbody = document.getElementById("teams-tbody");
  tbody.innerHTML = filtered
    .map(t => {
      const gdSign = t.cur_gd >= 0 ? "+" : "";
      return `
        <tr data-team="${t.team}">
          <td class="num"><strong>${t.cur_rank}e</strong></td>
          <td><strong>${t.team}</strong></td>
          <td class="num">${t.cur_pts} pts <span style="color: var(--muted);">(${gdSign}${t.cur_gd})</span></td>
          <td class="num">${pct(t.top1)}</td>
          <td class="num" style="color: var(--top8); font-weight: 700;">${pct(t.top8)}</td>
          <td class="num" style="color: var(--play); font-weight: 700;">${pct(t.playoff)}</td>
          <td class="num" style="color: var(--out); font-weight: 700;">${pct(t.out)}</td>
          <td class="num"><strong>${t.exp_pts.toFixed(1)} pts</strong></td>
          <td class="num">
            <div class="bar-stack">
              <div class="seg-top8" style="width:${(t.top8 * 100).toFixed(1)}%"></div>
              <div class="seg-play" style="width:${(t.playoff * 100).toFixed(1)}%"></div>
              <div class="seg-out" style="width:${(t.out * 100).toFixed(1)}%"></div>
            </div>
          </td>
        </tr>
      `;
    })
    .join("");

  tbody.querySelectorAll("tr[data-team]").forEach(row => {
    row.onclick = () => selectClubAndOpen(row.dataset.team);
  });
}

function renderDuelSelectors() {
  const selA = document.getElementById("duel-club-a");
  const selB = document.getElementById("duel-club-b");
  const names = [...state.teams].map(t => t.team).sort((a, b) => a.localeCompare(b, "fr"));
  const opts = names.map(n => `<option value="${n}">${n}</option>`).join("");
  selA.innerHTML = opts;
  selB.innerHTML = opts;
  if (names.includes(state.duelA)) selA.value = state.duelA;
  if (names.includes(state.duelB)) selB.value = state.duelB;
}

function renderDuelPage() {
  const a = state.teams.find(t => t.team === state.duelA) || state.teams[0];
  const b = state.teams.find(t => t.team === state.duelB) || state.teams[1] || state.teams[0];
  if (!a || !b) return;

  const tbl = document.getElementById("duel-summary-table");
  tbl.innerHTML = `
    <table class="duel-Comp-table">
      <thead>
        <tr>
          <th>${a.team}</th>
          <th>Indicateur</th>
          <th>${b.team}</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td><strong>${a.cur_rank}e (${a.cur_pts} pts)</strong></td>
          <td style="color: var(--muted);">Classement actuel (J${state.matchday})</td>
          <td><strong>${b.cur_rank}e (${b.cur_pts} pts)</strong></td>
        </tr>
        <tr>
          <td style="color: var(--top8); font-weight: 700;">${pct(a.top8)}</td>
          <td style="color: var(--muted);">Qualification directe (Top 8)</td>
          <td style="color: var(--top8); font-weight: 700;">${pct(b.top8)}</td>
        </tr>
        <tr>
          <td style="color: var(--play); font-weight: 700;">${pct(a.playoff)}</td>
          <td style="color: var(--muted);">Barrages (Places 9 à 24)</td>
          <td style="color: var(--play); font-weight: 700;">${pct(b.playoff)}</td>
        </tr>
        <tr>
          <td style="color: var(--out); font-weight: 700;">${pct(a.out)}</td>
          <td style="color: var(--muted);">Élimination (Places 25 à 36)</td>
          <td style="color: var(--out); font-weight: 700;">${pct(b.out)}</td>
        </tr>
        <tr>
          <td><strong>${a.exp_pts.toFixed(1)} pts</strong></td>
          <td style="color: var(--muted);">Points finaux attendus</td>
          <td><strong>${b.exp_pts.toFixed(1)} pts</strong></td>
        </tr>
      </tbody>
    </table>
  `;

  const q = `?t=${state.cacheBust}`;
  document.getElementById("duel-charts").innerHTML = `
    <div>
      <img src="/outputs/${state.outputFolder}/equipes/${a.slug}/classement.png${q}" alt="${a.team}" onclick="openLightbox(this.src)">
    </div>
    <div>
      <img src="/outputs/${state.outputFolder}/equipes/${b.slug}/classement.png${q}" alt="${b.team}" onclick="openLightbox(this.src)">
    </div>
  `;
}

function renderCalendarFilter() {
  const sel = document.getElementById("calendar-club-filter");
  const currentVal = sel.value;
  const names = [...state.teams].map(t => t.team).sort((a, b) => a.localeCompare(b, "fr"));
  sel.innerHTML = `<option value="">Tous les clubs (36)</option>` +
    names.map(n => `<option value="${n}">${n}</option>`).join("");
  sel.value = currentVal;
}

function renderCalendar() {
  const box = document.getElementById("calendar-list");
  const list = state.calMode === "played" ? state.played : state.remaining;
  const filtered = list.filter(m => !state.calClub || m.home === state.calClub || m.away === state.calClub);

  box.innerHTML = filtered
    .map(m => {
      const right = state.calMode === "played"
        ? `<span class="match-score">${m.hg} - ${m.ag}</span>`
        : `<span class="tier-badge">À venir</span>`;
      return `
        <div class="match-pill">
          <div>
            <span class="match-j">J${m.matchday}</span>
            <strong>${m.home}</strong> - ${m.away}
          </div>
          ${right}
        </div>
      `;
    })
    .join("");
}

/* Écouteurs d'événements */
document.querySelectorAll("#main-nav .nav-tab").forEach(btn => {
  btn.onclick = () => navigateTo(btn.dataset.page);
});

document.getElementById("toggle-manual-editor").onclick = () => {
  document.getElementById("manual-editor-drawer").classList.toggle("open");
};

document.getElementById("elo-editor-search").oninput = () => renderManualEditor();

document.getElementById("reset-default-elo-btn").onclick = async () => {
  const res = await fetch("/api/reset-manual", { method: "POST" });
  const data = await res.json();
  if (data.ok) {
    state.manualElo = { ...data.manual_elo };
    renderManualEditor();
    setStatus("Valeurs remises par défaut. Cliquez sur « Appliquer & Recalculer » pour régénérer les graphiques.", "ok");
  }
};

async function triggerSimulation(customElo = null) {
  const btn = document.getElementById("run-sim-btn");
  const saveBtn = document.getElementById("save-manual-elo-btn");
  const nSims = parseInt(document.getElementById("n-sims").value, 10) || 100000;
  btn.disabled = true;
  saveBtn.disabled = true;
  setStatus(`Calcul de ${nSims.toLocaleString("fr-FR")} scénarios en cours...`);

  try {
    const body = { source: state.activeSource, n_sims: nSims };
    if (customElo) body.custom_elo = customElo;

    const res = await fetch("/api/simulate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok || !data.ok) {
      setStatus(data.error || "Impossible de recalculer les projections.", "err");
      return;
    }
    state.cacheBust = Date.now();
    await loadState(state.activeSource);
    setStatus(`Projections mises à jour (${nSims.toLocaleString("fr-FR")} scénarios).`, "ok");
  } catch (err) {
    setStatus("Erreur de connexion au serveur.", "err");
  } finally {
    btn.disabled = false;
    saveBtn.disabled = false;
  }
}

document.getElementById("run-sim-btn").onclick = () => triggerSimulation(null);

document.getElementById("save-manual-elo-btn").onclick = () => {
  for (const [club, val] of Object.entries(state.manualElo)) {
    if (!Number.isInteger(val) || val < 500 || val > 3000) {
      setStatus(`Valeur invalide pour ${club} : entrez un nombre entier entre 500 et 3 000.`, "err");
      return;
    }
  }
  triggerSimulation(state.manualElo);
};

document.getElementById("club-search").oninput = () => renderClubExplorer();

document.getElementById("prev-team").onclick = () => {
  if (!state.teams.length) return;
  const idx = state.teams.findIndex(t => t.team === state.selectedTeam);
  state.selectedTeam = state.teams[(idx - 1 + state.teams.length) % state.teams.length].team;
  renderClubExplorer();
};

document.getElementById("next-team").onclick = () => {
  if (!state.teams.length) return;
  const idx = state.teams.findIndex(t => t.team === state.selectedTeam);
  state.selectedTeam = state.teams[(idx + 1) % state.teams.length].team;
  renderClubExplorer();
};

document.querySelectorAll("#club-chart-tabs .pill-btn").forEach(btn => {
  btn.onclick = () => {
    state.activeChart = btn.dataset.chart;
    document.querySelectorAll("#club-chart-tabs .pill-btn").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    renderClubExplorer();
  };
});

document.querySelectorAll("#standings-subtabs .pill-btn").forEach(btn => {
  btn.onclick = () => {
    document.querySelectorAll("#standings-subtabs .pill-btn").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    for (const id of ["sub-table", "sub-overview", "sub-thresholds", "sub-rank-points"]) {
      document.getElementById(id).style.display = (id === btn.dataset.sub) ? "block" : "none";
    }
  };
});

document.getElementById("rank-pos-select").onchange = (e) => {
  state.selectedRankPos = parseInt(e.target.value, 10) || 1;
  renderRankPointsChart();
};

document.getElementById("prev-rank-pos").onclick = () => {
  state.selectedRankPos = state.selectedRankPos > 1 ? state.selectedRankPos - 1 : 36;
  renderRankPointsChart();
};

document.getElementById("next-rank-pos").onclick = () => {
  state.selectedRankPos = state.selectedRankPos < 36 ? state.selectedRankPos + 1 : 1;
  renderRankPointsChart();
};

document.querySelectorAll("#rank-pos-shortcuts [data-rank-pos]").forEach(btn => {
  btn.onclick = () => {
    state.selectedRankPos = parseInt(btn.dataset.rankPos, 10) || 1;
    renderRankPointsChart();
  };
});

document.querySelectorAll("#sub-table [data-filter]").forEach(btn => {
  btn.onclick = () => {
    state.tableFilter = btn.dataset.filter;
    document.querySelectorAll("#sub-table [data-filter]").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    renderStandingsPage();
  };
});

document.querySelectorAll("th.sortable").forEach(th => {
  th.onclick = () => {
    const key = th.dataset.sort;
    if (state.sortKey === key) {
      state.sortDesc = !state.sortDesc;
    } else {
      state.sortKey = key;
      state.sortDesc = (key !== "cur_rank" && key !== "team");
    }
    renderStandingsPage();
  };
});

document.getElementById("duel-club-a").onchange = (e) => {
  state.duelA = e.target.value;
  renderDuelPage();
};

document.getElementById("duel-club-b").onchange = (e) => {
  state.duelB = e.target.value;
  renderDuelPage();
};

document.getElementById("calendar-club-filter").onchange = (e) => {
  state.calClub = e.target.value;
  renderCalendar();
};

document.querySelectorAll("#calendar-mode .pill-btn").forEach(btn => {
  btn.onclick = () => {
    state.calMode = btn.dataset.cal;
    document.querySelectorAll("#calendar-mode .pill-btn").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    renderCalendar();
  };
});

loadState();
