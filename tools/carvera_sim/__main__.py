"""Run the simulator so the real controller can connect to it.

    python -m carvera_sim              # listen on 127.0.0.1:2222
    python -m carvera_sim --load 0.7   # start under heavy cutting load

Then point the controller at 127.0.0.1 to drive a machine that cannot be
damaged.
"""

from __future__ import annotations

import argparse
import logging
import time

from .machine import SimulatedMachine
from .server import TCP_PORT, CarveraSimServer


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulated Carvera machine")
    parser.add_argument("--port", type=int, default=TCP_PORT)
    parser.add_argument("--load", type=float, default=0.0, help="cutting load, 0.0 to 1.0")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    machine = SimulatedMachine()
    machine.load = args.load
    server = CarveraSimServer(machine, port=args.port)
    server.start_background()
    print(f"Simulated Carvera listening on 127.0.0.1:{server.port}")
    print("Connect the controller to that address. Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nstopping")
    finally:
        server.stop()


if __name__ == "__main__":
    main()
