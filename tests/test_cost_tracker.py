"""
Tests for cost_tracker.py -- AI cost tracking system.
"""

import json
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "familyarchive"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from cost_tracker import CostTracker, MODEL_COSTS, get_tracker, reset_tracker


# ── CostTracker.record() ──────────────────────────────────────────────────────

class TestCostTrackerRecord:
    def test_record_accumulates_calls(self):
        """record() adds entries to the calls list."""
        tracker = CostTracker()
        tracker.record("gemini", "gemini-2.5-flash", 1000, 500, pipeline_step="transcribe")
        tracker.record("openai", "gpt-4o-mini", 2000, 300, pipeline_step="format")
        assert tracker.call_count == 2
        assert len(tracker.calls) == 2

    def test_record_captures_all_fields(self):
        """record() stores vendor, model, tokens, step, and file."""
        tracker = CostTracker()
        tracker.record("gemini", "gemini-2.5-flash", 1000, 500,
                       pipeline_step="transcribe", file_path="Letters/test.pdf")
        entry = tracker.calls[0]
        assert entry["vendor"] == "gemini"
        assert entry["model"] == "gemini-2.5-flash"
        assert entry["input_tokens"] == 1000
        assert entry["output_tokens"] == 500
        assert entry["pipeline_step"] == "transcribe"
        assert entry["file"] == "Letters/test.pdf"
        assert "timestamp" in entry

    def test_record_returns_cost(self):
        """record() returns the calculated cost for the call."""
        tracker = CostTracker()
        cost = tracker.record("gemini", "gemini-2.5-flash", 1_000_000, 1_000_000)
        # gemini-2.5-flash: $0.15/M input + $0.60/M output = $0.75
        assert abs(cost - 0.75) < 0.001

    def test_record_unknown_model_zero_cost(self):
        """record() uses zero cost for unknown models."""
        tracker = CostTracker()
        cost = tracker.record("custom", "unknown-model-v1", 1000, 500)
        assert cost == 0.0


# ── Cost calculation ──────────────────────────────────────────────────────────

class TestCostCalculation:
    def test_total_cost_single_call(self):
        """total_cost reflects the sum of all recorded calls."""
        tracker = CostTracker()
        tracker.record("openai", "gpt-4o", 1_000_000, 1_000_000)
        # gpt-4o: $2.50/M input + $10.00/M output = $12.50
        assert abs(tracker.total_cost - 12.50) < 0.01

    def test_total_cost_multiple_calls(self):
        """total_cost sums across multiple calls."""
        tracker = CostTracker()
        tracker.record("gemini", "gemini-2.5-flash", 1_000_000, 0)  # $0.15
        tracker.record("gemini", "gemini-2.5-flash", 0, 1_000_000)  # $0.60
        assert abs(tracker.total_cost - 0.75) < 0.001

    def test_total_tokens(self):
        """total_input_tokens and total_output_tokens sum correctly."""
        tracker = CostTracker()
        tracker.record("gemini", "gemini-2.5-flash", 1000, 500)
        tracker.record("openai", "gpt-4o-mini", 2000, 300)
        assert tracker.total_input_tokens == 3000
        assert tracker.total_output_tokens == 800

    def test_empty_tracker(self):
        """Empty tracker has zero cost and tokens."""
        tracker = CostTracker()
        assert tracker.total_cost == 0
        assert tracker.total_input_tokens == 0
        assert tracker.total_output_tokens == 0
        assert tracker.call_count == 0


# ── summary_by_step() ────────────────────────────────────────────────────────

class TestSummaryByStep:
    def test_groups_by_pipeline_step(self):
        """summary_by_step() groups calls by their pipeline_step."""
        tracker = CostTracker()
        tracker.record("gemini", "gemini-2.5-flash", 1000, 500, pipeline_step="transcribe")
        tracker.record("gemini", "gemini-2.5-flash", 2000, 300, pipeline_step="transcribe")
        tracker.record("openai", "gpt-4o-mini", 500, 100, pipeline_step="format")

        by_step = tracker.summary_by_step()
        assert "transcribe" in by_step
        assert "format" in by_step
        assert by_step["transcribe"]["calls"] == 2
        assert by_step["transcribe"]["input_tokens"] == 3000
        assert by_step["transcribe"]["output_tokens"] == 800
        assert by_step["format"]["calls"] == 1

    def test_empty_summary(self):
        """summary_by_step() returns empty dict for empty tracker."""
        tracker = CostTracker()
        assert tracker.summary_by_step() == {}


