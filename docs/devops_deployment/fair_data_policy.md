# FAIR Principles & Open Science Policy

In adherence to international **Open Science** recommendations, the Digital Twin Road platform implements the **FAIR Data Principles**:
**F**indable, **A**ccessible, **I**nteroperable, and **R**eusable.

---

## 1. Findable (F)

* **Permanent Citable DOI:** Archived via **Zenodo** (CERN's EU-funded open repository) under permanent DOI [10.5281/zenodo.24485660](https://doi.org/10.5281/zenodo.24485660).
* **Machine-Readable Metadata:** The repository includes a standardized `CITATION.cff` file conforming to the Citation File Format 1.2.0, providing automated citation parsing on GitHub, Zenodo, and Zotero.
* **Funding Acknowledgment:** Explicitly indexed with **DFG Project Number 453596084** (Transregio TRR 339).

---

## 2. Accessible (A)

* **Open-Source License:** Released under the permissive **MIT License**, granting royalty-free, perpetual rights to run, inspect, fork, modify, and redistribute the software.
* **Open Standard Protocols:** The platform relies exclusively on standard HTTP REST, Server-Sent Events (SSE), and JSON, avoiding proprietary binary protocols.
* **Zero-API-Key Base Maps:** Default GIS layers use OpenStreetMap and Esri Light Gray Canvas tiles accessible without proprietary developer tokens or fees.

---

## 3. Interoperable (I)

* **Standard Geospatial Formats:** Road centerlines, road segments, junctions, water bodies, and moving vehicles are represented strictly as standard **GeoJSON (RFC 7946)** FeatureCollections.
* **IEEE 1516 HLA / FOM Standard:** Co-simulation schemas adhere to the international High-Level Architecture standard, formalized in `configs/fom_schema.json`.
* **FIWARE NGSIv2 & UltraLight 2.0:** Integrates with the European Commission's FIWARE smart city standard for IoT sensor federation.
* **Formal Algebraic Composition:** Hybrid Petri Nets follow Wolfgang Reisig's published HERAKLIT module algebra ($M_1 \bullet M_2$).

---

## 4. Reusable (R)

* **Automated Quickstart:** The single CLI script (`./manage.sh`) allows any researcher or developer to install, test, and run the stack with a single command.
* **Zero External C++ Solvers:** The entire physics and formal algebra stack runs in pure Python and standard browser JavaScript/TypeScript, eliminating complicated compiled dependencies.
* **Automated Test Suite:** Shipped with a clean `pytest` suite covering Boussinesq mechanics, Petri net firing, and concurrency safety.
