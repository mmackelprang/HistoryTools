"""
AI Cost Tracker -- records token usage and estimated costs from API calls.

Token counts are actual (from API response metadata). Dollar costs are
ESTIMATES based on published per-token pricing in MODEL_COSTS. Actual
billing may differ due to price changes, caching discounts, image token
pricing, or per-request minimums. Compare _costs.json totals against
your vendor dashboards for exact billing.

Costs are tracked per-call, rolled up by pipeline step and file,
and saved to _costs.json in the archive root.
"""

import json
import time
from pathlib import Path
from datetime import datetime

# Approximate cost per 1M tokens for each model (input/output)
MODEL_COSTS = {
    # Gemini
    "gemini-2.5-flash": {"input": 0.15, "output": 0.60},
    "gemini-2.5-pro": {"input": 2.50, "output": 10.00},
    # OpenAI
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4.1": {"input": 2.00, "output": 8.00},
    "gpt-4.1-mini": {"input": 0.40, "output": 1.60},
    # Anthropic
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.00},
    "claude-sonnet-4-20250514": {"input": 3.00, "output": 15.00},
}


class CostTracker:
    """Tracks AI API costs across a processing session."""

    def __init__(self):
        self.calls = []
        self.session_start = datetime.now().isoformat()

    def record(self, vendor, model, input_tokens, output_tokens, pipeline_step="unknown", file_path=None):
        """Record a single API call's usage."""
        costs = MODEL_COSTS.get(model, {"input": 0.0, "output": 0.0})
        input_cost = (input_tokens / 1_000_000) * costs["input"]
        output_cost = (output_tokens / 1_000_000) * costs["output"]
        total_cost = input_cost + output_cost

        entry = {
            "timestamp": datetime.now().isoformat(),
            "vendor": vendor,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": round(total_cost, 6),
            "pipeline_step": pipeline_step,
            "file": file_path,
        }
        self.calls.append(entry)
        return total_cost

    @property
    def total_cost(self):
        return sum(c["cost_usd"] for c in self.calls)

    @property
    def total_input_tokens(self):
        return sum(c["input_tokens"] for c in self.calls)

    @property
    def total_output_tokens(self):
        return sum(c["output_tokens"] for c in self.calls)

    @property
    def call_count(self):
        return len(self.calls)

    def summary_by_step(self):
        """Roll up costs by pipeline step."""
        by_step = {}
        for c in self.calls:
            step = c["pipeline_step"]
            if step not in by_step:
                by_step[step] = {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}
            by_step[step]["calls"] += 1
            by_step[step]["input_tokens"] += c["input_tokens"]
            by_step[step]["output_tokens"] += c["output_tokens"]
            by_step[step]["cost_usd"] += c["cost_usd"]
        return by_step

    def print_summary(self):
        """Print a formatted cost summary."""
        if not self.calls:
            print("No AI API calls made.")
            return

        print(f"\nAI Cost Summary ({self.call_count} calls)")
        print(f"{'=' * 50}")

        by_step = self.summary_by_step()
        for step, data in sorted(by_step.items()):
            print(f"  {step:30s} {data['calls']:3d} calls  ${data['cost_usd']:.4f}")

        print(f"  {'─' * 46}")
        print(f"  {'TOTAL':30s} {self.call_count:3d} calls  ${self.total_cost:.4f}")
        print(f"  Tokens: {self.total_input_tokens:,} in / {self.total_output_tokens:,} out")
        print(f"  (costs are estimates based on published per-token pricing)")

    def save(self, dest_root):
        """Append session costs to _costs.json in the archive root."""
        costs_path = Path(dest_root) / "_costs.json"

        existing = []
        if costs_path.exists():
            try:
                with open(costs_path, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            except (json.JSONDecodeError, IOError):
                existing = []

        session = {
            "session_start": self.session_start,
            "session_end": datetime.now().isoformat(),
            "total_calls": self.call_count,
            "total_cost_usd": round(self.total_cost, 6),
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "by_step": {k: {**v, "cost_usd": round(v["cost_usd"], 6)} for k, v in self.summary_by_step().items()},
            "calls": self.calls,
        }
        existing.append(session)

        with open(costs_path, "w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2, ensure_ascii=False)


# Global tracker instance (used by ai_client.py)
_tracker = None


def get_tracker():
    """Get or create the global cost tracker."""
    global _tracker
    if _tracker is None:
        _tracker = CostTracker()
    return _tracker


def reset_tracker():
    """Reset the global cost tracker (for testing)."""
    global _tracker
    _tracker = CostTracker()
