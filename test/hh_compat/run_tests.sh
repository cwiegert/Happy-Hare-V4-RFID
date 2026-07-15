#!/bin/sh
# test/hh_compat/run_tests.sh
#
# Runs the Happy Hare compatibility harness against a local Happy Hare
# checkout. Defaults to ~/Documents/GitHub/Happy-Hare; override with
# HAPPY_HARE_PATH=/path/to/checkout to point at a different one.
#
# Tests skip cleanly (not fail) if no checkout is found, so this is safe
# to leave in a general test run on a machine without Happy Hare cloned.

set -e
cd "$(dirname "$0")"
python3 -m unittest discover -p "test_*.py" -v
