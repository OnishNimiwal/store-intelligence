# Engineering Choices

This document outlines the three major architectural decisions made during the design and implementation of the Store Intelligence system. For each decision, we evaluate the options considered, document what the AI suggested, detail what was ultimately implemented, and justify the rationale.

---

## 1. Computer Vision: YOLOv8n + Persistent Color-Registry Re-ID

### Options Considered
1. **YOLOv8n + ByteTrack + OSNet (Deep Re-ID):** Heavy person detection coupled with deep-learning Re-ID embeddings.
2. **RT-DETR + Custom Trajectory-based Tracking:** High accuracy on occlusions but massive hardware footprint.
3. **YOLOv8n + Custom Persistent Color-Registry (Implemented):** Object detection and multi-object tracking combined with an asynchronous, persistent RGB color signature registry (`reid_registry.json`).
4. **VLM-only Pipeline (GPT-4V / Claude Vision):** Directly feeding video frames to a multimodal LLM for visitor tracking and counting.

### What AI Suggested
The AI recommended a hybrid pipeline: using YOLOv8n for fast object tracking, and spinning up a PyTorch-based OSNet model to generate 512-dimensional Re-ID feature vectors for each visitor crop.

### What I Chose and Why
I selected **YOLOv8n with a custom persistent RGB color-registry**. While deep Re-ID models like OSNet provide superior feature matching across frames, they are incredibly heavy, slow on CPU-only machines, and difficult to set up in containerised environments without CUDA drivers. VLMs were rejected due to non-deterministic outputs, extreme API costs, and latency constraints.

Our custom persistent registry tracks:
* **Active Sessions:** Captures a visitor's average RGB color signature on entrance and matches subsequent tracks on floor/billing cameras using a **5-minute sliding window** and Euclidean distance thresholding (< 45.0).
* **Completed Sessions:** Keeps track of recently exited sessions to handle re-entry within 120 seconds.
* **Resiliency Fallbacks:** If a visitor misses the entry camera, a synthetic `ENTRY` is emitted when they enter a zone to ensure session compliance in the downstream FastAPI database.

This choice runs beautifully on standard CPUs, maintains a tiny Docker image size (no massive PyTorch/CUDA weights), matches visitors across independent python runtimes, and remains completely deterministic.

---

## 2. Event Schema: Nested Metadata vs Flat Events

### Options Considered
1. **Flat Event Structure:** All fields (like `queue_depth`, `sku_zone`, `session_seq`) at the top level of the JSON payload.
2. **Nested Metadata (Implemented):** Strict validation of core parameters, with specific contextual markers enclosed inside a sub-object `metadata`.
3. **Dynamic / Schemaless JSON:** Storing raw payloads in database JSON columns to support high-velocity, evolving analytics fields.

### What AI Suggested
The AI suggested using a flat schema because it is easier to query using SQL `SELECT` operations and avoids the overhead of parsing nested JSON strings in relational databases.

### What I Chose and Why
I chose the **nested metadata schema** (matching the strict challenge specification). While flat schemas are easier to query in basic SQL, a nested metadata structure keeps the core event structure clean and clean-cut. 

**Downstream Trade-off Resolution:**
To resolve the relational querying trade-off, our SQLAlchemy database layer (`database.py`) parses the nested fields during ingestion and maps them directly to flat SQL columns (`queue_depth`, `sku_zone`, `session_seq`). This gives us the **best of both worlds**:
1. Full API compliance with the nested JSON format.
2. High-performance indexing and fast querying on flat database columns for real-time analytics.

---

## 3. Database Engine: SQLite with On-Read SQLAlchemy Aggregations

### Options Considered
1. **PostgreSQL + TimescaleDB (Time-series optimization):** Ideal for production scale (40 stores, 8 cities) with automatic partitioning.
2. **SQLite + On-Read SQLAlchemy Aggregations (Implemented):** SQLite database file, doing real-time session reconstructions and math on request.
3. **Redis Cache Layer + SQLite:** Caching the metrics endpoint and invalidating on event ingest.

### What AI Suggested
The AI recommended using PostgreSQL as the primary datastore to simulate production realism, combined with a Redis cache to prevent `/metrics` calculations from blocking threads.

### What I Chose and Why
I chose **SQLite with on-read SQLAlchemy aggregations**. While Postgres is the industry standard for production, it requires spinning up a second Docker service, managing network bridges, and dealing with connection pools during startup. For the 48-hour take-home scope, SQLite ensures that `docker compose up` works **instantly on a clean machine** without any service-dependency timing bugs.

By leveraging SQLAlchemy, the database layer remains abstract. Migrating to PostgreSQL in a real-world deploy is a **single-line change** to the database connection string.

**Aggregation Choice:**
I chose **on-read aggregations** over pre-aggregated views. The scale of this take-home dataset is small enough that real-time SQL queries (using `func.distinct`, time window joins, and session intersections) complete in **under 5 milliseconds**, ensuring 100% data correctness (no cache lag). 

**First Breakage Point at Scale:**
At 40 stores sending events in real-time, the first thing to break would be SQLite write locks (due to file write contention). The production roadmap would introduce an ingest buffer (Kafka/SQS) and transition SQLite to a clustered PostgreSQL instance before introducing a Redis cache.
