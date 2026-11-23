# Docker Containerization & Deployment

The platform is fully containerized using **Docker** and **Docker Compose**, providing a reproducible deployment stack across Linux, macOS, and Windows environments.

---

## Container Services

The multi-container cluster is defined in `docker-compose.yml`:

| Service | Port | Description |
| :--- | :--- | :--- |
| `demo-backend` | `:8000` | Python 3.12 FastAPI backend and in-tree co-simulation engines. |
| `demo-frontend` | `:5173` | Nginx production container serving the compiled Vue 3 + Vite SPA. |
| `orion` | `:1026` | *(Optional, profile `fiware`)* FIWARE Orion Context Broker (NGSIv2). |
| `mongo-db` | `:27017` | *(Optional, profile `fiware`)* MongoDB document store for Orion entity persistence. |
| `iot-agent` | `:4041 / :7896` | *(Optional, profile `fiware`)* FIWARE IoT Agent for UltraLight 2.0 sensor ingest. |

---

## Lean Container Architecture

To maintain fast CI/CD builds and minimal container footprints:

* Heavy offline 3D rendering libraries and system-level Mesa/OpenGL dependencies are omitted in favor of the in-tree pure NumPy 1D FEM solver and browser-native HTML5 Canvas 2D Boussinesq/Westergaard engines.
* **Result:** Backend Docker image size is reduced by **>1.2 GB**, completing container builds in under 45 seconds.

---

## Environment Configuration

Service hostnames and CORS policies are parameterized via environment variables:

```yaml
demo-backend:
  environment:
    - DATA_BROKER_BACKEND=${DATA_BROKER_BACKEND:-native}
    - CORS_ORIGINS=${CORS_ORIGINS:-http://localhost:5173,http://127.0.0.1:5173}
    - ORION_HOST=${ORION_HOST:-orion}
    - IOT_AGENT_HOST=${IOT_AGENT_HOST:-iot-agent}
    - IOT_AGENT_SOUTH_HOST=${IOT_AGENT_SOUTH_HOST:-iot-agent}
```

Use `./manage.sh up` for the 2-container Native stack (`DATA_BROKER_BACKEND=native`) or `./manage.sh up-fiware` to launch the full FIWARE Orion + IoT Agent + MongoDB profile (`DATA_BROKER_BACKEND=fiware`). `./manage.sh down` stops containers across both profiles.

To override defaults in production, copy the provided `.env.example` template to `.env`:

```bash
cp .env.example .env
```
