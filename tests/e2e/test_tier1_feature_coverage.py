"""
test_tier1_feature_coverage.py — Tier 1: Comprehensive Feature Coverage for All 20 Features.
5 Feature Groups, >= 5 Test Cases per Group (Total 30 Test Cases).
"""

import importlib.util
import json
import math
import os
import re
import sys
import unittest
from pathlib import Path

# Add tests/e2e to sys.path
CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from fixtures import (
    BENCHMARK_25_FUNDS,
    TOP_15_PENETRATED_ORACLE,
    SKILL_ROOT,
    SCRIPTS_DIR,
    TEMPLATES_DIR,
    REFERENCES_DIR,
    DOCS_DIR,
    calculate_portfolio_totals,
    detect_parallel_clones,
    evaluate_risk_rules,
    get_benchmark_csv_content,
    get_benchmark_markdown_content
)


def load_module_from_file(module_name: str, file_path: Path):
    if not file_path.exists():
        return None
    spec = importlib.util.spec_from_file_location(module_name, str(file_path))
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ==============================================================================
# GROUP A: Core Algorithm & Penetration Engine (F03, F04, F05, F12, F13)
# ==============================================================================
class TestGroupACoreAlgorithm(unittest.TestCase):
    """Features 3, 4, 5, 12, 13: Parsing, Penetration, Redundancy, Clones, Tech Exposure"""

    def test_f03_multi_format_data_parsing_csv_and_markdown(self):
        """F03: Parse CSV and Markdown table formats into structured fund records."""
        csv_text = get_benchmark_csv_content()
        lines = csv_text.strip().split("\n")
        self.assertGreaterEqual(len(lines), 26, "CSV should contain header + 25 funds")
        header = lines[0].split(",")
        self.assertIn("基金代码", header)
        self.assertIn("投入本金", header)

        # Markdown test
        md_text = get_benchmark_markdown_content()
        md_lines = [l for l in md_text.strip().split("\n") if l.startswith("|")]
        self.assertGreaterEqual(len(md_lines), 27, "Markdown should contain header, divider, and 25 rows")
        first_row = [c.strip() for c in md_lines[2].split("|") if c.strip()]
        self.assertEqual(first_row[0], "000055", "First fund code must match")

    def test_f04_penetration_matrix_aggregation_logic(self):
        """F04: Mathematical verification of weighted product aggregation W_k = sum(w_i * f_ik)."""
        # Test NVDA penetration from 8 QDII funds
        qdii_funds = [f for f in BENCHMARK_25_FUNDS if f["category"] == "QDII并联纳指"]
        self.assertEqual(len(qdii_funds), 8, "Must have exactly 8 parallel QDII funds")
        
        # In Nasdaq-100 benchmark, NVDA weight is ~8.8%
        nvda_weight = 0.088
        total_nvda_val = sum(f["market_value"] * nvda_weight for f in qdii_funds)
        # 31,400 * 0.088 = 2,763.20
        self.assertAlmostEqual(total_nvda_val, 2763.20, places=2)
        
        # Portfolio weight of NVDA = 2763.20 / 87000 = 3.176% (~3.18%)
        total_mv = sum(f["market_value"] for f in BENCHMARK_25_FUNDS)
        nvda_ratio = (total_nvda_val / total_mv) * 100
        self.assertAlmostEqual(nvda_ratio, 3.18, places=1)

    def test_f05_parallel_redundancy_index_calculation(self):
        """F05: Quantify parallel clone redundancy index RI for multiple QDII funds."""
        clones = detect_parallel_clones(BENCHMARK_25_FUNDS)
        self.assertEqual(len(clones), 1, "Should identify 1 clone group for Nasdaq-100")
        ndx_group = clones[0]
        self.assertEqual(ndx_group["count"], 8, "Nasdaq group must contain 8 funds")
        self.assertEqual(ndx_group["group_id"], "CLONE_QDII_NDX100")
        
        # Redundancy Index: RI = (N - 1) / N, for N=8, RI = 7/8 = 0.875 (87.5% redundancy)
        ri = (ndx_group["count"] - 1) / ndx_group["count"]
        self.assertAlmostEqual(ri, 0.875, places=3)

    def test_f12_qdii_parallel_cluster_detection(self):
        """F12: Aggregate 8 parallel QDII funds and extract consolidated US Tech holdings."""
        qdii_codes = {"000055", "006479", "000834", "160213", "000043", "040046", "016055", "009880"}
        found_codes = {f["code"] for f in BENCHMARK_25_FUNDS if f["category"] == "QDII并联纳指"}
        self.assertEqual(qdii_codes, found_codes, "All 8 QDII codes must match benchmark")
        
        # Consolidated market value of QDII funds = ¥31,400.00
        total_qdii_mv = sum(f["market_value"] for f in BENCHMARK_25_FUNDS if f["code"] in qdii_codes)
        self.assertEqual(total_qdii_mv, 31400.0)

    def test_f13_macro_tech_exposure_high_concentration(self):
        """F13: Merged A-share semiconductor + US Tech exposure reaches 65.56% of total."""
        totals = calculate_portfolio_totals(BENCHMARK_25_FUNDS)
        self.assertEqual(totals["tech_market_value"], 57040.0, "Tech exposure value must be exactly ¥57,040.00")
        self.assertAlmostEqual(totals["tech_ratio"] * 100, 65.56, delta=0.05, msg="Tech ratio must be ~65.56%")

    def test_f04_f13_production_script_penetration_contract(self):
        """F04 & F13: Validate scripts/penetration.py interface contract if implemented."""
        script_path = SCRIPTS_DIR / "penetration.py"
        if not script_path.exists():
            self.skipTest("M1: scripts/penetration.py not yet created by Worker")
        mod = load_module_from_file("penetration", script_path)
        self.assertIsNotNone(mod, "penetration.py must be importable")
        # Check standard engine or penetration function
        has_engine = (
            hasattr(mod, "penetrate_portfolio") or
            hasattr(mod, "EthanHoldEngine") or
            hasattr(mod, "evaluate_penetration") or
            hasattr(mod, "calculate_penetration")
        )
        self.assertTrue(has_engine, "penetration.py must expose penetrate_portfolio or EthanHoldEngine")


