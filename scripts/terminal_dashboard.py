"""Terminal live dashboard polling /metrics (Part E bonus)."""
import os
import time

import requests
from rich.console import Console
from rich.live import Live
from rich.table import Table

API_URL = os.getenv("API_URL", "http://localhost:8000")
STORE_ID = os.getenv("STORE_ID", "STORE_BLR_002")


def build_table() -> Table:
    table = Table(title=f"Live Metrics — {STORE_ID}")
    table.add_column("Metric")
    table.add_column("Value")
    try:
        res = requests.get(f"{API_URL}/stores/{STORE_ID}/metrics", timeout=5)
        res.raise_for_status()
        m = res.json()
        table.add_row("Unique visitors", str(m["unique_visitors"]))
        table.add_row("Conversion rate", f"{m['conversion_rate'] * 100:.1f}%")
        table.add_row("Queue depth", str(m["current_queue_depth"]))
        table.add_row("Abandonment rate", f"{m['abandonment_rate'] * 100:.1f}%")
    except Exception as exc:
        table.add_row("Error", str(exc))
    return table


def main():
    console = Console()
    with Live(build_table(), console=console, refresh_per_second=0.5) as live:
        while True:
            live.update(build_table())
            time.sleep(2)


if __name__ == "__main__":
    main()
