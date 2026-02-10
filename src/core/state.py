"""State persistence — saves/loads active_trades to disk."""

import json
import logging
import threading
from pathlib import Path

logger = logging.getLogger("state")


class StateManager:
    """Persist active_trades to JSON file. Load on startup, save after every trade event."""

    def __init__(self, state_dir: str = "state", filename: str = "active_trades.json"):
        self.state_dir = Path(__file__).resolve().parent.parent.parent / state_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.filepath = self.state_dir / filename
        self._lock = threading.Lock()

    def load_active_trades(self) -> dict:
        """Load active_trades from disk. Returns dict with 'crypto' and 'equity' keys."""
        if not self.filepath.exists():
            logger.info(f"No state file found at {self.filepath}, starting fresh")
            return {}
        try:
            with open(self.filepath) as f:
                data = json.load(f)
            total = sum(len(v) for v in data.values() if isinstance(v, dict))
            logger.info(f"Loaded {total} active trades from {self.filepath}")
            return data
        except Exception as e:
            logger.error(f"Failed to load state from {self.filepath}: {e}")
            return {}

    def save_active_trades(self, trades: dict):
        """Save active_trades to disk atomically. Merges with existing data."""
        with self._lock:
            try:
                # Load existing to merge (strategies save independently)
                existing = {}
                if self.filepath.exists():
                    try:
                        with open(self.filepath) as f:
                            existing = json.load(f)
                    except Exception:
                        pass

                existing.update(trades)

                tmp = self.filepath.with_suffix(".tmp")
                with open(tmp, "w") as f:
                    json.dump(existing, f, indent=2, default=str)
                tmp.replace(self.filepath)
            except Exception as e:
                logger.error(f"Failed to save state to {self.filepath}: {e}")