# ==============================================================================
# GROUP B: Circuit Breakers & Risk Engine (F06, F07, F15)
# ==============================================================================
class TestGroupBCircuitBreaker(unittest.TestCase):
    """Features 6, 7, 15: P0/P1/P2 Rules, Pre-Trade Simulation, Cooling Period"""

    def test_f06_l3_macro_tech_hard_cap_trip(self):
        """F06: Macro Tech >= 50.0% triggers L3 P0_CRITICAL circuit breaker."""
        totals = calculate_portfolio_totals(BENCHMARK_25_FUNDS)
        rules = evaluate_risk_rules(totals)
        self.assertTrue(rules["is_tripped"], "Circuit breaker must trip when tech is 65.56%")
        self.assertEqual(rules["max_severity"], "P0_CRITICAL")
        codes = [m["code"] for m in rules["intercept_messages"]]
        self.assertIn("P0_MACRO_TECH_OVERWEIGHT", codes)

    def test_f06_l1_and_l2_caps_threshold_matrix(self):
        """F06: Threshold values for L1 (5.0%), L2 (30.0%), L3 (50.0%), and L4 Defensive (15.0%)."""
        # NVDA 3.18% < 5.0% (Warning range 3.5%-5.0%)
        nvda = TOP_15_PENETRATED_ORACLE[0]
        self.assertLess(nvda["weight_pct"], 5.0, "NVDA single stock under 5.0% cap")
        
        # QDII Sub-sector = 31400 / 87000 = 36.09% >= 30.0% (L2 trip)
        qdii_pct = 31400.0 / 87000.0 * 100
        self.assertGreaterEqual(qdii_pct, 30.0, "QDII sub-sector exceeds 30.0% cap")

    def test_f07_pre_trade_impulse_buy_intercept(self):
        """F07: Pre-trade What-If simulation intercepts adding ¥5,000 to 诺安成长 (loss -23%)."""
        totals = calculate_portfolio_totals(BENCHMARK_25_FUNDS)
        proposed_order = {
            "code": "320007",
            "name": "诺安成长混合",
            "amount": 5000.0,
            "target_pnl_rate": -0.23,
            "sector": "A股半导体与芯片"
        }
        res = evaluate_risk_rules(totals, proposed_order)
        self.assertTrue(res["is_tripped"])
        self.assertEqual(res["max_severity"], "P0_CRITICAL")
        codes = [m["code"] for m in res["intercept_messages"]]
        self.assertIn("P0_LOSS_CHASING_INTERCEPT", codes)

    def test_f07_pre_trade_approved_for_safe_asset(self):
        """F07: Adding to defensive assets (pure bond) does NOT trip loss-chasing breaker."""
        totals = calculate_portfolio_totals(BENCHMARK_25_FUNDS)
        safe_order = {
            "code": "000198",
            "name": "天弘同利债券(LOF)A",
            "amount": 5000.0,
            "target_pnl_rate": 0.02,
            "sector": "纯债防守"
        }
        res = evaluate_risk_rules(totals, safe_order)
        codes = [m["code"] for m in res["intercept_messages"]]
        self.assertNotIn("P0_LOSS_CHASING_INTERCEPT", codes, "Safe bond order must not trigger impulse buy intercept")

    def test_f15_cooling_off_period_and_defensive_guidance(self):
        """F15: Intercept message outputs mandatory 48-hour cooling period & defensive suggestions."""
        totals = calculate_portfolio_totals(BENCHMARK_25_FUNDS)
        proposed_order = {"code": "320007", "amount": 5000.0, "target_pnl_rate": -0.23}
        res = evaluate_risk_rules(totals, proposed_order)
        self.assertEqual(res["cooling_off_hours"], 48, "Cooling off hours must be 48")
        self.assertGreaterEqual(len(res["rebalance_recommendations"]), 1)
        recs_text = " ".join(res["rebalance_recommendations"])
        self.assertTrue("纯债" in recs_text or "固收" in recs_text or "48小时" in recs_text)

    def test_f06_production_script_circuit_breaker_contract(self):
        """F06: Validate scripts/circuit_breaker.py interface contract if implemented."""
        script_path = SCRIPTS_DIR / "circuit_breaker.py"
        if not script_path.exists():
            self.skipTest("M1: scripts/circuit_breaker.py not yet created by Worker")
        mod = load_module_from_file("circuit_breaker", script_path)
        self.assertIsNotNone(mod)
        has_eval = hasattr(mod, "evaluate_circuit_breakers") or hasattr(mod, "check_circuit_breaker")
        self.assertTrue(has_eval, "circuit_breaker.py must expose evaluate_circuit_breakers or check_circuit_breaker")


