#!/bin/bash
# Digital Twin Road Demonstrator Management Script
# Usage: ./manage.sh [up-local|down-local|stop-local|up|up-fiware|down|reload|status|clean|test|benchmark|docs]

set -e
DEMO_ROOT=$(cd "$(dirname "$0")" && pwd)
FRONTEND_DIR="$DEMO_ROOT/frontend"
LOG_DIR="$DEMO_ROOT/logs"

PYTHON_BIN="python3"
UVICORN_BIN="uvicorn"
PYTEST_BIN="pytest"
ZENSICAL_BIN="zensical"
for venv_dir in "$DEMO_ROOT/.venv/bin" "$DEMO_ROOT/venv/bin"; do
    if [ -x "$venv_dir/python3" ]; then
        PYTHON_BIN="$venv_dir/python3"
        [ -x "$venv_dir/uvicorn" ] && UVICORN_BIN="$venv_dir/uvicorn"
        [ -x "$venv_dir/pytest" ] && PYTEST_BIN="$venv_dir/pytest"
        [ -x "$venv_dir/zensical" ] && ZENSICAL_BIN="$venv_dir/zensical"
        break
    fi
done

mkdir -p "$LOG_DIR"

function stop_pids() {
    local pids="$1"
    [ -z "$pids" ] && return 0

    for pid in $pids; do
        kill -TERM "$pid" 2>/dev/null || true
    done

    local i
    for i in $(seq 1 10); do
        local still_alive=""
        for pid in $pids; do
            if kill -0 "$pid" 2>/dev/null; then
                still_alive="$still_alive $pid"
            fi
        done
        [ -z "$still_alive" ] && return 0
        sleep 0.2
    done

    for pid in $pids; do
        if kill -0 "$pid" 2>/dev/null; then
            kill -9 "$pid" 2>/dev/null || true
        fi
    done
}

function stop_all() {
    echo "Stopping Demonstrator processes..."

    # Gracefully stop tracked server PID files first
    for pid_file in "$LOG_DIR/backend.pid" "$LOG_DIR/frontend.pid"; do
        if [ -f "$pid_file" ]; then
            SAVED_PID=$(cat "$pid_file" 2>/dev/null || true)
            if [ -n "$SAVED_PID" ]; then
                echo "Stopping tracked process from $(basename "$pid_file") (PID: $SAVED_PID)..."
                stop_pids "$SAVED_PID"
            fi
            rm -f "$pid_file"
        fi
    done

    # Terminate only LISTENing server sockets on port 8000 (never client browser connections)
    BACKEND_PIDS=$(lsof -nP -tiTCP:8000 -sTCP:LISTEN 2>/dev/null || true)
    if [ -n "$BACKEND_PIDS" ]; then
        echo "Stopping backend listener on port 8000 (PIDs: $BACKEND_PIDS)..."
        stop_pids "$BACKEND_PIDS"
    else
        echo "Backend port 8000 is clear."
    fi

    # Terminate only LISTENing server sockets on ports 5173 / 5174 (Frontend)
    for port in 5173 5174; do
        PORT_PIDS=$(lsof -nP -tiTCP:$port -sTCP:LISTEN 2>/dev/null || true)
        if [ -n "$PORT_PIDS" ]; then
            echo "Stopping frontend listener on port $port (PIDs: $PORT_PIDS)..."
            stop_pids "$PORT_PIDS"
        fi
    done

    # Gentle fallback scoped strictly to this project's server commands
    pkill -TERM -f "uvicorn dashboard_backend:app" 2>/dev/null || true
    pkill -TERM -f "node.*vite.*frontend" 2>/dev/null || true

    echo "Done."
}

