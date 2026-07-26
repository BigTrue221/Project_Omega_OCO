# -*- coding: utf-8 -*-
"""Tests for the OCO public capability contract."""

from pathlib import Path

try:
    from Project_Omega_OCO.oco.capability import OCOCapability
except ImportError:
    from oco.capability import OCOCapability


FIXTURES = Path(__file__).parent / "fixtures"


def test_plan_offline_returns_replayable_steps():
    cap = OCOCapability()
    result = cap.plan("写一个科幻小说大纲")

    assert result["mode"] == "offline"
    assert result["route"]["path"] == "oco"
    assert len(result["plan"]) >= 1
    assert any(item["tool"] == "CRITIC" for item in result["plan"])


def test_critic_offline_detects_error_markers():
    cap = OCOCapability()
    result = cap.critic("分析 OCO 架构", "Error: capability_missing", threshold=0.7)

    assert result["passed"] is False
    assert "error_marker_detected" in result["issues"]


def test_eval_route_mode_reads_jsonl_cases():
    cap = OCOCapability()
    result = cap.eval(FIXTURES / "eval_cases.jsonl", mode="route")

    assert result["total"] == 3
    assert result["passed"] >= 2
    assert result["results"][0]["route"]["path"] == "legacy"


def test_replay_jsonl_trace_summary():
    cap = OCOCapability()
    result = cap.replay(FIXTURES / "trace_sample.jsonl")

    assert result["replayable"] is True
    assert result["event_count"] == 5
    assert result["stages"]["critic"] == 1
    assert result["final_response"] == "已完成大纲生成。"