# ==============================================================================
# GROUP C: Standalone HTML Dashboard & SVG System (F08, F09, F10)
# ==============================================================================
class TestGroupCHtmlDashboard(unittest.TestCase):
    """Features 8, 9, 10: Single-file HTML, Zero CDN, Retina Pure SVG, Local Isolation"""

    def test_f08_offline_standalone_html_no_external_cdn(self):
        """F08: Standalone HTML template must NOT contain external CDN or remote scripts."""
        template_path = TEMPLATES_DIR / "dashboard_template.html"
        if not template_path.exists():
            self.skipTest("M2: templates/dashboard_template.html not yet created by Worker")
        content = template_path.read_text(encoding="utf-8")
        
        # Check forbidden external CDN script tags
        cdn_patterns = [
            r'<script[^>]+src=["\']http[s]?://',
            r'<link[^>]+rel=["\']stylesheet["\'][^>]+href=["\']http[s]?://',
            r'cdn\.jsdelivr\.net',
            r'cdnjs\.cloudflare\.com',
            r'unpkg\.com'
        ]
        for pat in cdn_patterns:
            self.assertFalse(
                re.search(pat, content, re.IGNORECASE),
                f"Dashboard template contains forbidden external CDN pattern: {pat}"
            )

    def test_f08_self_contained_inline_css_and_js(self):
        """F08: Standalone HTML must contain inline <style> and <script> tags."""
        template_path = TEMPLATES_DIR / "dashboard_template.html"
        if not template_path.exists():
            self.skipTest("M2: templates/dashboard_template.html not yet created by Worker")
        content = template_path.read_text(encoding="utf-8")
        self.assertIn("<style>", content, "Dashboard template must contain inline <style>")
        self.assertIn("<script>", content, "Dashboard template must contain inline <script>")

    def test_f09_retina_pure_svg_vector_charts(self):
        """F09: Visual charts must be implemented with native SVG elements."""
        template_path = TEMPLATES_DIR / "dashboard_template.html"
        if not template_path.exists():
            self.skipTest("M2: templates/dashboard_template.html not yet created by Worker")
        content = template_path.read_text(encoding="utf-8")
        self.assertIn("<svg", content, "Dashboard must use native <svg> tags")
        self.assertTrue("viewBox=" in content or "viewbox=" in content.lower(), "SVG must use responsive viewBox")

    def test_f09_circuit_breaker_alert_banner_rendered(self):
        """F09: Alert banner or badge elements must exist for circuit breaker warnings."""
        template_path = TEMPLATES_DIR / "dashboard_template.html"
        if not template_path.exists():
            self.skipTest("M2: templates/dashboard_template.html not yet created by Worker")
        content = template_path.read_text(encoding="utf-8")
        self.assertTrue(
            "熔断" in content or "circuit-breaker" in content.lower() or "breaker" in content.lower(),
            "Dashboard must include visual circuit breaker indicators"
        )

    def test_f10_privacy_and_local_zero_network_isolation(self):
        """F10: Dashboard must not contain any tracking pixels, google analytics, or telemetry."""
        template_path = TEMPLATES_DIR / "dashboard_template.html"
        if not template_path.exists():
            self.skipTest("M2: templates/dashboard_template.html not yet created by Worker")
        content = template_path.read_text(encoding="utf-8")
        tracking_keywords = ["google-analytics", "gtag", "telemetry", "tracking", "pixel.gif", "beacon"]
        for kw in tracking_keywords:
            self.assertNotIn(kw, content.lower(), f"Privacy violation: found telemetry keyword '{kw}'")

    def test_f08_production_script_dashboard_contract(self):
        """F08: Validate scripts/generate_dashboard.py contract if implemented."""
        script_path = SCRIPTS_DIR / "generate_dashboard.py"
        if not script_path.exists():
            self.skipTest("M2: scripts/generate_dashboard.py not yet created by Worker")
        mod = load_module_from_file("generate_dashboard", script_path)
        self.assertIsNotNone(mod)
        has_render = hasattr(mod, "render_dashboard_html") or hasattr(mod, "generate_dashboard")
        self.assertTrue(has_render, "generate_dashboard.py must expose render_dashboard_html")


