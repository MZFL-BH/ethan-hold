#!/usr/bin/env python3
"""
run_all_e2e_tests.py — Unified Test Runner for ethan-hold 4-Tier E2E Test Suite.
Returns Exit Code 0 when all tests pass.
"""

import os
import sys
import time
import unittest
from pathlib import Path

# 1. 动态确保技能根目录 (SKILL_ROOT) 与当前测试目录处于 sys.path 最前端
CURRENT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = CURRENT_DIR.parent.parent

if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

# 2. 生产模块前置加载强校验（Pre-flight Hard Check）
REQUIRED_PROD_MODULES = [
    "scripts.penetration",
    "scripts.circuit_breaker",
    "scripts.generate_dashboard",
    "scripts.run_analysis",
]

missing_modules = []
for mod_name in REQUIRED_PROD_MODULES:
    try:
        __import__(mod_name)
    except ImportError as exc:
        missing_modules.append((mod_name, str(exc)))

if missing_modules:
    print("=" * 80, file=sys.stderr)
    print("❌ FATAL INTEGRITY ERROR: Production modules failed to load!", file=sys.stderr)
    print("E2E test suite MUST execute against real production scripts. Mock fallback is strictly prohibited.", file=sys.stderr)
    for mod_name, err in missing_modules:
        print(f"  - {mod_name}: {err}", file=sys.stderr)
    print("=" * 80, file=sys.stderr)
    sys.exit(1)

# 3. 正常导入各 Tier E2E 测试模块
import test_tier1_feature_coverage
import test_tier2_boundaries_and_corners
import test_tier3_pairwise_combinations
import test_tier4_real_world_scenarios

# 4. 后置校验：确保各 Tier 模块中的 PROD_MODULES_AVAILABLE 状态绝对为 True
for tier_mod, tier_label in [
    (test_tier2_boundaries_and_corners, "Tier 2"),
    (test_tier3_pairwise_combinations, "Tier 3"),
    (test_tier4_real_world_scenarios, "Tier 4"),
]:
    avail = getattr(tier_mod, "PROD_MODULES_AVAILABLE", None)
    if avail is not True:
        print(f"❌ INTEGRITY VIOLATION: {tier_label} has PROD_MODULES_AVAILABLE = {avail!r} (expected True)!", file=sys.stderr)
        sys.exit(1)



class E2EResultCollector(unittest.TestResult):
    def __init__(self):
        super().__init__()
        self.passed_tests = []
        self.failed_tests = []
        self.errored_tests = []
        self.skipped_tests = []
        self.tier_stats = {}

    def addSuccess(self, test):
        super().addSuccess(test)
        self.passed_tests.append(test)

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.failed_tests.append((test, err))

    def addError(self, test, err):
        super().addError(test, err)
        self.errored_tests.append((test, err))

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self.skipped_tests.append((test, reason))


def run_tier(suite: unittest.TestSuite, tier_name: str, collector: E2EResultCollector) -> dict:
    t0 = time.perf_counter()
    start_passes = len(collector.passed_tests)
    start_failures = len(collector.failed_tests)
    start_errors = len(collector.errored_tests)
    start_skips = len(collector.skipped_tests)

    suite.run(collector)

    duration = time.perf_counter() - t0
    tier_passes = len(collector.passed_tests) - start_passes
    tier_failures = len(collector.failed_tests) - start_failures
    tier_errors = len(collector.errored_tests) - start_errors
    tier_skips = len(collector.skipped_tests) - start_skips
    total = tier_passes + tier_failures + tier_errors + tier_skips

    stat = {
        "name": tier_name,
        "total": total,
        "passed": tier_passes,
        "failed": tier_failures,
        "errors": tier_errors,
        "skipped": tier_skips,
        "duration": duration,
        "status": "PASS" if (tier_failures == 0 and tier_errors == 0) else "FAIL"
    }
    collector.tier_stats[tier_name] = stat
    return stat


