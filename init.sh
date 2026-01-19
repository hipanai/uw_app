#!/bin/bash
# init.sh - Environment setup script for Upwork Auto-Apply Pipeline
# Run this script at the start of each development session

set -e

echo "=========================================="
echo "Upwork Auto-Apply Pipeline - Setup"
echo "=========================================="

# Check Python version
echo "[1/9] Checking Python version..."
python3 --version || python --version

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "[2/9] Creating virtual environment..."
    python3 -m venv venv || python -m venv venv
else
    echo "[2/9] Virtual environment already exists"
fi

# Activate virtual environment (cross-platform)
echo "[3/9] Activating virtual environment..."
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
elif [ -f "venv/Scripts/activate" ]; then
    source venv/Scripts/activate
fi

# Install Python dependencies
echo "[4/9] Installing Python dependencies..."
pip install -q -r requirements.txt

# Install Playwright browsers if needed
echo "[5/9] Installing Playwright browsers..."
playwright install chromium --with-deps 2>/dev/null || echo "Playwright browsers already installed or skipped"

# Create .tmp directory for intermediate files
echo "[6/9] Creating .tmp directory..."
mkdir -p .tmp

# Create static directory for frontend build
echo "[7/9] Creating static directory..."
mkdir -p static/frontend

# Install frontend dependencies if frontend exists
echo "[8/9] Setting up frontend..."
if [ -d "frontend" ]; then
    cd frontend
    if [ -f "package.json" ]; then
        echo "  Installing frontend dependencies..."
        npm install
    else
        echo "  Frontend package.json not found, skipping npm install"
    fi
    cd ..
else
    echo "  Frontend directory not found, skipping frontend setup"
fi

# Check for required environment variables
echo ""
echo "[9/9] Checking environment variables..."
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
    echo "Backend Config:"
    check_env "ANTHROPIC_API_KEY"
    check_env "HEYGEN_API_KEY"
    check_env "HEYGEN_AVATAR_ID"
    check_env "SLACK_BOT_TOKEN"
    check_env "SLACK_SIGNING_SECRET"
    check_env "SLACK_APPROVAL_CHANNEL"
    check_env "UPWORK_PIPELINE_SHEET_ID"
    check_env "UPWORK_PROCESSED_IDS_SHEET_ID"
    echo ""
    echo "Web UI Config:"
    check_env "UI_PASSWORD"
    check_env "JWT_SECRET"
else
    echo "  WARNING: .env file not found"
    echo "  Create .env with required variables (see app_spec.txt)"
fi

echo ""
echo "=========================================="
echo "Setup Complete"
echo "=========================================="
echo ""
echo "To start development:"
echo ""
echo "  Backend (FastAPI):"
echo "    uvicorn executions.local_server:app --reload --port 8000"
echo ""
echo "  Frontend (Vite dev server):"
echo "    cd frontend && npm run dev"
echo ""
echo "  Production (single server):"
echo "    cd frontend && npm run build"
echo "    uvicorn executions.local_server:app --port 8000"
echo ""
echo "Access URLs:"
echo "  - Dev Frontend:  http://localhost:5173"
echo "  - Backend API:   http://localhost:8000"
echo "  - Production:    http://localhost:8000"
echo ""
