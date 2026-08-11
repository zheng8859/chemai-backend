#!/usr/bin/env python3
"""run_evals — ChemAI 质量门禁评测脚本 (v0.5.0)

三层评测体系 + Golden 数据集：
  L1 — 单元测试 + 覆盖率（目标 ≥ 95%）
  L2 — 集成测试 + 数据库 CRUD（目标通过率 ≥ 90%）
  L3 — Golden 评测 + 回归基线（目标准确率 ≥ 70%）

CI 模式下对比基线，任一指标劣化 > 5% 则阻断。

用法:
    python scripts/run_evals.py                  # 全量运行 L1+L2+L3
    python scripts/run_evals.py --level L1       # 仅 L1
    python scripts/run_evals.py --baseline       # 生成/更新基线文件
    python scripts/run_evals.py --save-baseline  # 同上（显式语义）
    python scripts/run_evals.py --ci             # CI 严格模式（对比基线，失败 exit 1）
    python scripts/run_evals.py --run-slow       # 启用 L3 @slow 测试（需 LLM API Key）
    python scripts/run_evals.py --compare <file> # 对比指定基线文件
    python scripts/run_evals.py --output report.html  # 生成 HTML 报告
    python scripts/run_evals.py --json           # JSON 格式输出结果
"""

import argparse
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Windows GBK 终端兼容: 强制 stdout/stderr 使用 UTF-8
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore

# ── 路径常量 ──────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
BASELINE_PATH = PROJECT_ROOT / "data" / "evals" / "baseline.json"
REPORTS_DIR = PROJECT_ROOT / "data" / "evals" / "reports"

# ── 质量门禁阈值 ──────────────────────────────────────────
THRESHOLDS = {
    "l1_coverage": 95.0,
    "l1_pass_rate": 100.0,    # 单元测试必须全绿
    "l2_pass_rate": 90.0,
    "l3_pass_rate": 70.0,
    "max_degradation_pct": 5.0,
}


# ═══════════════════════════════════════════════════════════
# 核心：运行 pytest
# ═══════════════════════════════════════════════════════════

