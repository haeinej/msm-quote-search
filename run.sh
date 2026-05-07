#!/bin/bash
# MSM Valve Management System — Quick Start
cd "$(dirname "$0")"

echo "Starting MSM Valve Management System..."
echo "  → http://localhost:8000"
echo ""

python3 -m uvicorn web.server:app --host 0.0.0.0 --port 8000 --reload
