#!/bin/bash
# Run the simulated Carvera so the controller can connect without hardware.
#
#   ./scripts/sim.sh                # idle machine on 127.0.0.1:2222
#   ./scripts/sim.sh --load 0.7     # under heavy cutting load
#
# Then start the controller and connect to 127.0.0.1.
set -e

cd "$(dirname "$0")"
cd ..

PYTHONPATH=tools poetry run python -m carvera_sim "$@"
