#!/bin/bash
# Setup script for eSSL ADMS Receiver

set -e

echo "======================================"
echo "eSSL ADMS Receiver Setup"
echo "======================================"

# Check Python version
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 not found. Please install Python 3.7+"
    exit 1
fi

echo "✓ Python3 found: $(python3 --version)"

# Create virtual environment if not exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate venv
source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt

# Setup .env file
if [ ! -f ".env" ]; then
    echo "Creating .env file from template..."
    cp .env.example .env
    echo "⚠️  IMPORTANT: Edit .env file with your Frappe API credentials"
    echo "   - Get API Key from: Settings → My Account → API Access (in Frappe)"
    echo "   - Update FRAPPE_URL if needed"
else
    echo "✓ .env file already exists"
fi

echo ""
echo "======================================"
echo "Setup Complete!"
echo "======================================"
echo ""
echo "📋 Next Steps:"
echo "1. Edit .env file with your Frappe API credentials:"
echo "   nano .env"
echo ""
echo "2. Generate Frappe API Key:"
echo "   - Log in to http://localhost:8000"
echo "   - Go to Settings → My Account"
echo "   - Click 'API Access' → 'Generate Keys'"
echo "   - Copy API Key and Secret into .env"
echo ""
echo "3. Configure Employee IDs in Frappe:"
echo "   - Employee → Attendance & Leave Details"
echo "   - Set 'Attendance Device ID' to match eSSL device User IDs"
echo ""
echo "4. Configure eSSL Device Network (Menu → Comm → Ethernet):"
echo "   - Gateway: 192.168.1.1 (your router IP)"
echo "   - DNS: 8.8.8.8"
echo ""
echo "5. Configure ADMS on Device (Menu → Comm → ADMS):"
echo "   - Enable Domain Name: ON"
echo "   - Server Address: 192.168.1.XXX:8080 (your server IP)"
echo "   - Or use public domain if remote"
echo ""
echo "6. Run the receiver:"
echo "   python3 receiver.py"
echo ""
