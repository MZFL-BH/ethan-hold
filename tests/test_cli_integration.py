#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_cli_integration.py — Integration and Unit Tests for ethan-hold CLI Orchestrator (run_analysis.py)
"""

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# Add skill root to path
SKILL_ROOT = Path(__file__).resolve().parent.parent
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))

from scripts.run_analysis import (
    build_cli_parser,
    clean_financial_number,
    convert_dict_to_fund,
    main,
    parse_portfolio_file,
    run_pipeline,
)


class TestCLIIntegration(unittest.TestCase):
    """Test suite for CLI Orchestrator run_analysis.py."""

    def setUp(self):
        self.fixture_path = SKILL_ROOT / "tests" / "fixtures" / "portfolio_25_funds.json"
        self.assertTrue(self.fixture_path.exists(), "Benchmark 25-fund fixture must exist")

    def test_clean_financial_number(self):
        """Test financial dirty number string parsing."""
        self.assertEqual(clean_financial_number("¥6,000.00"), 6000.0)
        self.assertEqual(clean_financial_number("(600.00)"), -600.0)
        self.assertEqual(clean_financial_number("-1,840.00"), -1840.0)
        self.assertEqual(clean_financial_number("+840.00"), 840.0)
        self.assertAlmostEqual(clean_financial_number("28.00%"), 0.28)
        self.assertEqual(clean_financial_number(1234.5), 1234.5)
        self.assertEqual(clean_financial_number(None), 0.0)
        self.assertEqual(clean_financial_number("invalid"), 0.0)

    def test_benchmark_fixture_integrity(self):
        """Test the canonical 25-fund JSON fixture mathematical ground truth."""
        with open(self.fixture_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.assertEqual(len(data["funds"]), 25, "Must contain exactly 25 funds")
        self.assertEqual(data["total_cost"], 100000.0)
        self.assertEqual(data["total_market_value"], 87000.0)
        self.assertEqual(data["total_pnl"], -13000.0)
        self.assertAlmostEqual(data["total_pnl_rate"], -0.13, places=4)

        # Count QDII parallel funds
        qdii_funds = [f for f in data["funds"] if f["category"] == "QDII并联纳指"]
        self.assertEqual(len(qdii_funds), 8, "Must contain 8 QDII parallel funds")
        self.assertEqual(sum(f["cost"] for f in qdii_funds), 35000.0)
        self.assertEqual(sum(f["market_value"] for f in qdii_funds), 31400.0)

        # Count Semiconductor funds
        chip_funds = [f for f in data["funds"] if "半导体" in f["category"]]
        self.assertEqual(len(chip_funds), 4, "Must contain 4 semiconductor funds")
        self.assertEqual(sum(f["cost"] for f in chip_funds), 25000.0)
        self.assertEqual(sum(f["market_value"] for f in chip_funds), 19790.0)

    def test_cli_help_flag(self):
        """Test --help CLI invocation."""
        parser = build_cli_parser()
        with io.StringIO() as buf, io.StringIO() as err:
            sys_stdout_bak = sys.stdout
            try:
                sys.stdout = buf
                with self.assertRaises(SystemExit) as cm:
                    parser.parse_args(["--help"])
                self.assertEqual(cm.exception.code, 0)
                help_text = buf.getvalue()
                self.assertIn("ethan-hold", help_text)
                self.assertIn("--input", help_text)
                self.assertIn("--output", help_text)
                self.assertIn("--simulate-buy", help_text)
            finally:
                sys.stdout = sys_stdout_bak

    def test_cli_run_pipeline_default(self):
        """Test run_pipeline execution with default benchmark data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out_html = Path(tmpdir) / "test_dashboard.html"
            result = run_pipeline(
                input_path=self.fixture_path,
                output_path=out_html,
                quiet=True,
            )
            self.assertTrue(out_html.exists())
            self.assertGreater(out_html.stat().st_size, 20000)

            # Check penetration results
            pen = result["penetration"]
            self.assertEqual(pen["summary"]["total_funds_count"], 25)
            self.assertEqual(pen["summary"]["total_cost"], 100000.0)
            self.assertEqual(pen["summary"]["total_value"], 87000.0)
            self.assertEqual(pen["summary"]["floating_pnl"], -13000.0)
            self.assertAlmostEqual(pen["summary"]["floating_pnl_rate"], -0.13, places=4)

            # Check circuit breaker
            cb = result["circuit_breaker"]
            self.assertTrue(cb["is_tripped"])
            self.assertEqual(cb["max_severity"], "P0_CRITICAL")
            self.assertEqual(cb["cooling_off_hours"], 48)

    def test_cli_simulate_buy_blocked(self):
        """Test --simulate-buy on deep-loss fund triggers P0 CRITICAL block."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out_html = Path(tmpdir) / "test_sim.html"
            result = run_pipeline(
                input_path=self.fixture_path,
                output_path=out_html,
                simulate_buy="320007,5000",
                quiet=True,
            )
            sim = result["simulation"]
            self.assertIsNotNone(sim)
            self.assertEqual(sim["status"], "BLOCKED")
            self.assertEqual(sim["max_severity"], "P0_CRITICAL")
            self.assertEqual(sim["cooling_off_hours"], 48)
            self.assertIn("越跌越补", sim["intercept_reason"])

    def test_cli_simulate_buy_approved(self):
        """Test --simulate-buy on defensive bond fund is approved."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out_html = Path(tmpdir) / "test_sim_bond.html"
            result = run_pipeline(
                input_path=self.fixture_path,
                output_path=out_html,
                simulate_buy="000198,10000",
                quiet=True,
            )
            sim = result["simulation"]
            self.assertIsNotNone(sim)
            self.assertEqual(sim["status"], "APPROVED")

    def test_cli_json_output(self):
        """Test --json flag produces valid JSON on stdout."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out_html = Path(tmpdir) / "test_json.html"
            buf = io.StringIO()
            sys_stdout_bak = sys.stdout
            try:
                sys.stdout = buf
                exit_code = main([
                    "--input", str(self.fixture_path),
                    "--output", str(out_html),
                    "--json"
                ])
                self.assertEqual(exit_code, 0)
                captured = buf.getvalue()
                parsed = json.loads(captured)
                self.assertIn("portfolio_summary", parsed)
                self.assertIn("circuit_breaker", parsed)
                self.assertIn("top_10_stocks", parsed)
                self.assertEqual(parsed["portfolio_summary"]["total_cost"], 100000.0)
            finally:
                sys.stdout = sys_stdout_bak

    def test_cli_csv_input_parsing(self):
        """Test CLI with CSV input."""
        csv_content = """基金代码,基金名称,资产分类,行业赛道,投入本金,当前市值,浮动盈亏,收益率
