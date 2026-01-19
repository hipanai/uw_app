#!/bin/bash
# init.sh - Environment setup script for Upwork Auto-Apply Pipeline
# Run this script at the start of each development session

set -e

echo "=========================================="
echo "Upwork Auto-Apply Pipeline - Setup"
echo "=========================================="

# Check Python version
echo "[1/6] Checking Python version..."
python3 --version

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "[2/6] Creating virtual environment..."
    python3 -m venv venv
else
    echo "[2/6] Virtual environment already exists"
fi

# Activate virtual environment
echo "[3/6] Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "[4/6] Installing Python dependencies..."
pip install -q -r requirements.txt

# Install Playwright browsers if needed
echo "[5/6] Installing Playwright browsers..."
playwright install chromium --with-deps 2>/dev/null || echo "Playwright browsers already installed or skipped"

# Create .tmp directory for intermediate files
echo "[6/6] Creating .tmp directory..."
mkdir -p .tmp

# Check for required environment variables
echo ""
echo "=========================================="
echo "Environment Check"
echo "=========================================="

check_env() {
    if [ -z "${!1}" ]; then
        echo "  WARNING: $1 not set"
    else
        echo "  OK: $1 is configured"
    fi
}

if [ -f ".env" ]; then
    source .env
    check_env "ANTHROPIC_API_KEY"
    check_env "HEYGEN_API_KEY"
    check_env "HEYGEN_AVATAR_ID"
    check_env "SLACK_BOT_TOKEN"
    check_env "SLACK_SIGNING_SECRET"
    check_env "SLACK_APPROVAL_CHANNEL"
    check_env "UPWORK_PIPELINE_SHEET_ID"
    check_env "UPWORK_PROCESSED_IDS_SHEET_ID"
else
    echo "  WARNING: .env file not found"
    echo "  Create .env with required variables (see app_spec.txt)"
fi

echo ""
echo "=========================================="
echo "Setup Complete"
echo "=========================================="
echo ""
echo "Next steps:"
echo "  1. Ensure .env file contains all required API keys"
echo "  2. Run: source venv/bin/activate"
echo "  3. Start developing!"
echo ""
echo "Key scripts:"
echo "  - executions/upwork_apify_scraper.py      # Scrape jobs from Apify"
echo "  - executions/upwork_proposal_generator.py # Generate proposals"
echo "  - executions/modal_webhook.py             # Deploy Modal webhooks"
echo ""
