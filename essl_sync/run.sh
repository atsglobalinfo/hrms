#!/bin/bash
# Quick start eSSL receiver with environment variables

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Check if .env exists
if [ ! -f ".env" ]; then
    echo "❌ .env file not found!"
    echo "Please run setup.sh first and configure your API credentials"
    exit 1
fi

# Activate virtual environment
if [ ! -d "venv" ]; then
    echo "❌ Virtual environment not found. Running setup.sh..."
    ./setup.sh
fi

source venv/bin/activate

# Load environment variables
export $(cat .env | grep -v '^#' | xargs)

# Verify credentials
if [ -z "$API_KEY" ] || [ -z "$API_SECRET" ]; then
    echo "❌ API credentials not configured in .env"
    exit 1
fi

echo "=================================="
echo "Starting eSSL Receiver"
echo "=================================="
echo "Frappe URL: $FRAPPE_URL"
echo "Device ID: $DEVICE_ID"
echo "Port: 8080"
echo ""
echo "📝 Logs: /tmp/essl_sync.log"
echo "🏥 Health check: curl http://localhost:8080/health"
echo ""
echo "Press Ctrl+C to stop"
echo "=================================="
echo ""

# Run with gunicorn for production-like behavior
python3 receiver.py
