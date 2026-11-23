# Quickstart Guide

The Digital Twin Road platform provides a unified CLI orchestrator (`./manage.sh`) to control the complete application lifecycle.

---

## 1. Starting Local Development Stack

To start both the FastAPI backend and the Vue 3 + Vite frontend in hot-reloading background daemon mode:

```bash
./manage.sh up-local
```

Console Output:

```text
Stopping Demonstrator processes...
Backend port 8000 is clear.
Starting Backend (FastAPI)...
Starting Frontend (Vue/Vite)...
Demonstrator is starting up.
Backend logs: logs/backend.log
Frontend logs: logs/frontend.log
Access frontend at http://localhost:5173
```

---

## 2. Accessing Platform Services

Once the background processes initialize:

* **Interactive Web Dashboard:** Open [http://localhost:5173](http://localhost:5173) in Google Chrome, Firefox, or Safari.
* **FastAPI Swagger / Interactive Docs:** Navigate to [http://localhost:8000/docs](http://localhost:8000/docs) for live REST API inspection.
* **OpenAPI Raw Specification:** Available at [http://localhost:8000/openapi.json](http://localhost:8000/openapi.json).

---

## 3. Inspecting System Status & Logs

Check active process IDs, ports, and connection status:

```bash
./manage.sh status
```

To follow real-time backend simulation logs:

```bash
tail -f logs/backend.log
```

To follow frontend compilation and HMR logs:

```bash
tail -f logs/frontend.log
```

---

## 4. Stopping Local Services

To gracefully terminate all running local backend and frontend instances:

```bash
./manage.sh down-local
```

---

## 5. Running with Docker Compose

To boot the containerized demonstrator stack via Nginx reverse proxy:

```bash
# Standard mode (lightweight 2-container Native stack):
./manage.sh up

# Full FIWARE mode (Orion Context Broker, IoT Agent UltraLight & MongoDB):
./manage.sh up-fiware
```

To shut down running containers (both standard and FIWARE profiles):

```bash
./manage.sh down
```

---

## 6. Running Fleet Scalability Benchmark

To run the multi-vehicle co-simulation scalability benchmark ($N = 10 \dots 2{,}000$ active vehicles):

```bash
./manage.sh benchmark
```