# ── save() / load ────────────────────────────────────────────────────────────

class TestSaveLoad:
    def test_save_creates_costs_json(self, tmp_path):
        """save() creates _costs.json in the dest root."""
        tracker = CostTracker()
        tracker.record("gemini", "gemini-2.5-flash", 1000, 500, pipeline_step="transcribe")
        tracker.save(tmp_path)

        costs_path = tmp_path / "_costs.json"
        assert costs_path.exists()

        with open(costs_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert len(data) == 1
        assert data[0]["total_calls"] == 1
        assert data[0]["total_input_tokens"] == 1000
        assert "transcribe" in data[0]["by_step"]

    def test_save_appends_to_existing(self, tmp_path):
        """save() appends to existing _costs.json (multiple sessions)."""
        tracker1 = CostTracker()
        tracker1.record("gemini", "gemini-2.5-flash", 1000, 500)
        tracker1.save(tmp_path)

        tracker2 = CostTracker()
        tracker2.record("openai", "gpt-4o", 2000, 300)
        tracker2.save(tmp_path)

        costs_path = tmp_path / "_costs.json"
        with open(costs_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert len(data) == 2

    def test_save_handles_corrupt_json(self, tmp_path):
        """save() recovers from corrupt _costs.json."""
        costs_path = tmp_path / "_costs.json"
        costs_path.write_text("not valid json{{{", encoding="utf-8")

        tracker = CostTracker()
        tracker.record("gemini", "gemini-2.5-flash", 1000, 500)
        tracker.save(tmp_path)

        with open(costs_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert len(data) == 1


# ── MODEL_COSTS ───────────────────────────────────────────────────────────────

class TestModelCosts:
    def test_has_expected_models(self):
        """MODEL_COSTS includes all expected models."""
        expected = [
            "gemini-2.5-flash", "gemini-2.5-pro",
            "gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini",
            "claude-haiku-4-5-20251001", "claude-sonnet-4-20250514",
        ]
        for model in expected:
            assert model in MODEL_COSTS, f"Missing model: {model}"

    def test_all_models_have_input_output(self):
        """Every model in MODEL_COSTS has both input and output costs."""
        for model, costs in MODEL_COSTS.items():
            assert "input" in costs, f"{model} missing 'input' cost"
            assert "output" in costs, f"{model} missing 'output' cost"
            assert costs["input"] >= 0
            assert costs["output"] >= 0


# ── get_tracker / reset_tracker ──────────────────────────────────────────────

class TestGlobalTracker:
    def test_get_tracker_returns_singleton(self):
        """get_tracker() returns the same instance on repeated calls."""
        reset_tracker()
        t1 = get_tracker()
        t2 = get_tracker()
        assert t1 is t2

    def test_reset_tracker_creates_new_instance(self):
        """reset_tracker() creates a fresh tracker."""
        reset_tracker()
        t1 = get_tracker()
        t1.record("gemini", "gemini-2.5-flash", 100, 50)
        assert t1.call_count == 1

        reset_tracker()
        t2 = get_tracker()
        assert t2.call_count == 0
        assert t1 is not t2


# ── print_summary() ──────────────────────────────────────────────────────────

class TestPrintSummary:
    def test_print_summary_empty(self, capsys):
        """print_summary() with no calls prints 'No AI API calls made.'"""
        tracker = CostTracker()
        tracker.print_summary()
        captured = capsys.readouterr()
        assert "No AI API calls made." in captured.out

    def test_print_summary_with_calls(self, capsys):
        """print_summary() with calls prints formatted output."""
        tracker = CostTracker()
        tracker.record("gemini", "gemini-2.5-flash", 1000, 500, pipeline_step="transcribe")
        tracker.print_summary()
        captured = capsys.readouterr()
        assert "AI Cost Summary" in captured.out
        assert "transcribe" in captured.out
        assert "TOTAL" in captured.out
