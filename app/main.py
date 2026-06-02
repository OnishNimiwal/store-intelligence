import json
import logging
import time
import uuid

from fastapi import FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError

from app.anomalies import router as anomalies_router
from app.database import init_db
from app.funnel import router as funnel_router
from app.health import router as health_router
from app.heatmap import router as heatmap_router
from app.ingestion import router as ingestion_router
from app.metrics import router as metrics_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("store_intelligence")

app = FastAPI(
    title="Store Intelligence API",
    description="Retail analytics API from CCTV behavioural events.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    init_db()
    logger.info("Database initialized.")


@app.exception_handler(OperationalError)
def db_operational_exception_handler(request: Request, exc: OperationalError):
    logger.critical("Database connection error: %s", exc)
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "error": "Service Unavailable",
            "message": "Database is currently offline or unreachable.",
            "code": "DB_OFFLINE",
        },
    )


@app.middleware("http")
async def log_requests(request: Request, call_next):
    trace_id = str(uuid.uuid4())
    start_time = time.time()
    event_count = 0
    body_json = None
    store_id = "N/A"

    if request.method == "POST" and request.url.path == "/events/ingest":
        try:
            body = await request.body()

            async def receive():
                return {"type": "http.request", "body": body, "more_body": False}

            request._receive = receive
            body_json = json.loads(body.decode("utf-8"))
            if isinstance(body_json, list):
                event_count = len(body_json)
                if body_json:
                    store_id = body_json[0].get("store_id", "N/A")
        except Exception:
            pass

    path_parts = request.url.path.split("/")
    if "stores" in path_parts:
        try:
            idx = path_parts.index("stores")
            if idx + 1 < len(path_parts):
                store_id = path_parts[idx + 1]
        except ValueError:
            pass

    response: Response = await call_next(request)
    latency_ms = round((time.time() - start_time) * 1000, 2)
    logger.info(
        json.dumps(
            {
                "trace_id": trace_id,
                "store_id": store_id,
                "endpoint": request.url.path,
                "method": request.method,
                "latency_ms": latency_ms,
                "event_count": event_count,
                "status_code": response.status_code,
            }
        )
    )
    response.headers["X-Trace-ID"] = trace_id
    return response


app.include_router(ingestion_router)
app.include_router(metrics_router)
app.include_router(funnel_router)
app.include_router(heatmap_router)
app.include_router(anomalies_router)
app.include_router(health_router)
