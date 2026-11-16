"""Optional, user-editable price table for cost estimates.

Prices are never hard-coded. To enable cost estimates create ``<data_dir>/config/llm_prices.json``::

    {"<model name>": {"prompt_per_1k_tokens_usd": 0.0, "completion_per_1k_tokens_usd": 0.0}}

The numbers are yours to fill from your provider's price list. Without an entry the cost is null.
"""

from __future__ import annotations

import json
from pathlib import Path


def estimate_cost_usd(
    model: str | None, prompt_tokens: int | None, completion_tokens: int | None, config_dir: Path
) -> float | None:
    path = config_dir / "llm_prices.json"
    if not model or prompt_tokens is None or completion_tokens is None or not path.is_file():
        return None
    try:
        prices = json.loads(path.read_text())[model]
        return prompt_tokens / 1000 * float(
            prices["prompt_per_1k_tokens_usd"]
        ) + completion_tokens / 1000 * float(prices["completion_per_1k_tokens_usd"])
    except (KeyError, ValueError, TypeError, OSError):
        return None
