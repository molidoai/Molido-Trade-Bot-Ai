#!/bin/bash
# Build one or more compose services inside a CPU-capped, low-priority slice.
#
# Unconstrained builds have repeatedly saturated this 2-core box to the point
# where nginx and sshd stopped responding -- users saw CDN 504s and SSH hung
# at banner exchange. The last such 504 timestamp matched a build exactly.
# Under molido-build.slice the site stays responsive throughout (measured
# ~0.5s while building); the build just takes longer, which is the right
# trade on a box this size.
set -euo pipefail
cd /opt/molido
[ $# -gt 0 ] || { echo "usage: $0 <service> [service...]" >&2; exit 1; }
echo "building (CPU-capped): $*"
# --working-directory is required: systemd-run starts the transient unit in
# / regardless of the caller's cwd, so compose would not find the project.
systemd-run --pipe --wait --collect \
  --slice=molido-build.slice \
  --unit="molido-build-$$" \
  --working-directory=/opt/molido \
  --property=CPUQuota=70% \
  --property=CPUWeight=50 \
  /usr/bin/docker compose build "$@"
echo "build done; restarting: $*"
docker compose up -d "$@"
