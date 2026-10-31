"""Token usage and cost tracking for BoardBridge LLM calls."""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class CostRecord(BaseModel):
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    estimated: bool = False
    latency_ms: float = 0.0
    cost_usd: float = 0.0
    success: bool = True
    fallback_used: bool = False
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


def calculate_cost(
    input_tokens: int,
    output_tokens: int,
    price_input_per_million: float,
    price_output_per_million: float,
) -> float:
    """Calculate cost in USD given token counts and prices per million tokens."""
    input_cost = (input_tokens * price_input_per_million) / 1_000_000.0
    output_cost = (output_tokens * price_output_per_million) / 1_000_000.0
    return round(input_cost + output_cost, 6)


def estimate_tokens(text: str) -> int:
    """Estimate token count at roughly 4 characters per token."""
    if not text:
        return 0
    return max(1, math.ceil(len(text) / 4.0))


def log_cost(record: CostRecord, log_path: str | Path = "logs/cost.jsonl") -> None:
    """Append a cost record to the JSONL log file, creating directories if needed."""
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record.model_dump()) + "\n")


def aggregate_usage(log_path: str | Path = "logs/cost.jsonl") -> dict[str, dict[str, Any]]:
    """Aggregate cost records from JSONL log file by UTC date."""
    path = Path(log_path)
    if not path.is_file():
        return {}

    daily_stats: dict[str, dict[str, Any]] = {}
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    raw_ts = data.get("timestamp", "")
                    if not raw_ts:
                        continue
                    # Extract date string YYYY-MM-DD from ISO format
                    dt = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
                    utc_date = dt.astimezone(timezone.utc).strftime("%Y-%m-%d")

                    if utc_date not in daily_stats:
                        daily_stats[utc_date] = {
                            "calls": 0,
                            "input_tokens": 0,
                            "output_tokens": 0,
                            "cost_usd": 0.0,
                        }

                    daily_stats[utc_date]["calls"] += 1
                    daily_stats[utc_date]["input_tokens"] += int(data.get("input_tokens", 0))
                    daily_stats[utc_date]["output_tokens"] += int(data.get("output_tokens", 0))
                    daily_stats[utc_date]["cost_usd"] = round(
                        daily_stats[utc_date]["cost_usd"] + float(data.get("cost_usd", 0.0)),
                        6,
                    )
                except Exception:
                    # Ignore malformed or corrupted log entries safely
                    continue
    except Exception:
        return {}

    return daily_stats