def run_pytest(test_path: str, label: str, *,
               extra_args: list = None,
               timeout: int = 300) -> dict:
    """运行 pytest 并解析统计结果。

    通过解析 pytest 摘要行获取 passed/failed/errors/skipped 计数，
    不依赖额外插件。
    """
    start = time.monotonic()
    cmd = [
        sys.executable, "-m", "pytest", test_path,
        "-v", "--tb=short", "--no-header",
    ]
    if extra_args:
        cmd.extend(extra_args)

    try:
        proc = subprocess.run(
            cmd,
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {
            "label": label,
            "total": 0, "passed": 0, "failed": 0,
            "errors": 1, "skipped": 0,
            "pass_rate": 0.0,
            "elapsed_s": round(timeout, 1),
            "exit_code": -1,
            "error": f"超时 ({timeout}s)",
        }

    elapsed = round(time.monotonic() - start, 1)
    stdout = proc.stdout
    stderr = proc.stderr

    # 解析 pytest 摘要行： "= X passed, Y failed, Z errors in W.WWs ="
    passed = failed = errors = skipped = 0
    summary_match = re.search(
        r'=+\s*(\d+)\s+passed[,，]\s*(\d+)\s+failed',
        stdout
    )
    if not summary_match:
        # 尝试 "X passed" 单独模式
        summary_match = re.search(r'(\d+)\s+passed', stdout)

    if summary_match:
        passed = int(summary_match.group(1))
        if summary_match.lastindex and summary_match.lastindex >= 2:
            failed = int(summary_match.group(2))
        else:
            # 单独匹配 failed
            fm = re.search(r'(\d+)\s+failed', stdout)
            if fm:
                failed = int(fm.group(1))

    em = re.search(r'(\d+)\s+errors?', stdout)
    if em:
        errors = int(em.group(1))

    sm = re.search(r'(\d+)\s+skipped', stdout)
    if sm:
        skipped = int(sm.group(1))

    # 处理 "no tests ran" 场景
    if passed == 0 and failed == 0 and "no tests ran" in stdout.lower():
        total = 0
        pass_rate = 100.0  # 没有测试 = 不扣分
    else:
        total = passed + failed + errors
        pass_rate = round(passed / total * 100, 2) if total > 0 else 100.0

    # 提取失败摘要 (最后 2000 字符)
    failure_tail = ""
    if failed > 0 or errors > 0:
        failure_tail = stdout[-2000:]

    return {
        "label": label,
        "total": total,
        "passed": passed,
        "failed": failed,
        "errors": errors,
        "skipped": skipped,
        "pass_rate": pass_rate,
        "elapsed_s": elapsed,
        "exit_code": proc.returncode,
        "failure_tail": failure_tail,
        "stderr_tail": stderr[-500:] if stderr else "",
    }


def run_coverage(sources: list, test_path: str,
                 label: str, timeout: int = 300) -> dict:
    """运行 pytest --cov 并解析覆盖率百分比。

    使用 pytest-cov（已在 requirements.txt），
    同时输出 term 和 json 报告，优先从 json 解析。
    """
    cov_json_path = PROJECT_ROOT / "coverage_eval.json"
    # 清理旧文件
    if cov_json_path.exists():
        cov_json_path.unlink()

    start = time.monotonic()
    cmd = [
        sys.executable, "-m", "pytest", test_path,
        "-q", "--no-header", "--tb=short",
        "--cov-report", f"json:{cov_json_path}",
        "--cov-report", "term",
    ]
    for src in sources:
        cmd.extend(["--cov", src])

    try:
        proc = subprocess.run(
            cmd,
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {
            "label": label,
            "coverage_pct": 0.0,
            "elapsed_s": round(timeout, 1),
            "error": f"超时 ({timeout}s)",
        }

    elapsed = round(time.monotonic() - start, 1)

    # 优先从 JSON 解析
    coverage_pct = 0.0
    if cov_json_path.exists():
        try:
            cov_data = json.loads(cov_json_path.read_text(encoding="utf-8"))
            summary = cov_data.get("totals", {})
            coverage_pct = round(summary.get("percent_covered", 0.0), 2)
        except (json.JSONDecodeError, KeyError):
            pass
        finally:
            # 清理临时文件
            if cov_json_path.exists():
                cov_json_path.unlink()

    # Fallback: 从终端输出解析 TOTAL 行
    if coverage_pct == 0.0:
        m = re.search(r'TOTAL\s+\d+\s+\d+\s+(\d+)%', proc.stdout)
        if m:
            coverage_pct = float(m.group(1))

    return {
        "label": label,
        "coverage_pct": coverage_pct,
        "elapsed_s": elapsed,
    }


# ═══════════════════════════════════════════════════════════
# 基线管理
# ═══════════════════════════════════════════════════════════

def load_baseline() -> dict | None:
    """加载基线文件，不存在则返回 None。"""
    if not BASELINE_PATH.exists():
        return None
    try:
        return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def save_baseline(data: dict) -> None:
    """写入基线文件。"""
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def extract_scores(results: dict) -> dict:
    """从完整结果中提取可对比的关键得分。"""
    scores = {}

    l1_cov = results.get("l1_coverage", {})
    scores["l1_coverage_pct"] = l1_cov.get("coverage_pct", 0.0)

    l1_unit = results.get("l1_unit", {})
    scores["l1_pass_rate"] = l1_unit.get("pass_rate", 0.0)
    scores["l1_total"] = l1_unit.get("total", 0)

    l2 = results.get("l2_integration", {})
    scores["l2_pass_rate"] = l2.get("pass_rate", 100.0)
    scores["l2_total"] = l2.get("total", 0)

    l3 = results.get("l3_golden", {})
    scores["l3_pass_rate"] = l3.get("pass_rate", 100.0)
    scores["l3_total"] = l3.get("total", 0)

    return scores


def build_baseline(results: dict) -> dict:
    """从评测结果构建基线文件。"""
    return {
        "meta": {
            "version": "0.5.0",
            "created": datetime.now(timezone.utc).isoformat(),
            "description": "v0.5.0 质量门禁基线 — Golden 100 样本 + L1/L2/L3 三层评测",
        },
        "config": THRESHOLDS,
        "scores": extract_scores(results),
    }


def compare_to_baseline(current_scores: dict, baseline: dict) -> dict:
    """对比当前得分与基线，检测劣化。

    返回每条指标的对比结果和 overall pass/fail。
    """
    config = baseline.get("config", THRESHOLDS)
    base_scores = baseline.get("scores", {})
    max_deg = config.get("max_degradation_pct", 5.0)

    # 定义对比指标
    metrics = [
        ("L1", "覆盖率", "l1_coverage_pct", config["l1_coverage"]),
        ("L1", "单元测试通过率", "l1_pass_rate", config["l1_pass_rate"]),
        ("L2", "集成测试通过率", "l2_pass_rate", config["l2_pass_rate"]),
        ("L3", "Golden 准确率", "l3_pass_rate", config["l3_pass_rate"]),
    ]

    checks = []
    for layer, name, key, threshold in metrics:
        current_val = current_scores.get(key, 0.0)
        baseline_val = base_scores.get(key, 0.0)
        degradation = round(baseline_val - current_val, 2)

        # 劣化检查：当前值 vs 基线（基线对比只关心劣化，阈值由各层独立判定）
        degradation_pass = degradation <= max_deg

        checks.append({
            "layer": layer,
            "metric": name,
            "key": key,
            "current": current_val,
            "baseline": baseline_val,
            "threshold": threshold,
            "degradation": degradation,
            "degradation_pass": degradation_pass,
            "overall_pass": degradation_pass,
        })

    all_pass = all(c["overall_pass"] for c in checks)
    return {
        "all_pass": all_pass,
        "max_degradation_pct": max_deg,
        "checks": checks,
    }


# ═══════════════════════════════════════════════════════════
# 评测编排
# ═══════════════════════════════════════════════════════════

def run_l1(results: dict) -> None:
    """L1: 单元测试 + 覆盖率。"""
    print("=" * 60)
    print("L1 — 单元测试 + 覆盖率")
    print("=" * 60)

    # 1a. 单元测试
    unit = run_pytest("tests/unit", "L1 单元测试")
    results["l1_unit"] = unit
    _print_test_result(unit, "单元测试")

    # 1b. 覆盖率
    print("  计算覆盖率 (app + chem_skills)...")
    cov = run_coverage(
        sources=["app", "chem_skills"],
        test_path="tests/unit",
        label="L1 覆盖率",
        timeout=300,
    )
    results["l1_coverage"] = cov

    coverage_ok = cov["coverage_pct"] >= THRESHOLDS["l1_coverage"]
    print(f"  覆盖率: {cov['coverage_pct']}% "
          f"(目标 ≥ {THRESHOLDS['l1_coverage']}%)  "
          f"{'✓' if coverage_ok else '✗ 未达标'}")

    # 1c. 判定
    unit_ok = unit["failed"] == 0 and unit["errors"] == 0
    l1_ok = unit_ok and coverage_ok
    results["l1_verdict"] = {
        "passed": l1_ok,
        "unit_ok": unit_ok,
        "coverage_ok": coverage_ok,
    }
    if not l1_ok:
        reasons = []
        if not unit_ok:
            reasons.append(f"{unit['failed']} 失败 / {unit['errors']} 错误")
        if not coverage_ok:
            reasons.append(f"覆盖率 {cov['coverage_pct']}% < {THRESHOLDS['l1_coverage']}%")
        print(f"  ⚠ L1 未通过: {'; '.join(reasons)}")


def run_l2(results: dict) -> None:
    """L2: 集成测试。"""
    print("\n" + "=" * 60)
    print("L2 — 集成测试")
    print("=" * 60)

    integ = run_pytest("tests/integration", "L2 集成测试", timeout=600)
    results["l2_integration"] = integ
    _print_test_result(integ, "集成测试")

    l2_ok = integ["pass_rate"] >= THRESHOLDS["l2_pass_rate"]
    results["l2_verdict"] = {
        "passed": l2_ok,
        "pass_rate": integ["pass_rate"],
    }
    if not l2_ok:
        print(f"  ⚠ L2 未通过: 通过率 {integ['pass_rate']}% < {THRESHOLDS['l2_pass_rate']}%")


def run_l3(results: dict, run_slow: bool = False) -> None:
    """L3: Golden 评测（含 tests/golden + tests/evals/regression + tests/evals/baseline DB）。"""
    print("\n" + "=" * 60)
    print("L3 — Golden 评测")
    print("=" * 60)

    extra_args = []
    if run_slow:
        extra_args.append("--run-slow")
        print("  [--run-slow] 启用 L3 @slow 测试")

    # 先跑原有 tests/golden（不传 --run-slow，旧的 conftest 不支持）
    golden = run_pytest("tests/golden", "L3 Golden 原有", timeout=180)
    results["l3_golden_legacy"] = golden
    _print_test_result(golden, "Golden 原有")

    # 再跑新增 tests/evals/regression (L3 + slow)
    evals_regression = run_pytest(
        "tests/evals/regression", "L3 Evals 回归",
        timeout=300, extra_args=extra_args,
    )
    results["l3_evals_regression"] = evals_regression
    _print_test_result(evals_regression, "Evals 回归")

    # 跑 tests/evals/baseline 中的 L3 DB 测试
    evals_baseline = run_pytest(
        "tests/evals/baseline", "L3 Evals DB CRUD",
        timeout=60, extra_args=extra_args,
    )
    results["l3_evals_baseline"] = evals_baseline
    _print_test_result(evals_baseline, "Evals DB CRUD")

    # 汇总 L3
    total = (golden.get("total", 0) + evals_regression.get("total", 0)
             + evals_baseline.get("total", 0))
    passed = (golden.get("passed", 0) + evals_regression.get("passed", 0)
              + evals_baseline.get("passed", 0))
    failed = (golden.get("failed", 0) + evals_regression.get("failed", 0)
              + evals_baseline.get("failed", 0))
    errors = (golden.get("errors", 0) + evals_regression.get("errors", 0)
              + evals_baseline.get("errors", 0))

    total_with_fail = passed + failed + errors
    pass_rate = round(passed / total_with_fail * 100, 2) if total_with_fail > 0 else 100.0

    combined = {
        "label": "L3 汇总",
        "total": total, "passed": passed, "failed": failed,
        "errors": errors, "pass_rate": pass_rate,
    }
    results["l3_golden"] = combined

    l3_ok = pass_rate >= THRESHOLDS["l3_pass_rate"]
    results["l3_verdict"] = {
        "passed": l3_ok,
        "pass_rate": pass_rate,
    }
    print(f"  → L3 汇总通过率: {pass_rate}% (目标 ≥ {THRESHOLDS['l3_pass_rate']}%)  "
          f"{'✓' if l3_ok else '✗ 未达标'}")


def _print_test_result(r: dict, tag: str) -> None:
    """格式化打印单层测试结果。"""
    status = "✓" if r.get("failed", 0) == 0 and r.get("errors", 0) == 0 else "✗"
    print(f"  {status} {tag}: {r['passed']}/{r['total']} 通过, "
          f"{r['failed']} 失败, {r['errors']} 错误, "
          f"{r['skipped']} 跳过 ({r['pass_rate']}%)  [{r['elapsed_s']}s]")


# ═══════════════════════════════════════════════════════════
# 判定与输出
# ═══════════════════════════════════════════════════════════

def compute_verdict(results: dict, baseline_result: dict | None) -> dict:
    """根据各层结果和基线对比计算最终 verdict。

    只检查实际运行了的层级，未运行的层跳过。
    """
    levels_run = set(results.get("meta", {}).get("levels_run", ["L1", "L2", "L3"]))
    failures = []

    # L1: 仅当 L1 被运行时检查
    if "L1" in levels_run:
        l1v = results.get("l1_verdict", {})
        if not l1v.get("passed", False):
            if not l1v.get("unit_ok", False):
                u = results.get("l1_unit", {})
                failures.append(
                    f"L1 单元测试 {u.get('failed', 0)} 失败 / {u.get('errors', 0)} 错误"
                )
            if not l1v.get("coverage_ok", False):
                cov = results.get("l1_coverage", {})
                failures.append(
                    f"L1 覆盖率 {cov.get('coverage_pct', 0)}% < {THRESHOLDS['l1_coverage']}%"
                )

    # L2: 仅当 L2 被运行时检查
    if "L2" in levels_run:
        l2v = results.get("l2_verdict", {})
        if not l2v.get("passed", False):
            l2 = results.get("l2_integration", {})
            failures.append(
                f"L2 通过率 {l2.get('pass_rate', 0)}% < {THRESHOLDS['l2_pass_rate']}%"
            )

    # L3: 仅当 L3 被运行时检查
    if "L3" in levels_run:
        l3v = results.get("l3_verdict", {})
        if not l3v.get("passed", False):
            l3 = results.get("l3_golden", {})
            failures.append(
                f"L3 准确率 {l3.get('pass_rate', 0)}% < {THRESHOLDS['l3_pass_rate']}%"
            )

    # 基线对比: 仅检查劣化（阈值已在各层判定）
    if baseline_result:
        if not baseline_result.get("all_pass", False):
            for c in baseline_result.get("checks", []):
                if not c.get("degradation_pass", False):
                    failures.append(
                        f"基线劣化: {c['layer']} {c['metric']} "
                        f"(劣化 {c['degradation']}%, 最大允许 {baseline_result.get('max_degradation_pct', 5.0)}%)"
                    )

    passed = len(failures) == 0
    return {
        "passed": passed,
        "failures": failures,
        "summary": "✓ 全部通过" if passed else f"✗ {len(failures)} 项未通过",
    }


def save_html_report(results: dict, output_path: Path) -> Path:
    """生成单文件 HTML 评测报告（内嵌 CSS，颜色编码绿/黄/红）。"""
    verdict = results.get("verdict", {})
    passed = verdict.get("passed", False)
    baseline = results.get("baseline_comparison", {})

    status_color = "#22c55e" if passed else "#ef4444"
    status_text = "✓ 通过" if passed else "✗ 未通过"

    # 构建各层结果 HTML
    def _layer_row(label, data, threshold=None):
        if not data:
            return ""
        pr = data.get("pass_rate", data.get("coverage_pct", 0))
        t = data.get("total", 0)
        p = data.get("passed", 0)
        f = data.get("failed", 0)
        e = data.get("errors", 0)
        s = data.get("skipped", 0)
        elapsed = data.get("elapsed_s", 0)

        # 颜色判断
        if threshold is not None and pr >= threshold:
            color = "#22c55e"
        elif threshold is not None and pr >= threshold * 0.9:
            color = "#eab308"
        elif threshold is not None:
            color = "#ef4444"
        else:
            color = "#94a3b8"

        return f"""
        <tr>
          <td>{label}</td>
          <td>{t}</td><td>{p}</td><td>{f}</td><td>{e}</td><td>{s}</td>
          <td style="color:{color};font-weight:700">{pr}%</td>
          <td>{elapsed}s</td>
        </tr>"""

    layers_html = ""
    layers_html += _layer_row("L1 单元测试", results.get("l1_unit", {}), THRESHOLDS["l1_pass_rate"])
    layers_html += _layer_row("L1 覆盖率", results.get("l1_coverage", {}), THRESHOLDS["l1_coverage"])
    layers_html += _layer_row("L2 集成测试", results.get("l2_integration", {}), THRESHOLDS["l2_pass_rate"])
    layers_html += _layer_row("L3 Golden 原有", results.get("l3_golden_legacy", {}))
    layers_html += _layer_row("L3 Evals 回归", results.get("l3_evals_regression", {}))
    layers_html += _layer_row("L3 Evals DB CRUD", results.get("l3_evals_baseline", {}))
    layers_html += _layer_row("L3 汇总", results.get("l3_golden", {}), THRESHOLDS["l3_pass_rate"])

    # 基线对比
    baseline_rows = ""
    if baseline:
        for c in baseline.get("checks", []):
            icon = "✓" if c["degradation_pass"] else "✗"
            bg = "#dcfce7" if c["degradation_pass"] else "#fee2e2"
            baseline_rows += f"""
            <tr style="background:{bg}">
              <td>{c['layer']}</td><td>{c['metric']}</td>
              <td>{c['current']}%</td><td>{c['baseline']}%</td>
              <td>{c['degradation']}%</td>
              <td>{icon}</td>
            </tr>"""

    # 失败项
    failures_html = ""
    for f_text in verdict.get("failures", []):
        failures_html += f"<li>{f_text}</li>"

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ChemAI 质量门禁报告 — v0.5.0</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
       background:#f8fafc; color:#1e293b; padding:2rem; }}
.container {{ max-width:960px; margin:0 auto; }}
.header {{ background:#fff; border-radius:12px; padding:2rem; margin-bottom:1.5rem;
          box-shadow: 0 1px 3px rgba(0,0,0,.1); }}
.header h1 {{ font-size:1.5rem; margin-bottom:.5rem; }}
.status {{ display:inline-block; padding:.25rem .75rem; border-radius:999px;
          color:#fff; background:{status_color}; font-size:.875rem; }}
.meta {{ color:#64748b; font-size:.875rem; margin-top:.5rem; }}
.card {{ background:#fff; border-radius:12px; padding:1.5rem; margin-bottom:1.5rem;
        box-shadow: 0 1px 3px rgba(0,0,0,.1); }}
.card h2 {{ font-size:1.1rem; margin-bottom:1rem; color:#334155; }}
table {{ width:100%; border-collapse:collapse; }}
th, td {{ text-align:left; padding:.5rem .75rem; border-bottom:1px solid #e2e8f0;
         font-size:.875rem; }}
th {{ background:#f1f5f9; font-weight:600; color:#475569; }}
.failures {{ background:#fef2f2; border-left:3px solid #ef4444; padding:1rem;
            border-radius:8px; margin-top:1rem; }}
.failures h3 {{ color:#dc2626; margin-bottom:.5rem; }}
.failures li {{ margin-left:1.5rem; margin-bottom:.25rem; color:#7f1d1d; }}
.footer {{ text-align:center; color:#94a3b8; font-size:.75rem; margin-top:2rem; }}
@media (max-width:640px) {{ body {{ padding:1rem; }} table {{ font-size:.75rem; }} }}
</style>
</head>
<body>
<div class="container">
<div class="header">
  <h1>ChemAI 质量门禁评测报告</h1>
  <span class="status">{status_text}</span>
  <div class="meta">
    版本 v0.5.0 &nbsp;|&nbsp;
    时间 {results.get('meta', {}).get('timestamp', '')} &nbsp;|&nbsp;
    模式 {results.get('meta', {}).get('mode', '')}
  </div>
</div>

<div class="card">
  <h2>测试结果</h2>
  <table>
    <thead><tr>
      <th>层级</th><th>总数</th><th>通过</th><th>失败</th><th>错误</th><th>跳过</th><th>通过率</th><th>耗时</th>
    </tr></thead>
    <tbody>{layers_html}
    </tbody>
  </table>
</div>
{""
if not baseline_rows else f'''
<div class="card">
  <h2>基线对比</h2>
  <table>
    <thead><tr>
      <th>层级</th><th>指标</th><th>当前</th><th>基线</th><th>劣化</th><th>判定</th>
    </tr></thead>
    <tbody>{baseline_rows}
    </tbody>
  </table>
</div>
'''}
{""
if not failures_html else f'''
<div class="failures">
  <h3>未通过项</h3>
  <ul>{failures_html}</ul>
</div>
'''}

<div class="footer">
  ChemAI Evals v0.5.0 · Golden 100 样本 · L1/L2/L3 三层门禁 ·
  Generated by run_evals.py
</div>
</div>
</body>
</html>"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    return output_path


def save_report(results: dict) -> Path:
    """保存评测报告到 data/evals/reports/。"""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = REPORTS_DIR / f"eval_{ts}.json"
    # 移除冗余的 stdout/stderr 以减少报告体积
    slim = _slim_results(results)
    path.write_text(
        json.dumps(slim, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    return path


def _slim_results(results: dict) -> dict:
    """精简结果：去掉长文本 tail 字段，保留关键统计数据。"""
    out = {}
    for k, v in results.items():
        if isinstance(v, dict):
            out[k] = {
                kk: vv for kk, vv in v.items()
                if not kk.endswith("_tail")
            }
        else:
            out[k] = v
    return out


# ═══════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        description="ChemAI 质量门禁评测脚本 (v0.5.0)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python scripts/run_evals.py                     全量运行 L1+L2+L3
  python scripts/run_evals.py --level L1          仅运行 L1
  python scripts/run_evals.py --baseline          生成基线文件
  python scripts/run_evals.py --save-baseline     生成基线文件（显式语义）
  python scripts/run_evals.py --ci                严格 CI 模式
  python scripts/run_evals.py --run-slow          启用 L3 @slow 测试
  python scripts/run_evals.py --compare baseline.json  对比指定基线
  python scripts/run_evals.py --output report.html     生成 HTML 报告
        """,
    )
    parser.add_argument(
        "--level", choices=["L1", "L2", "L3", "all"],
        default="all",
        help="运行层级 (默认: all)",
    )
    parser.add_argument(
        "--baseline", action="store_true",
        help="生成/更新基线文件 data/evals/baseline.json",
    )
    parser.add_argument(
        "--save-baseline", action="store_true",
        help="同 --baseline，显式语义别名",
    )
    parser.add_argument(
        "--ci", action="store_true",
        help="CI 严格模式：必须对比基线通过才 exit 0",
    )
    parser.add_argument(
        "--run-slow", action="store_true",
        help="启用 L3 @slow 标记测试（需设置 LLM API Key 环境变量）",
    )
    parser.add_argument(
        "--compare", type=str, metavar="FILE",
        help="对比指定的基线 JSON 文件（而非默认 data/evals/baseline.json）",
    )
    parser.add_argument(
        "--output", type=str, metavar="PATH",
        help="生成 HTML 单文件报告到指定路径",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="以 JSON 格式输出最终结果到 stdout",
    )
    args = parser.parse_args()

    # --save-baseline 是 --baseline 的别名
    save_baseline_mode = args.baseline or args.save_baseline

    # 确定要运行的层级
    levels = {"L1", "L2", "L3"} if args.level == "all" else {args.level}

    print(f"\n  ChemAI 质量门禁评测 — v0.5.0")
    print(f"  层级: {args.level}  |  项目: {PROJECT_ROOT.name}")
    if args.run_slow:
        print(f"  [--run-slow] L3 @slow 已启用")
    print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    results: dict = {
        "meta": {
            "tool": "run_evals",
            "version": "0.5.0",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "project_root": str(PROJECT_ROOT),
            "levels_run": sorted(levels),
            "mode": "baseline" if save_baseline_mode else ("ci" if args.ci else "check"),
            "run_slow": args.run_slow,
        },
    }

    # 按 L1 → L2 → L3 顺序执行
    if "L1" in levels:
        run_l1(results)

    if "L2" in levels:
        run_l2(results)

    if "L3" in levels:
        run_l3(results, run_slow=args.run_slow)

    # 基线对比 (CI 或 baseline 模式)
    baseline_comparison = None
    compare_path = None
    if args.compare:
        compare_path = Path(args.compare)
        if not compare_path.is_absolute():
            compare_path = PROJECT_ROOT / compare_path

    if args.ci or save_baseline_mode or args.compare:
        if compare_path and compare_path.exists():
            baseline = json.loads(compare_path.read_text(encoding="utf-8"))
        else:
            baseline = load_baseline()
        if baseline:
            current_scores = extract_scores(results)
            baseline_comparison = compare_to_baseline(current_scores, baseline)
            results["baseline_comparison"] = baseline_comparison

            print("\n" + "=" * 60)
            print("基线对比")
            print("=" * 60)
            for c in baseline_comparison["checks"]:
                icon = "✓" if c["degradation_pass"] else "✗"
                print(f"  {icon} {c['layer']} {c['metric']}: "
                      f"当前 {c['current']}%  "
                      f"(基线 {c['baseline']}%, "
                      f"劣化 {c['degradation']}%)")

            if baseline_comparison["all_pass"]:
                print("  ✓ 基线对比通过 (无劣化)")
            else:
                failed_checks = [
                    c for c in baseline_comparison["checks"]
                    if not c["degradation_pass"]
                ]
                print(f"  ✗ 基线对比未通过 ({len(failed_checks)} 项)")
        elif args.ci and not compare_path:
            print("\n  ⚠ 基线文件不存在，CI 模式无法对比。"
                  "请先运行 --baseline 生成基线。")
            results["meta"]["baseline_fallback"] = True

    # --baseline / --save-baseline 模式：保存基线
    if save_baseline_mode:
        bl = build_baseline(results)
        if baseline_comparison:
            bl["scores"] = extract_scores(results)
        save_baseline(bl)
        print(f"\n  ✓ 基线已保存 → {BASELINE_PATH}")
        report_path = save_report(results)
        print(f"  报告: {report_path}")
        if args.output:
            html_path = Path(args.output)
            if not html_path.is_absolute():
                html_path = PROJECT_ROOT / html_path
            save_html_report(results, html_path)
            print(f"  HTML 报告: {html_path}")
        # baseline 模式不判定通过/失败，只是快照
        results["verdict"] = {
            "passed": True,
            "failures": [],
            "summary": "✓ 基线已保存 (快照模式，不判定)",
        }
        if args.json:
            print("\n--- JSON ---")
            print(json.dumps(results, ensure_ascii=False, indent=2, default=str))
        sys.exit(0)

    # 计算最终判定
    verdict = compute_verdict(results, baseline_comparison)
    results["verdict"] = verdict

    # 保存 JSON 报告
    report_path = save_report(results)
    results["report_path"] = str(report_path)

    # 生成 HTML 报告（如果指定 --output）
    if args.output:
        html_path = Path(args.output)
        if not html_path.is_absolute():
            html_path = PROJECT_ROOT / html_path
        save_html_report(results, html_path)
        results["html_report_path"] = str(html_path)

    # ── 输出 ──
    print(f"\n{'=' * 60}")
    print(f"判定: {verdict['summary']}")
    if verdict["failures"]:
        for f in verdict["failures"]:
            print(f"  • {f}")
    print(f"JSON 报告: {report_path}")
    if args.output:
        print(f"HTML 报告: {results.get('html_report_path', '')}")

    if args.json:
        print("\n--- JSON ---")
        print(json.dumps(results, ensure_ascii=False, indent=2, default=str))

    # 退出码: --ci 严格模式 or 普通检查模式
    sys.exit(0 if verdict["passed"] else 1)


if __name__ == "__main__":
    main()
