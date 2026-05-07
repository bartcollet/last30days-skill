#!/bin/bash
# Wrapper script for last30days that fixes SSL certificate issues on macOS

# Set SSL certificate path to certifi's certificates
export SSL_CERT_FILE=$(python3 -c "import certifi; print(certifi.where())" 2>/dev/null)

# Run the actual last30days script with all arguments
python3 "$(dirname "$0")/scripts/last30days.py" "$@"
