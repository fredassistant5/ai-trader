#!/usr/bin/env python3
"""AI Trader Health Monitor / Watchdog

Checks:
1. Process is alive (systemd service active)
2. Trading loop is functioning (heartbeat file freshness)
3. Log activity is recent
4. No duplicate instances

Logs health status to /var/log/ai-trader/health.log
Designed to run via cron every 2 minutes or as a systemd timer.
"""

import json
import logging
import os
import subprocess
import sys
import time
import fcntl
from datetime import datetime, timedelta
from pathlib import Path

# Paths
PROJECT_DIR = Path.home() / "clawd" / "projects" / "ai-trader"
STATE_DIR = PROJECT_DIR / "state"
LOG_DIR = Path("/var/log/ai-trader")
HEALTH_LOG = LOG_DIR / "health.log"
HEARTBEAT_FILE = STATE_DIR / "heartbeat.json"
LOCKFILE = Path("/tmp/ai-trader-health-monitor.lock")
ALERT_STATE_FILE = STATE_DIR / "alert_state.json"

# Thresholds
HEARTBEAT_MAX_AGE_SEC = 180  # 3 minutes
LOG_MAX_AGE_SEC = 300  # 5 minutes
MAX_CONSECUTIVE_FAILURES = 3

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(HEALTH_LOG),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("health_monitor")


def acquire_lock():
    """Prevent multiple monitor instances."""
    try:
        lock_fd = open(LOCKFILE, "w")
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        lock_fd.write(str(os.getpid()))
        lock_fd.flush()
        return lock_fd
    except (IOError, OSError):
        log.warning("Another health monitor instance is running. Exiting.")
        sys.exit(0)


def check_service_active() -> tuple[bool, str]:
    """Check if ai-trader.service is active."""
    try:
        result = subprocess.run(
            ["systemctl", "is-active", "ai-trader.service"],
            capture_output=True, text=True, timeout=10,
        )
        state = result.stdout.strip()
        return state == "active", state
    except Exception as e:
        return False, str(e)


def check_no_duplicate_processes() -> tuple[bool, int]:
    """Ensure only one trader process is running."""
    try:
        result = subprocess.run(
            ["pgrep", "-f", "python.*src\\.main"],
            capture_output=True, text=True, timeout=10,
        )
        pids = [p for p in result.stdout.strip().split("\n") if p]
        count = len(pids)
        return count <= 1, count
    except Exception:
        return True, 0


def check_heartbeat() -> tuple[bool, str]:
    """Check heartbeat file freshness."""
    if not HEARTBEAT_FILE.exists():
        return False, "no heartbeat file"
    try:
        data = json.loads(HEARTBEAT_FILE.read_text())
        ts = data.get("timestamp", 0)
        age = time.time() - ts
        if age > HEARTBEAT_MAX_AGE_SEC:
            return False, f"stale ({age:.0f}s old)"
        return True, f"fresh ({age:.0f}s old)"
    except Exception as e:
        return False, str(e)


def check_log_activity() -> tuple[bool, str]:
    """Check if trader log has recent writes."""
    trader_log = LOG_DIR / "trader.log"
    if not trader_log.exists():
        return False, "no log file"
    age = time.time() - trader_log.stat().st_mtime
    if age > LOG_MAX_AGE_SEC:
        return False, f"stale ({age:.0f}s)"
    return True, f"active ({age:.0f}s ago)"


def load_alert_state() -> dict:
    """Load persistent alert state."""
    if ALERT_STATE_FILE.exists():
        try:
            return json.loads(ALERT_STATE_FILE.read_text())
        except Exception:
            pass
    return {"consecutive_failures": 0, "last_alert": 0}


def save_alert_state(state: dict):
    """Save alert state."""
    ALERT_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    ALERT_STATE_FILE.write_text(json.dumps(state))


def send_alert(message: str):
    """Log critical alert. Extend with notification integration as needed."""
    log.critical(f"ALERT: {message}")
    # Future: integrate with Fred/main agent notification


def run_checks() -> bool:
    """Run all health checks. Returns True if healthy."""
    all_ok = True
    checks = {}

    # 1. Service active
    ok, detail = check_service_active()
    checks["service"] = (ok, detail)
    if not ok:
        log.error(f"Service not active: {detail}")
        all_ok = False

    # 2. No duplicates
    ok, count = check_no_duplicate_processes()
    checks["duplicates"] = (ok, f"{count} instances")
    if not ok:
        log.error(f"Multiple trader instances detected: {count}")
        all_ok = False

    # 3. Heartbeat
    ok, detail = check_heartbeat()
    checks["heartbeat"] = (ok, detail)
    if not ok:
        log.warning(f"Heartbeat check failed: {detail}")
        # Don't fail overall if service is active but heartbeat missing
        # (might not be implemented yet in trader)

    # 4. Log activity
    ok, detail = check_log_activity()
    checks["log_activity"] = (ok, detail)
    if not ok:
        log.warning(f"Log activity check failed: {detail}")

    # Summary
    status = "HEALTHY" if all_ok else "UNHEALTHY"
    summary = " | ".join(f"{k}={'OK' if v[0] else 'FAIL'}({v[1]})" for k, v in checks.items())
    log.info(f"Health: {status} — {summary}")

    return all_ok


def main():
    lock_fd = acquire_lock()

    log.info("Health monitor starting")
    healthy = run_checks()

    # Alert escalation
    state = load_alert_state()
    if not healthy:
        state["consecutive_failures"] += 1
        if state["consecutive_failures"] >= MAX_CONSECUTIVE_FAILURES:
            now = time.time()
            # Alert at most once per 10 minutes
            if now - state.get("last_alert", 0) > 600:
                send_alert(
                    f"AI Trader unhealthy for {state['consecutive_failures']} "
                    f"consecutive checks. Manual intervention may be needed."
                )
                state["last_alert"] = now
    else:
        if state["consecutive_failures"] > 0:
            log.info(f"Recovered after {state['consecutive_failures']} failures")
        state["consecutive_failures"] = 0

    save_alert_state(state)
    lock_fd.close()
    os.unlink(LOCKFILE)

    sys.exit(0 if healthy else 1)


if __name__ == "__main__":
    main()
