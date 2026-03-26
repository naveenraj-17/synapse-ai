#!/bin/bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
# Global PIDs
BACKEND_PID=""
FRONTEND_PID=""

# Cleanup function to kill processes on exit
cleanup() {
    echo ""
    echo "Stopping services..."
    
    if [ ! -z "$BACKEND_PID" ]; then
        echo "Killing Backend (PID $BACKEND_PID)..."
        kill "$BACKEND_PID" 2>/dev/null
    fi
    
    if [ ! -z "$FRONTEND_PID" ]; then
        echo "Killing Frontend (PID $FRONTEND_PID)..."
        kill "$FRONTEND_PID" 2>/dev/null
    fi
    
    echo "Done."
}

# Trap signals: EXIT (normal exit), INT (Ctrl+C), TERM (termination)
trap cleanup EXIT INT TERM

# Function to check if a port is in use
check_port() {
    (echo > /dev/tcp/localhost/$1) >/dev/null 2>&1
    if [ $? -eq 0 ]; then
        echo "Service on port $1 is already running."
        return 0
    else
        echo "Service on port $1 is NOT running."
        return 1
    fi
}

# Function to wait for a URL to be available (warm-up)
wait_for_url() {
    local url=$1
    local name=$2
    local max_retries=30
    local count=0

    echo "Waiting for $name to be ready at $url..."
    while [ $count -lt $max_retries ]; do
        # Use curl to check status. -s silent, -o output null, -w http_code
        status=$(curl -s -o /dev/null -w "%{http_code}" "$url")
        if [ "$status" -eq 200 ]; then
            echo "$name is ready!"
            return 0
        fi
        echo "$name not ready yet (status: $status). Retrying in 2s..."
        sleep 2
        count=$((count + 1))
    done
    
    echo "Timeout waiting for $name!"
    return 1
}

# Check and start Backend (Port 8000)
echo "Checking Backend..."
if ! check_port 8000; then
    echo "Starting Backend..."
    source "$DIR/backend/venv/bin/activate"
    python3.11 "$DIR/backend/main.py" &
    BACKEND_PID=$!
    echo "Backend started with PID $BACKEND_PID"
else
    echo "Backend is already running."
fi

# Always wait for backend to ensure it's responsive
wait_for_url "http://localhost:8000/api/status" "Backend"

# Check and start Frontend (Port 3000)
echo "Checking Frontend..."
if ! check_port 3000; then
    echo "Starting Frontend..."
    cd "$DIR/frontend" && npm run dev &
    FRONTEND_PID=$!
    echo "Frontend started with PID $FRONTEND_PID"
    cd ..
else
    echo "Frontend is already running."
fi

# Always wait for frontend (this warms up Next.js compilation)
wait_for_url "http://localhost:3000" "Frontend"

echo "Launching Browser..."
python3.11 "$DIR/launch_browser.py"

echo "Services are running. Press Ctrl+C to stop."
wait
