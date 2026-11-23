# Installation & Setup

## Prerequisites

The Digital Twin Road Platform is engineered to run on modern Linux, macOS, and Windows workstations. Ensure the following host dependencies are installed:

* **Python:** 3.11, 3.12, or 3.13 (64-bit)
* **Node.js:** v20.x LTS or higher (v22 recommended)
* **npm:** v10.x or higher
* **Docker & Docker Compose:** *(Optional)* required for containerized production deployment.

---

## Cloning the Repository

Clone the official open-source repository:

```bash
git clone https://github.com/vprokopets/digital-twin-road.git
cd digital-twin-road
```

---

## Local Virtual Environment Setup

### 1. Create and Activate Python Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 2. Install Backend Python Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Install Frontend Dependencies

```bash
cd frontend
npm ci --legacy-peer-deps
cd ..
```

---

## Verification of Installation

Verify that backend imports, unit tests, and frontend typechecking compile cleanly using the automated test CLI:

```bash
./manage.sh test
```

Expected output:

```text
Running frontend typecheck & build test...
✓ built in 380ms (0 type errors, 0 warnings)
Running backend test suite (pytest)...
============================== 70 passed in 1.75s ==============================
Running backend import test...
Backend syntax & imports OK
```
