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
  calMatchday: null,
  calSort: "order",
  calClub: "",
  cacheBust: Date.now(),
};

const frenchClubs = new Set(["PSG", "Lille", "Lens"]);

const chartDescriptions = {
  classement: "Probabilité pour le club de terminer à chacune des 36 places finales, de la 36e place à gauche jusqu'à la 1re place à droite (rose : élimination, jaune : barrages, vert : Top 8 direct).",
  points: "Distribution du total de points en fin de phase de ligue. Le trait pointillé vert indique la moyenne attendue et les barres jaunes représentent la plage probable (80 % des scénarios).",
  matchs_cles: "Les 10 rencontres à venir (parmi tous les matchs de la compétition) qui créent le plus grand écart de classement final moyen pour le club selon leur issue (1 / N / 2).",
  calendrier: "Affiches restantes du club avec les probabilités (Domicile / Nul / Extérieur) et l'écart de classement final moyen en jeu pour chacune des deux équipes.",
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

  if (state.calMatchday === null) {
    state.calMatchday = Math.min(state.matchday + 1, state.totalMatchdays);
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
  renderCalendarMatchdays();
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

  const captionEl = document.getElementById("club-chart-caption");
  const zoomHint = document.getElementById("club-zoom-hint");
  const base = `/outputs/${state.outputFolder}/equipes/${club.slug}`;
  const q = `?t=${state.cacheBust}`;
  const display = document.getElementById("club-chart-display");

  if (state.activeChart === "calendrier") {
    if (zoomHint) zoomHint.style.display = "none";
    renderClubUpcomingTab(club.team, captionEl, display);
  } else if (state.activeChart === "all") {
    if (zoomHint) zoomHint.style.display = "";
    captionEl.textContent = chartDescriptions.all;
    display.innerHTML = `
      <div class="triple-chart-grid">
        <img src="${base}/classement.png${q}" alt="Classement ${club.team}" onclick="openLightbox(this.src)">
        <img src="${base}/points.png${q}" alt="Points ${club.team}" onclick="openLightbox(this.src)">
        <img src="${base}/matchs_cles.png${q}" alt="Matchs clés ${club.team}" onclick="openLightbox(this.src)">
      </div>
    `;
  } else {
    if (zoomHint) zoomHint.style.display = "";
    captionEl.textContent = chartDescriptions[state.activeChart];
    const src = `${base}/${state.activeChart}.png${q}`;
    display.innerHTML = `
      <div class="single-chart-wrap">
        <img src="${src}" alt="${state.activeChart} ${club.team}" onclick="openLightbox(this.src)">
      </div>
    `;
  }
}

function renderClubUpcomingTab(teamName, captionEl, displayEl) {
  const teamMap = new Map(state.teams.map(t => [t.team, t]));
  const upcoming = state.remaining
    .filter(m => m.home === teamName || m.away === teamName)
    .sort((a, b) => a.matchday - b.matchday);

  const nHome = upcoming.filter(m => m.home === teamName).length;
  const nAway = upcoming.length - nHome;

  if (captionEl) {
    captionEl.textContent = upcoming.length > 0
      ? `${upcoming.length} affiches restantes pour ${teamName} (${nHome} à domicile, ${nAway} à l'extérieur) — probabilités 1 / N / 2 et impact moyen au classement final pour les deux clubs. Cliquez sur un adversaire pour ouvrir sa fiche.`
      : `Aucun match restant pour ${teamName}.`;
  }

  if (upcoming.length === 0) {
    displayEl.innerHTML = `<div class="cal-empty">Aucune affiche restante.</div>`;
    return;
  }

  displayEl.innerHTML = `
    <div class="matches-grid club-matches-grid">
      ${upcoming.map(m => renderMatchCard(m, false, teamMap, teamName)).join("")}
    </div>
  `;

  displayEl.querySelectorAll(".mc-team-btn[data-team]").forEach(btn => {
    btn.onclick = () => selectClubAndOpen(btn.dataset.team);
  });
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

function renderCalendarMatchdays() {
  const box = document.getElementById("calendar-matchdays");
  if (!box) return;

  const buttons = [];
  for (let md = 1; md <= state.totalMatchdays; md++) {
    const isPlayed = md <= state.matchday;
    const isActive = state.calMatchday === md;
    const cls = `md-pill ${isPlayed ? "played-md" : "upcoming-md"}${isActive ? " active" : ""}`;
    const tip = isPlayed ? `Journée ${md} (terminée)` : `Journée ${md} (à venir)`;
    buttons.push(
      `<button type="button" class="${cls}" data-md="${md}" title="${tip}" role="tab" aria-selected="${isActive}">` +
      `<span class="md-dot"></span>J${md}</button>`
    );
    if (md === state.matchday && md < state.totalMatchdays) {
      buttons.push(`<span class="md-sep" aria-hidden="true"></span>`);
    }
  }

  const allActive = state.calMatchday === "all";
  buttons.push(`<span class="md-sep" aria-hidden="true"></span>`);
  buttons.push(
    `<button type="button" class="md-pill all-md${allActive ? " active" : ""}" data-md="all" title="Afficher les 8 journées" role="tab" aria-selected="${allActive}">` +
    `<span class="md-dot"></span>Toutes</button>`
  );

  box.innerHTML = buttons.join("");
  box.querySelectorAll(".md-pill").forEach(btn => {
    btn.onclick = () => {
      state.calMatchday = btn.dataset.md === "all" ? "all" : parseInt(btn.dataset.md, 10);
      renderCalendarMatchdays();
      renderCalendar();
    };
  });

  const prevBtn = document.getElementById("cal-prev-md");
  const nextBtn = document.getElementById("cal-next-md");
  if (prevBtn) prevBtn.disabled = state.calMatchday === "all" || state.calMatchday <= 1;
  if (nextBtn) nextBtn.disabled = state.calMatchday === "all" || state.calMatchday >= state.totalMatchdays;
}

function stakesTier(imp) {
  if (imp >= 6.7) return { cls: "high", label: "Choc décisif" };
  if (imp >= 5.2) return { cls: "med", label: "Enjeu élevé" };
  return { cls: "low", label: "Enjeu modéré" };
}

function zoneDotClass(rank) {
  if (!rank) return "play";
  if (rank <= 8) return "top8";
  if (rank <= 24) return "play";
  return "out";
}

function renderTeamMeta(teamName, teamMap) {
  const info = teamMap.get(teamName);
  if (!info) return "";
  const dot = zoneDotClass(info.cur_rank);
  return `<span class="mc-team-meta"><span class="zone-dot ${dot}"></span>${info.cur_rank}e · ${info.cur_pts} pts</span>`;
}

function renderImpactBox(teamName, imp, bestRank, worstRank, isFocused = false) {
  const tier = stakesTier(imp);
  const rangeText = bestRank > 0 && worstRank > 0
    ? `Rang moyen : ${bestRank.toFixed(1)}e → ${worstRank.toFixed(1)}e`
    : "Impact sur le classement final";
  return `
    <div class="mc-imp-box${isFocused ? " focused" : ""}">
      <div class="mc-imp-top">
        <span class="mc-imp-club" title="Importance pour ${teamName}">Enjeu ${teamName}</span>
        <span class="mc-imp-val ${tier.cls}">±${imp.toFixed(1)} pl.</span>
      </div>
      <div class="mc-imp-range">${rangeText}</div>
    </div>
  `;
}

function renderMatchCard(m, isPlayed, teamMap, focusTeam = null) {
  if (isPlayed) {
    const winner = m.winner || (m.hg > m.ag ? "home" : (m.ag > m.hg ? "away" : "draw"));
    const homeCls = winner === "home" ? "winner" : (winner === "away" ? "loser" : "");
    const awayCls = winner === "away" ? "winner" : (winner === "home" ? "loser" : "");
    const cardCls = winner === "draw" ? "played-draw" : "played-win";
    const statusLabel = winner === "draw"
      ? `<span class="mc-badge med">Match nul</span>`
      : `<span class="mc-badge low">Score final</span>`;

    return `
      <article class="match-card ${cardCls}">
        <div class="mc-head">
          <span class="mc-md-tag">Journée ${m.matchday} · Terminé</span>
          ${statusLabel}
        </div>
        <div class="mc-teams">
          <div class="mc-team home ${homeCls}">
            <button type="button" class="mc-team-btn" data-team="${m.home}">${m.home}</button>
            ${renderTeamMeta(m.home, teamMap)}
          </div>
          <div class="mc-center">
            <span class="match-score ${winner === "draw" ? "draw" : ""}">${m.hg} - ${m.ag}</span>
          </div>
          <div class="mc-team away ${awayCls}">
            <button type="button" class="mc-team-btn" data-team="${m.away}">${m.away}</button>
            ${renderTeamMeta(m.away, teamMap)}
          </div>
        </div>
      </article>
    `;
  }

  const hasStats = typeof m.p_home === "number" && typeof m.home_imp === "number";
  const avgImp = hasStats ? (m.home_imp + m.away_imp) / 2 : 0;
  const tier = hasStats ? stakesTier(avgImp) : { cls: "neutral", label: "À venir" };
  const cardStakesCls = hasStats ? `stakes-${tier.cls}` : "";

  const fav = hasStats
    ? (m.p_home >= m.p_away && m.p_home >= m.p_draw ? "home" : (m.p_away >= m.p_home && m.p_away >= m.p_draw ? "away" : "draw"))
    : "";

  const probsHtml = hasStats ? `
    <div class="mc-probs">
      <div class="mc-prob-labels">
        <span class="mc-prob-home ${fav === "home" ? "fav" : ""}">Dom. <span class="mc-prob-val">${pct(m.p_home)}</span></span>
        <span class="mc-prob-draw ${fav === "draw" ? "fav" : ""}">Nul <span class="mc-prob-val">${pct(m.p_draw)}</span></span>
        <span class="mc-prob-away ${fav === "away" ? "fav" : ""}">Ext. <span class="mc-prob-val">${pct(m.p_away)}</span></span>
      </div>
      <div class="mc-prob-bar" title="Domicile ${pct(m.p_home)} · Nul ${pct(m.p_draw)} · Extérieur ${pct(m.p_away)}">
        <div class="mc-seg-home" style="width: ${(m.p_home * 100).toFixed(1)}%"></div>
        <div class="mc-seg-draw" style="width: ${(m.p_draw * 100).toFixed(1)}%"></div>
        <div class="mc-seg-away" style="width: ${(m.p_away * 100).toFixed(1)}%"></div>
      </div>
    </div>
  ` : "";

  const impactsHtml = hasStats ? `
    <div class="mc-impacts">
      ${renderImpactBox(m.home, m.home_imp, m.home_best_rank, m.home_worst_rank, focusTeam === m.home)}
      ${renderImpactBox(m.away, m.away_imp, m.away_best_rank, m.away_worst_rank, focusTeam === m.away)}
    </div>
  ` : "";

  const venueTag = focusTeam
    ? (focusTeam === m.home
      ? `<span class="mc-venue-tag home">Domicile</span>`
      : `<span class="mc-venue-tag away">Extérieur</span>`)
    : "";

  const badgeText = hasStats ? tier.label : "À venir";

  return `
    <article class="match-card ${cardStakesCls}">
      <div class="mc-head">
        <span class="mc-md-tag">Journée ${m.matchday}${venueTag}</span>
        <span class="mc-badge ${tier.cls}">${badgeText}</span>
      </div>
      <div class="mc-teams">
        <div class="mc-team home">
          <button type="button" class="mc-team-btn" data-team="${m.home}">${m.home}</button>
          ${renderTeamMeta(m.home, teamMap)}
        </div>
        <div class="mc-center">
          <span class="mc-vs">VS</span>
        </div>
        <div class="mc-team away">
          <button type="button" class="mc-team-btn" data-team="${m.away}">${m.away}</button>
          ${renderTeamMeta(m.away, teamMap)}
        </div>
      </div>
      ${probsHtml}
      ${impactsHtml}
    </article>
  `;
}

function sortUpcomingMatches(list) {
  const copy = [...list];
  if (state.calSort === "stakes") {
    copy.sort((a, b) =>
      ((b.home_imp || 0) + (b.away_imp || 0)) - ((a.home_imp || 0) + (a.away_imp || 0))
    );
  } else if (state.calSort === "balanced") {
    copy.sort((a, b) => Math.abs((a.p_home || 0) - (a.p_away || 0)) - Math.abs((b.p_home || 0) - (b.p_away || 0)));
  }
  return copy;
}

function renderCalendar() {
  const box = document.getElementById("calendar-list");
  const summary = document.getElementById("calendar-summary");
  const sortSel = document.getElementById("calendar-sort");
  if (!box) return;

  const teamMap = new Map(state.teams.map(t => [t.team, t]));
  const clubFilter = state.calClub;
  const matchClub = m => !clubFilter || m.home === clubFilter || m.away === clubFilter;

  const isSinglePlayed = typeof state.calMatchday === "number" && state.calMatchday <= state.matchday;
  if (sortSel) sortSel.disabled = isSinglePlayed;

  const sections = [];
  let totalShown = 0;
  let hasUpcoming = false;

  const matchdaysToShow = state.calMatchday === "all"
    ? Array.from({ length: state.totalMatchdays }, (_, i) => i + 1)
    : [state.calMatchday];

  for (const md of matchdaysToShow) {
    const isPlayed = md <= state.matchday;
    const sourceList = isPlayed ? state.played : state.remaining;
    let items = sourceList.filter(m => m.matchday === md && matchClub(m));
    if (!isPlayed) {
      items = sortUpcomingMatches(items);
      if (items.length > 0) hasUpcoming = true;
    }
    if (items.length === 0) continue;
    totalShown += items.length;
    sections.push({ md, isPlayed, items });
  }

  if (summary) {
    const mdLabel = state.calMatchday === "all"
      ? `Toutes les journées (J1–J${state.totalMatchdays})`
      : `Journée ${state.calMatchday} (${state.calMatchday <= state.matchday ? "terminée" : "à venir"})`;
    const clubLabel = clubFilter ? ` · Filtre : ${clubFilter}` : "";
    const countLabel = `${totalShown} match${totalShown > 1 ? "s" : ""}`;
    const legendHtml = hasUpcoming
      ? `
        <div class="cal-legend">
          <span class="cal-legend-item"><span class="legend-swatch" style="background: var(--top8);"></span>Domicile</span>
          <span class="cal-legend-item"><span class="legend-swatch" style="background: #6f82cf;"></span>Nul</span>
          <span class="cal-legend-item"><span class="legend-swatch" style="background: var(--play);"></span>Extérieur</span>
          <span class="cal-legend-item"><span class="legend-swatch" style="background: var(--out);"></span>Choc décisif (≥ 6.7 pl.)</span>
        </div>
      `
      : `
        <div class="cal-legend">
          <span class="cal-legend-item"><span class="legend-swatch" style="background: var(--top8);"></span>Vainqueur / Top 8</span>
          <span class="cal-legend-item"><span class="legend-swatch" style="background: var(--play);"></span>Match nul / Barrages</span>
          <span class="cal-legend-item"><span class="legend-swatch" style="background: var(--out);"></span>Zone élimination</span>
        </div>
      `;
    summary.innerHTML = `<div class="cal-summary-main">${mdLabel}${clubLabel} · ${countLabel}</div>${legendHtml}`;
  }

  if (sections.length === 0) {
    box.innerHTML = `<div class="cal-empty">Aucun match ne correspond à ce filtre.</div>`;
    return;
  }

  // Vue compacte 2 colonnes quand on affiche le parcours complet (J1–J8) d'un seul club.
  if (state.calMatchday === "all" && clubFilter) {
    const flatCards = sections.flatMap(sec =>
      sec.items.map(m => renderMatchCard(m, sec.isPlayed, teamMap))
    );
    box.innerHTML = `<div class="matches-grid">${flatCards.join("")}</div>`;
  } else {
    box.innerHTML = sections
      .map(sec => {
        const groupHead = state.calMatchday === "all"
          ? `
            <div class="cal-group-header">
              <div class="cal-group-title">Journée ${sec.md}</div>
              <span class="mc-badge ${sec.isPlayed ? "low" : "med"}">${sec.isPlayed ? "Résultats officiels" : "Affiches à venir"}</span>
            </div>
          `
          : "";
        return `
          <div>
            ${groupHead}
            <div class="matches-grid">
              ${sec.items.map(m => renderMatchCard(m, sec.isPlayed, teamMap)).join("")}
            </div>
          </div>
        `;
      })
      .join("");
  }

  box.querySelectorAll(".mc-team-btn[data-team]").forEach(btn => {
    btn.onclick = () => selectClubAndOpen(btn.dataset.team);
  });
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
  // Quand un club précis est choisi, afficher toutes ses journées (J1–J8) rend la lecture immédiate.
  if (state.calClub && state.calMatchday !== "all") {
    state.calMatchday = "all";
    renderCalendarMatchdays();
  }
  renderCalendar();
};

document.getElementById("calendar-sort").onchange = (e) => {
  state.calSort = e.target.value;
  renderCalendar();
};

document.getElementById("cal-prev-md").onclick = () => {
  if (typeof state.calMatchday === "number" && state.calMatchday > 1) {
    state.calMatchday -= 1;
    renderCalendarMatchdays();
    renderCalendar();
  }
};

document.getElementById("cal-next-md").onclick = () => {
  if (typeof state.calMatchday === "number" && state.calMatchday < state.totalMatchdays) {
    state.calMatchday += 1;
    renderCalendarMatchdays();
    renderCalendar();
  }
};

loadState();
