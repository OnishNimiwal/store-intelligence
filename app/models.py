from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class EventMetadata(BaseModel):
    queue_depth: Optional[int] = None
    sku_zone: Optional[str] = None
    session_seq: Optional[int] = None


class EventSchema(BaseModel):
    event_id: str
    store_id: str
    camera_id: str
    visitor_id: str
    event_type: str
    timestamp: datetime
    zone_id: Optional[str] = None
    dwell_ms: int = 0
    is_staff: bool = False
    confidence: float
    metadata: Optional[EventMetadata] = Field(default_factory=EventMetadata)


class IngestResponse(BaseModel):
    success: bool
    ingested_count: int
    errors: List[Dict[str, Any]] = []


class StoreMetricsResponse(BaseModel):
    store_id: str
    unique_visitors: int
    conversion_rate: float
    avg_dwell_per_zone: Dict[str, float]
    current_queue_depth: int
    abandonment_rate: float


class FunnelStage(BaseModel):
    stage_name: str
    count: int
    drop_off_pct: float


class StoreFunnelResponse(BaseModel):
    store_id: str
    stages: List[FunnelStage]


class HeatmapItem(BaseModel):
    zone_id: str
    visit_frequency: int
    avg_dwell_sec: float
    score: float


class StoreHeatmapResponse(BaseModel):
    store_id: str
    heatmap: List[HeatmapItem]
    data_confidence: bool


class AnomalyItem(BaseModel):
    anomaly_id: str
    type: str
    severity: str
    timestamp: datetime
    details: str
    suggested_action: str


class StoreAnomaliesResponse(BaseModel):
    store_id: str
    anomalies: List[AnomalyItem]
