"""Entry point: python -m bbsyncer [--port /dev/ttyACM0] [--dry-run] [--web]

Usage:
  # Run the sync service (triggered by systemd/udev):
  python -m bbsyncer --port /dev/ttyACM0

  # Run the web server:
  python -m bbsyncer --web

  # Dry-run (copy but don't erase):
  python -m bbsyncer --port /dev/ttyACM0 --dry-run

  # Override config file:
  python -m bbsyncer --port /dev/ttyACM0 --config /etc/bbsyncer/bbsyncer.toml
"""
from __future__ import annotations

import argparse
import logging
import sys

from bbsyncer.config import load_config
from bbsyncer.led.controller import LEDController, LEDState
from bbsyncer.sync.orchestrator import SyncOrchestrator, SyncResult, auto_detect_port


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Betaflight Blackbox Field Syncer",
        prog="python -m bbsyncer",
    )
    parser.add_argument(
        "--port", "-p",
        default="",
        help="Serial port (e.g. /dev/ttyACM0). Empty = auto-detect.",
    )
    parser.add_argument(
        "--config", "-c",
        default="",
        help="Path to bbsyncer.toml config file.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Copy flash but skip erase step.",
    )
    parser.add_argument(
        "--web",
        action="store_true",
        help="Run the web server instead of sync.",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug logging.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    log = logging.getLogger("bbsyncer")

    cfg = load_config(args.config or None)

    # ------------------------------------------------------------------
    # Web server mode
    # ------------------------------------------------------------------
    if args.web:
        from bbsyncer.web.server import run_server
        run_server(storage_path=cfg.storage_path, port=cfg.web_port)
        return 0

    # ------------------------------------------------------------------
    # Sync mode
    # ------------------------------------------------------------------
    port = args.port or cfg.serial_port or auto_detect_port()
    if not port:
        log.error(
            "No serial port specified and no /dev/ttyACM* found. "
            "Use --port /dev/ttyACM0 or connect the FC."
        )
        return 1

    log.info("Starting sync on port %s (dry_run=%s)", port, args.dry_run)

    led = LEDController(backend=cfg.led_backend, gpio_pin=cfg.led_gpio_pin)
    led.start()

    try:
        orchestrator = SyncOrchestrator(cfg, led, dry_run=args.dry_run)
        result = orchestrator.run(port)
    finally:
        # Give LED a moment to complete its final pattern before stopping
        import time
        time.sleep(6)
        led.stop()

    exit_codes = {
        SyncResult.SUCCESS: 0,
        SyncResult.ALREADY_EMPTY: 0,
        SyncResult.DRY_RUN: 0,
        SyncResult.ERROR: 1,
    }
    code = exit_codes.get(result, 1)
    log.info("Sync result: %s (exit %d)", result.name, code)
    return code


if __name__ == "__main__":
    sys.exit(main())
