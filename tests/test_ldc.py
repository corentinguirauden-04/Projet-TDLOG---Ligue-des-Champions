"""Suite de tests unitaires et d'intégration (bibliothèque standard unittest).

Exécution :
    python -m unittest discover -s tests -v
"""
from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

# Permet d'importer `ldc` depuis `src/` sans installation préalable.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ldc import config, data, elo, pipeline, simulation, visualization, web_server


class TestDataLayer(unittest.TestCase):
    """Vérifie les invariants du calendrier et la validation des notes Elo."""

    def test_calendar_invariants(self) -> None:
        self.assertTrue(data.check())
        self.assertEqual(len(data.TEAMS), 36)
        self.assertEqual(data.current_matchday(), 4)
        self.assertEqual(data.total_matchdays(), 8)

    def test_validate_elo_map_accepts_default(self) -> None:
        cleaned, err = data.validate_elo_map(data.DEFAULT_ELO)
        self.assertIsNone(err)
        self.assertIsNotNone(cleaned)
        assert cleaned is not None
        self.assertEqual(len(cleaned), 36)

    def test_validate_elo_map_rejects_invalid_cases(self) -> None:
        _, err_type = data.validate_elo_map([])
        self.assertIsNotNone(err_type)

        incomplete = dict(data.DEFAULT_ELO)
        incomplete.pop("PSG")
        _, err_missing = data.validate_elo_map(incomplete)
        self.assertIsNotNone(err_missing)

        out_of_range = dict(data.DEFAULT_ELO)
        out_of_range["PSG"] = 9999
        _, err_range = data.validate_elo_map(out_of_range)
        self.assertIsNotNone(err_range)

        bool_val = dict(data.DEFAULT_ELO)
        bool_val["PSG"] = True  # type: ignore[assignment]
        _, err_bool = data.validate_elo_map(bool_val)
        self.assertIsNotNone(err_bool)

    def test_load_elo_reads_data_file(self) -> None:
        ratings, elo_date = data.load_elo()
        self.assertEqual(set(ratings), set(data.TEAMS))
        self.assertTrue(elo_date is None or len(elo_date) == 10)


class TestEloIngestion(unittest.TestCase):
    """Vérifie la normalisation et le parsing complet de data/clubelo_ranking.html."""

    def test_norm_handles_accents_and_nordic_letters(self) -> None:
        self.assertEqual(elo._norm("Bodø/Glimt"), "bodoglimt")
        self.assertEqual(elo._norm("Bayern München"), "bayernmunchen")
        self.assertEqual(elo._norm("Fenerbahçe"), "fenerbahce")

    def test_clubelo_html_matches_all_36_teams(self) -> None:
        if not config.CLUBELO_HTML_FILE.is_file():
            self.skipTest("data/clubelo_ranking.html absent")
        html = elo._read_html_file(config.CLUBELO_HTML_FILE)
        records, _ = elo.extract_records_from_html(html)
        ratings, missing, _ = elo.match_project_teams(records)
        self.assertEqual(len(ratings), 36)
        self.assertEqual(missing, [])
        # Vérifie l'absence de collision d'homonymes (Barcelona Espagne vs Équateur, Liverpool ENG vs URY).
        self.assertGreater(ratings["Barcelona"], 1900)
        self.assertGreater(ratings["Liverpool"], 1850)

    def test_cloudflare_page_rejected(self) -> None:
        with self.assertRaises(ValueError):
            elo.extract_records_from_html("<html><title>Just a moment...</title><body>Checking your browser</body></html>")


