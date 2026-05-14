"""Cost tracker — logs per-request model usage and generates comparison reports."""

import json
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path

COST_RATES = {
    "gemini-2.5-flash-lite": {"input": 0.075, "output": 0.30},
    "gemini-2.5-flash": {"input": 0.15, "output": 0.60},
    "gemini-2.5-pro": {"input": 1.25, "output": 10.00},
    "claude-sonnet-4-6": {"input": 3.00, "output": 15.00},
    "claude-opus-4-6": {"input": 15.00, "output": 75.00},
    "classifier": {"input": 0.075, "output": 0.30},
}


@dataclass
class RequestLog:
    prompt: str
    complexity_level: str
    complexity_score: float
    model_used: str
    input_tokens: int
    output_tokens: int
    latency_ms: float
    cost_usd: float
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    rates = COST_RATES.get(model, COST_RATES["gemini-2.5-flash"])
    return (input_tokens * rates["input"] + output_tokens * rates["output"]) / 1_000_000


@dataclass
class CostTracker:
    log_path: Path = field(default_factory=lambda: Path("router_cost_log.jsonl"))
    entries: list[RequestLog] = field(default_factory=list)

    def log_request(self, entry: RequestLog):
        self.entries.append(entry)
        with open(self.log_path, "a") as f:
            f.write(json.dumps(asdict(entry)) + "\n")

    def total_cost(self) -> float:
        return sum(e.cost_usd for e in self.entries)

    def cost_by_model(self) -> dict[str, float]:
        result: dict[str, float] = {}
        for e in self.entries:
            result[e.model_used] = result.get(e.model_used, 0) + e.cost_usd
        return result

    def generate_report(self) -> str:
        lines = [
            "## Cost Summary",
            "",
            f"**Total requests:** {len(self.entries)}",
            f"**Total cost:** ${self.total_cost():.6f}",
            "",
            "### By Model",
            "",
            "| Model | Requests | Cost |",
            "|-------|----------|------|",
        ]
        model_counts: dict[str, int] = {}
        for e in self.entries:
            model_counts[e.model_used] = model_counts.get(e.model_used, 0) + 1
        for model, cost in sorted(self.cost_by_model().items()):
            lines.append(f"| {model} | {model_counts[model]} | ${cost:.6f} |")

        lines.extend([
            "",
            "### By Complexity",
            "",
            "| Level | Count | Avg Cost |",
            "|-------|-------|----------|",
        ])
        for level in ("low", "medium_low", "medium", "medium_high", "high"):
            level_entries = [e for e in self.entries if e.complexity_level == level]
            if level_entries:
                avg = sum(e.cost_usd for e in level_entries) / len(level_entries)
                lines.append(f"| {level} | {len(level_entries)} | ${avg:.6f} |")

        return "\n".join(lines)