def print_banner():
    print("=" * 80)
    print("       ethan-hold (仓位罗盘) — 4-Tier Opaque-Box E2E Test Suite")
    print("=" * 80)
    print(f"Target Skill Workspace: /Users/wangbinghao/.gemini/config/skills/ethan-hold")
    print(f"Test Directory:         {CURRENT_DIR}")
    print(f"Python Runtime:         {sys.version.split()[0]} ({sys.executable})")
    print("-" * 80)


def print_summary_table(collector: E2EResultCollector, total_duration: float):
    print("\n" + "=" * 80)
    print("                         E2E TEST EXECUTION SUMMARY")
    print("=" * 80)
    header = f"{'Tier':<36} | {'Total':<6} | {'Pass':<6} | {'Skip':<6} | {'Fail':<6} | {'Time (s)':<8} | {'Status'}"
    print(header)
    print("-" * len(header))

    total_tests = 0
    total_passes = 0
    total_skips = 0
    total_fails = 0
    total_errors = 0

    for name, s in collector.tier_stats.items():
        total_tests += s["total"]
        total_passes += s["passed"]
        total_skips += s["skipped"]
        total_fails += s["failed"]
        total_errors += s["errors"]
        status_symbol = "🟢 PASS" if s["status"] == "PASS" else "🔴 FAIL"
        print(f"{s['name']:<36} | {s['total']:<6} | {s['passed']:<6} | {s['skipped']:<6} | {s['failed']:<6} | {s['duration']:<8.3f} | {status_symbol}")

    print("-" * len(header))
    overall_status = "🟢 ALL TESTS PASSED" if (total_fails == 0 and total_errors == 0) else "🔴 TESTS FAILED"
    print(f"{'OVERALL TOTALS':<36} | {total_tests:<6} | {total_passes:<6} | {total_skips:<6} | {total_fails:<6} | {total_duration:<8.3f} | {overall_status}")
    print("=" * 80)

    # Print skipped summary note if any
    if collector.skipped_tests:
        print(f"\n[Notice]: {len(collector.skipped_tests)} test(s) skipped pending corresponding milestone implementations:")
        skip_reasons = {}
        for _, r in collector.skipped_tests:
            skip_reasons[r] = skip_reasons.get(r, 0) + 1
        for reason, count in skip_reasons.items():
            print(f"  - ({count}x) {reason}")

    # Print failures if any
    if collector.failed_tests or collector.errored_tests:
        print("\n" + "!" * 80)
        print("                         TEST FAILURE DETAILS")
        print("!" * 80)
        for t, err in collector.failed_tests:
            print(f"\n[FAIL] {t.id()}:")
            print(err)
        for t, err in collector.errored_tests:
            print(f"\n[ERROR] {t.id()}:")
            print(err)


def main():
    print_banner()
    loader = unittest.TestLoader()
    collector = E2EResultCollector()

    t_start = time.perf_counter()

    # Tier 1
    t1_suite = loader.loadTestsFromModule(test_tier1_feature_coverage)
    run_tier(t1_suite, "Tier 1: Feature Coverage (20 Features)", collector)

    # Tier 2
    t2_suite = loader.loadTestsFromModule(test_tier2_boundaries_and_corners)
    run_tier(t2_suite, "Tier 2: Boundary & Corner Conditions", collector)

    # Tier 3
    t3_suite = loader.loadTestsFromModule(test_tier3_pairwise_combinations)
    run_tier(t3_suite, "Tier 3: Pairwise Cross-Feature Interactions", collector)

    # Tier 4
    t4_suite = loader.loadTestsFromModule(test_tier4_real_world_scenarios)
    run_tier(t4_suite, "Tier 4: Real-World Scenarios (25-Fund Benchmark)", collector)

    total_duration = time.perf_counter() - t_start
    print_summary_table(collector, total_duration)

    # Exit code: 0 if no failures and no errors
    if len(collector.failed_tests) == 0 and len(collector.errored_tests) == 0:
        print("\n✅ Verification Successful: Exit code 0.\n")
        return 0
    else:
        print("\n❌ Verification Failed: Exit code 1.\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