class TestSimulationEngine(unittest.TestCase):
    """Vérifie les propriétés mathématiques et la reproductibilité du moteur Monte Carlo."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.sim = simulation.simulate(n_sims=600, seed=42, elo=data.DEFAULT_ELO, elo_date="2026-11-22")

    def test_win_exp_symmetry(self) -> None:
        self.assertAlmostEqual(simulation.win_exp(1800, 1800), 0.5)
        self.assertAlmostEqual(simulation.win_exp(2000, 1800) + simulation.win_exp(1800, 2000), 1.0)

    def test_reproducibility_with_fixed_seed(self) -> None:
        sim_b = simulation.simulate(n_sims=600, seed=42, elo=data.DEFAULT_ELO, elo_date="2026-11-22")
        np.testing.assert_array_equal(self.sim["ranks"], sim_b["ranks"])
        np.testing.assert_array_equal(self.sim["pts"], sim_b["pts"])

    def test_elo_remains_fixed_by_default(self) -> None:
        expected = np.array([data.DEFAULT_ELO[t] for t in data.TEAMS], dtype=np.float32)
        np.testing.assert_array_equal(self.sim["elo"], expected)

    def test_rank_distribution_is_doubly_stochastic(self) -> None:
        dist = simulation.rank_distribution(self.sim)
        self.assertEqual(dist.shape, (36, 36))
        np.testing.assert_allclose(dist.sum(axis=1), 1.0, atol=1e-9)
        np.testing.assert_allclose(dist.sum(axis=0), 1.0, atol=1e-9)

    def test_qualification_probs_sum_to_one(self) -> None:
        probs = simulation.qualification_probs(self.sim)
        for team, q in probs.items():
            self.assertAlmostEqual(q["top8"] + q["playoff"] + q["out"], 1.0, places=9, msg=team)
            self.assertAlmostEqual(q["top8"] + q["playoff"], q["top24"], places=9, msg=team)

    def test_points_by_position_is_monotonically_decreasing(self) -> None:
        pts_pos = simulation.points_by_position(self.sim)
        self.assertEqual(pts_pos.shape, (600, 36))
        self.assertTrue(np.all(pts_pos[:, :-1] >= pts_pos[:, 1:]))

    def test_qualification_by_points_sums_to_one(self) -> None:
        by_pts = simulation.qualification_by_points(self.sim)
        valid = by_pts["total"] > 0
        sums = by_pts["top8"][valid] + by_pts["playoff"][valid] + by_pts["out"][valid]
        np.testing.assert_allclose(sums, 1.0, atol=1e-9)

    def test_match_importance_structure_and_bounds(self) -> None:
        imp = simulation.match_importance(self.sim)
        self.assertEqual(len(imp["PSG"]), len(data.REMAINING))
        scores = [m["importance"] for m in imp["PSG"]]
        self.assertEqual(scores, sorted(scores, reverse=True))
        for entry in imp["PSG"]:
            self.assertGreaterEqual(entry["importance"], 0.0)
            self.assertGreaterEqual(entry["worst_rank"], entry["best_rank"])


class TestVisualization(unittest.TestCase):
    """Vérifie le formatage des pourcentages et la génération sans erreur de tous les graphiques."""

    def test_pct_formatting(self) -> None:
        self.assertEqual(visualization.pct(0.0), "0.0 %")
        self.assertEqual(visualization.pct(0.0001), "<0.1 %")
        self.assertEqual(visualization.pct(0.5), "50.0 %")
        self.assertEqual(visualization.pct(0.9999), ">99.9 %")
        self.assertEqual(visualization.pct(1.0), "100.0 %")

    def test_render_all_chart_types_smoke(self) -> None:
        sim = simulation.simulate(n_sims=200, seed=42, elo=data.DEFAULT_ELO, elo_date="2026-11-22")
        table = simulation.current_table()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            paths = [
                tmp_dir / "classement.png",
                tmp_dir / "points.png",
                tmp_dir / "matchs_cles.png",
                tmp_dir / "pos_8.png",
                tmp_dir / "overview.png",
                tmp_dir / "thresholds.png",
                tmp_dir / "scenario.png",
            ]
            visualization.team_card("PSG", sim, table, paths[0])
            visualization.team_points_card("PSG", sim, table, paths[1])
            visualization.team_important_matches_card("PSG", sim, table, paths[2])
            visualization.position_points_card(8, sim, paths[3])
            visualization.overview(sim, table, paths[4])
            visualization.points_thresholds_card(sim, paths[5])
            visualization.objectives_card(sim, {"PSG": 8, "Lens": 24}, paths[6])
            for path in paths:
                self.assertTrue(path.is_file() and path.stat().st_size > 1000, f"Image invalide : {path}")


class TestWebController(unittest.TestCase):
    """Vérifie la sécurité et les routes HTTP du serveur web."""

    def test_path_traversal_blocked(self) -> None:
        self.assertIsNone(web_server.resolve_safe_output_path("../data/elo.json"))
        self.assertIsNone(web_server.resolve_safe_output_path("../../README.md"))
        safe = web_server.resolve_safe_output_path("clubelo/classement_global.png")
        self.assertIsNotNone(safe)

    def test_safe_filename(self) -> None:
        self.assertEqual(pipeline.safe_filename("Bodo/Glimt"), "bodo-glimt")
        self.assertEqual(pipeline.safe_filename("Real Madrid"), "real_madrid")

    def _dispatch_request(self, method: str, path: str, payload: dict | None = None) -> tuple[int, bytes]:
        """Invoque LdcRequestHandler en mémoire (sans socket réseau : test unitaire hermétique)."""
        body = json.dumps(payload).encode("utf-8") if payload is not None else b""
        handler = web_server.LdcRequestHandler.__new__(web_server.LdcRequestHandler)
        handler.path = path
        handler.command = method
        handler.request_version = "HTTP/1.1"
        handler.client_address = ("127.0.0.1", 0)
        handler.headers = {"Content-Length": str(len(body))}
        handler.rfile = io.BytesIO(body)
        handler.wfile = io.BytesIO()
        status_holder: list[int] = []

        def _capture_response(code: int, message: str | None = None) -> None:
            status_holder.append(int(code))

        handler.send_response = _capture_response  # type: ignore[method-assign]
        handler.send_header = lambda _k, _v: None  # type: ignore[method-assign]
        handler.end_headers = lambda: None  # type: ignore[method-assign]
        handler.send_error = lambda code, message=None: status_holder.append(int(code))  # type: ignore[method-assign]

        if method == "GET":
            handler.do_GET()
        else:
            handler.do_POST()
        return status_holder[0], handler.wfile.getvalue()

    def test_http_routes_hermetic(self) -> None:
        for route, expected_fragment in (
            ("/", "OBSERVATOIRE LIGUE DES CHAMPIONS"),
            ("/styles.css", "--top8"),
            ("/app.js", "renderRankPointsChart"),
        ):
            status, raw = self._dispatch_request("GET", route)
            self.assertEqual(status, 200)
            self.assertIn(expected_fragment, raw.decode("utf-8"))

        status, raw = self._dispatch_request("GET", "/api/state?source=clubelo")
        self.assertEqual(status, 200)
        state = json.loads(raw.decode("utf-8"))
        self.assertEqual(state["active_source"], "clubelo")
        self.assertEqual(state["matchday"], 4)
        self.assertEqual(len(state["teams"]), 36)

        bad_status, _ = self._dispatch_request("POST", "/api/simulate", {"source": "clubelo", "n_sims": 5})
        self.assertEqual(bad_status, 400)

        traversal_status, _ = self._dispatch_request("GET", "/outputs/../data/elo.json")
        self.assertEqual(traversal_status, 403)


if __name__ == "__main__":
    unittest.main()
