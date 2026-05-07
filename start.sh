#!/bin/bash
# AstroAgent — start backend + frontend dev servers

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "🔭 Starting AstroAgent..."

# Backend
cd "$SCRIPT_DIR/backend"
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!
echo "  Backend PID: $BACKEND_PID (http://localhost:8000)"

# Frontend
cd "$SCRIPT_DIR/frontend"
npm run dev -- --host 0.0.0.0 &
FRONTEND_PID=$!
echo "  Frontend PID: $FRONTEND_PID (http://localhost:5173)"

echo ""
echo "  Open: http://localhost:5173"
echo "  API docs: http://localhost:8000/docs"
echo ""
echo "  Press Ctrl+C to stop both servers"

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT TERM
wait