function start_all() {
    if ! [ -x "$UVICORN_BIN" ] && ! command -v "$UVICORN_BIN" >/dev/null 2>&1; then
        echo "Error: Python backend dependency 'uvicorn' was not found."
        echo "Install backend dependencies first:"
        echo "  python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
        echo "Or run via Docker instead: ./manage.sh up"
        exit 1
    fi
    if [ ! -x "$FRONTEND_DIR/node_modules/.bin/vite" ]; then
        echo "Error: Frontend dependencies are not installed (missing frontend/node_modules)."
        echo "Install frontend dependencies first:"
        echo "  cd frontend && npm ci --legacy-peer-deps && cd .."
        echo "Or run via Docker instead: ./manage.sh up"
        exit 1
    fi

    stop_all
    echo "Starting Backend (FastAPI)..."
    cd "$DEMO_ROOT"
    nohup "$UVICORN_BIN" dashboard_backend:app --reload --port 8000 > "$LOG_DIR/backend.log" 2>&1 &
    echo $! > "$LOG_DIR/backend.pid"

    echo "Starting Frontend (Vue/Vite)..."
    cd "$FRONTEND_DIR"
    nohup npm run dev > "$LOG_DIR/frontend.log" 2>&1 &
    echo $! > "$LOG_DIR/frontend.pid"

    echo "Demonstrator is starting up."
    echo "Backend logs: $LOG_DIR/backend.log"
    echo "Frontend logs: $LOG_DIR/frontend.log"
    echo "Access frontend at http://localhost:5173"
}

case "$1" in
    up)
        echo "Starting Demonstrator in Docker mode (Standard Native)..."
        cd "$DEMO_ROOT"
        docker compose up --build -d
        ;;
    up-fiware)
        echo "Starting Demonstrator in Full FIWARE Docker mode (Orion + IoT Agent + MongoDB)..."
        cd "$DEMO_ROOT"
        DATA_BROKER_BACKEND=fiware docker compose --profile fiware up --build -d
        ;;
    up-local)
        echo "Starting Demonstrator in Local Process mode..."
        start_all
        ;;
    down)
        echo "Stopping Demonstrator containers..."
        cd "$DEMO_ROOT"
        docker compose --profile fiware down
        ;;
    down-local|stop-local)
        echo "Stopping local Demonstrator processes..."
        stop_all
        ;;
    reload)
        echo "Reloading Docker stack..."
        cd "$DEMO_ROOT"
        docker compose down
        docker compose up --build -d
        ;;
    clean)
        echo "DEEP CLEAN: Stopping processes, clearing logs and stale simulations..."
        stop_all
        docker compose --profile fiware down -v --remove-orphans 2>/dev/null || true
        rm -rf "$LOG_DIR"/*.log "$LOG_DIR"/*.pid
        rm -rf "$DEMO_ROOT"/simulations "$DEMO_ROOT"/*.h5
        echo "Cleanup complete."
        ;;
    status)
        echo "Checking Docker status..."
        docker compose ps 2>/dev/null || true
        echo ""
        echo "Checking local processes..."
        pgrep -fl "uvicorn" && echo "Local Backend is running" || echo "Local Backend is NOT running"
        pgrep -fl "vite" && echo "Local Frontend is running" || echo "Local Frontend is NOT running"
        ;;
    test)
        echo "Running frontend typecheck & build test..."
        cd "$FRONTEND_DIR" && npm run build
        echo "Running backend test suite (pytest)..."
        cd "$DEMO_ROOT" && "$PYTEST_BIN"
        echo "Running backend import test..."
        cd "$DEMO_ROOT" && "$PYTHON_BIN" -c "import dashboard_backend; print('Backend syntax & imports OK')"
        ;;
    benchmark)
        echo "Running multi-vehicle co-simulation scalability benchmark..."
        cd "$DEMO_ROOT" && "$PYTHON_BIN" scripts/benchmark_fleet.py
        ;;
    docs)
        echo "Building Zensical documentation site..."
        cd "$DEMO_ROOT"
        if command -v "$ZENSICAL_BIN" >/dev/null 2>&1 || [ -x "$ZENSICAL_BIN" ]; then
            "$ZENSICAL_BIN" build --clean
            echo "Zensical static documentation generated at site/index.html"
        else
            echo "zensical command not found. Install via: pip install zensical pymdown-extensions"
            echo "To preview locally with live reload: zensical serve"
            exit 1
        fi
        ;;
    *)
        echo "Usage: $0 {up-local|down-local|stop-local|up|up-fiware|down|reload|status|clean|test|benchmark|docs}"
        exit 1
        ;;
esac