000055,广发纳斯达克100ETF联接A,QDII并联纳指,海外美股科技,6000.00,5400.00,-600.00,-10.00%
320007,诺安成长混合,A股半导体重仓,A股半导体与芯片,8000.00,6160.00,-1840.00,-23.00%
000198,天弘同利债券(LOF)A,纯债流动性防守,纯债防守,1000.00,1020.00,20.00,2.00%
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "test_portfolio.csv"
            csv_path.write_text(csv_content, encoding="utf-8")
            out_html = Path(tmpdir) / "test_csv.html"

            result = run_pipeline(
                input_path=csv_path,
                output_path=out_html,
                quiet=True
            )
            self.assertEqual(result["penetration"]["summary"]["total_funds_count"], 3)
            self.assertEqual(result["penetration"]["summary"]["total_cost"], 15000.0)
            self.assertEqual(result["penetration"]["summary"]["total_value"], 12580.0)

    def test_cli_markdown_input_parsing(self):
        """Test CLI with Markdown table input."""
        md_content = """# 测试持仓
| 基金代码 | 基金名称 | 资产分类 | 行业赛道 | 投入本金 | 当前市值 | 浮动盈亏 | 收益率 |
| :---: | :--- | :--- | :--- | :---: | :---: | :---: | :---: |
| 000055 | 广发纳斯达克100ETF联接A | QDII并联纳指 | 海外美股科技 | 6000.00 | 5400.00 | -600.00 | -10.00% |
| 320007 | 诺安成长混合 | A股半导体重仓 | A股半导体与芯片 | 8000.00 | 6160.00 | -1840.00 | -23.00% |
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            md_path = Path(tmpdir) / "test_portfolio.md"
            md_path.write_text(md_content, encoding="utf-8")
            out_html = Path(tmpdir) / "test_md.html"

            result = run_pipeline(
                input_path=md_path,
                output_path=out_html,
                quiet=True
            )
            self.assertEqual(result["penetration"]["summary"]["total_funds_count"], 2)
            self.assertEqual(result["penetration"]["summary"]["total_cost"], 14000.0)

    def test_cli_file_not_found_handling(self):
        """Test non-existent input file returns exit code 1."""
        exit_code = main(["--input", "/path/to/non_existent_file.json", "--quiet"])
        self.assertEqual(exit_code, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
