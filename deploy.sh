#!/bin/bash

# Wrapper script for deployment
# This script calls the actual deployment script in scripts/deployment/

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "${SCRIPT_DIR}/scripts/deployment/deploy.sh" "$@"