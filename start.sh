#!/bin/bash
set -e

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}🚀 Starting Agentic Flow Platform...${NC}"

# Check .env exists
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}⚠️  No .env file found. Copying from .env.example...${NC}"
    cp .env.example .env
    echo -e "${YELLOW}   Please edit .env to add your GLM_API_KEY and TELEGRAM_BOT_TOKEN${NC}"
fi

# Check Node.js
if ! command -v node &> /dev/null; then
    echo "❌ Node.js not found. Install from https://nodejs.org"
    exit 1
fi

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 not found."
    exit 1
fi

# Install backend deps if needed
if [ ! -d "backend/.venv" ]; then
    echo -e "${BLUE}📦 Installing backend dependencies...${NC}"
    cd backend
    python3.11 -m venv .venv
    . .venv/bin/activate
    pip install -r requirements.txt -q
    deactivate
    cd ..
fi

# Install frontend deps if needed
if [ ! -d "frontend/node_modules" ]; then
    echo -e "${BLUE}📦 Installing frontend dependencies...${NC}"
    cd frontend && npm install --silent && cd ..
fi

echo -e "${GREEN}✅ Dependencies ready!${NC}"
echo -e "${GREEN}🌐 Frontend: http://localhost:5173${NC}"
echo -e "${GREEN}📡 Backend:  http://localhost:8000${NC}"
echo -e "${GREEN}📚 API Docs: http://localhost:8000/docs${NC}"
echo ""

# Use explicit venv Python/uvicorn path (no source — works in any POSIX shell)
npx concurrently \
    --names "BACKEND,FRONTEND" \
    --prefix-colors "blue,green" \
    --kill-others-on-fail \
    "cd backend && .venv/bin/uvicorn main:app --reload --host 0.0.0.0 --port 8000" \
    "cd frontend && npm run dev"