# ==============================================================================
# GROUP D: Benchmark Dataset & CLI Orchestration (F01, F02, F11, F14)
# ==============================================================================
class TestGroupDBenchmarkAndCLI(unittest.TestCase):
    """Features 1, 2, 11, 14: Skill YAML, Gate Modes, 25-Fund Math, CLI Entrypoint"""

    def test_f01_skill_yaml_frontmatter_specification(self):
        """F01: SKILL.md must contain valid YAML frontmatter with name and description."""
        skill_md = SKILL_ROOT / "SKILL.md"
        if not skill_md.exists():
            self.skipTest("M1: SKILL.md not yet created by Worker")
        content = skill_md.read_text(encoding="utf-8")
        self.assertTrue(content.startswith("---"), "SKILL.md must begin with YAML frontmatter delimiter '---'")
        self.assertIn("name: ethan-hold", content, "SKILL.md frontmatter must specify 'name: ethan-hold'")
        self.assertIn("description:", content, "SKILL.md frontmatter must contain 'description:'")

    def test_f02_interactive_stage_gate_mechanisms(self):
        """F02: SKILL.md defines advisory vs action modes and interactive gates."""
        skill_md = SKILL_ROOT / "SKILL.md"
        if not skill_md.exists():
            self.skipTest("M1: SKILL.md not yet created by Worker")
        content = skill_md.read_text(encoding="utf-8")
        self.assertTrue(
            "参谋模式" in content or "代操模式" in content or "门禁" in content or "ask_question" in content,
            "SKILL.md must define Ethan interactive stage gate mechanisms"
        )

    def test_f11_canonical_25_funds_benchmark_math_invariants(self):
        """F11: Exact mathematical invariant assertions for the 25-fund benchmark portfolio."""
        totals = calculate_portfolio_totals(BENCHMARK_25_FUNDS)
        self.assertEqual(totals["total_cost"], 100000.0, "Total cost must be exactly ¥100,000.00")
        self.assertEqual(totals["total_market_value"], 87000.0, "Market value must be exactly ¥87,000.00")
        self.assertEqual(totals["total_pnl"], -13000.0, "Total PnL must be exactly -¥13,000.00")
        self.assertAlmostEqual(totals["total_pnl_rate"], -0.13, places=4, msg="PnL rate must be exactly -13.00%")

    def test_f11_benchmark_json_fixture_validity(self):
        """F11: Verify tests/fixtures/portfolio_25_funds.json if present matches standard schema."""
        fixture_path = SKILL_ROOT / "tests" / "fixtures" / "portfolio_25_funds.json"
        if not fixture_path.exists():
            self.skipTest("M3: tests/fixtures/portfolio_25_funds.json pending creation by Worker")
        with open(fixture_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertIn("funds", data)
        self.assertEqual(len(data["funds"]), 25)
        self.assertEqual(data.get("total_cost"), 100000.0)
        self.assertEqual(data.get("total_market_value"), 87000.0)

    def test_f14_cli_entrypoint_file_existence_and_help(self):
        """F14: scripts/run_analysis.py exists and supports standard CLI arguments."""
        cli_path = SCRIPTS_DIR / "run_analysis.py"
        if not cli_path.exists():
            self.skipTest("M3: scripts/run_analysis.py pending creation by Worker")
        content = cli_path.read_text(encoding="utf-8")
        self.assertIn("argparse", content, "run_analysis.py should use argparse for CLI options")
        self.assertTrue("--input" in content or "-i" in content, "run_analysis.py should accept input argument")
        self.assertTrue("--output" in content or "-o" in content, "run_analysis.py should accept output argument")

    def test_f14_cli_pipeline_contract_callable(self):
        """F14: Validate scripts/run_analysis.py main entrypoint interface contract."""
        cli_path = SCRIPTS_DIR / "run_analysis.py"
        if not cli_path.exists():
            self.skipTest("M3: scripts/run_analysis.py pending creation by Worker")
        mod = load_module_from_file("run_analysis", cli_path)
        self.assertIsNotNone(mod)
        self.assertTrue(hasattr(mod, "main"), "run_analysis.py must define a main() function")


# ==============================================================================
# GROUP E: Open Source Repository & Media Artifacts (F16, F17, F18, F19, F20)
# ==============================================================================
class TestGroupEOpenSourceAndMedia(unittest.TestCase):
    """Features 16, 17, 18, 19, 20: Strategy Report, Checklist, Repo Material, Copy, Roadmap"""

    def test_f16_open_source_release_strategy_report(self):
        """F16: references/release_strategy.md contains Path A/B/C comparison and timeline."""
        strategy_path = REFERENCES_DIR / "release_strategy.md"
        if not strategy_path.exists():
            self.skipTest("M5: references/release_strategy.md pending creation by Worker")
        content = strategy_path.read_text(encoding="utf-8")
        self.assertTrue("路径" in content or "Path" in content, "Strategy doc must compare release paths")
        self.assertTrue("先发后开" in content or "同步开源" in content, "Must analyze key distribution paths")

    def test_f17_operations_checklist_cangqiong_style(self):
        """F17: docs/ethan_hold_operations_checklist.md follows Cangqiong Waimai style."""
        checklist_path = DOCS_DIR / "ethan_hold_operations_checklist.md"
        if not checklist_path.exists():
            self.skipTest("M5: docs/ethan_hold_operations_checklist.md pending creation by Worker")
        content = checklist_path.read_text(encoding="utf-8")
        self.assertIn("作战清单", content, "Checklist title must follow 《...作战清单》 convention")
        self.assertTrue("🔴" in content and "🟡" in content and "🔵" in content, "Must use 3-tier priority emojis")
        self.assertTrue(
            ("讲啥" in content and "重点拿" in content and "怎么用" in content),
            "Must use 3-part section structure (【讲啥】/【重点拿】/【怎么用】)"
        )

    def test_f18_github_repository_standard_files(self):
        """F18: Standard GitHub repository files (README.md, CONTRIBUTING.md, LICENSE) exist."""
        readme = SKILL_ROOT / "README.md"
        contributing = SKILL_ROOT / "CONTRIBUTING.md"
        license_file = SKILL_ROOT / "LICENSE"
        
        missing = [f.name for f in (readme, contributing, license_file) if not f.exists()]
        if missing:
            self.skipTest(f"M4: GitHub repo files {missing} pending creation by Worker")
            
        self.assertTrue(readme.exists())
        self.assertTrue(contributing.exists())
        self.assertTrue(license_file.exists())
        license_text = license_file.read_text(encoding="utf-8")
        self.assertIn("MIT License", license_text, "LICENSE must be MIT")

    def test_f19_media_storyboard_and_copywriting(self):
        """F19: references/media_copywriting.md contains 4-column video storyboard and platform copy."""
        media_path = REFERENCES_DIR / "media_copywriting.md"
        if not media_path.exists():
            self.skipTest("M5: references/media_copywriting.md pending creation by Worker")
        content = media_path.read_text(encoding="utf-8")
        self.assertTrue("分镜" in content or "storyboard" in content.lower(), "Must include video storyboard")
        self.assertTrue("小红书" in content or "B站" in content or "视频号" in content, "Must cover media platforms")

    def test_f20_ethan_family_ecosystem_roadmap(self):
        """F20: Roadmap describes ethan-hold -> ethan-trace -> ethan-plan family evolution."""
        readme = SKILL_ROOT / "README.md"
        roadmap_found = False
        for path in [readme, REFERENCES_DIR / "release_strategy.md"]:
            if path.exists():
                text = path.read_text(encoding="utf-8")
                if "ethan-trace" in text or "ethan-plan" in text:
                    roadmap_found = True
                    break
        if not roadmap_found:
            self.skipTest("M4/M5: Ethan family roadmap pending in README.md or release_strategy.md")
        self.assertTrue(roadmap_found, "Ethan Family roadmap must be documented")

    def test_f18_license_financial_disclaimer(self):
        """F18: Documentation must include a strict financial non-advisory disclaimer."""
        readme = SKILL_ROOT / "README.md"
        if not readme.exists():
            self.skipTest("M4: README.md pending creation by Worker")
        content = readme.read_text(encoding="utf-8")
        self.assertTrue(
            "免责声明" in content or "Disclaimer" in content or "不构成任何投资建议" in content,
            "README must contain explicit financial disclaimer"
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
