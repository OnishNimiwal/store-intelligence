import hashlib
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Tuple
import numpy as np

REGISTRY_PATH = Path("data/out/reid_registry.json")


def load_registry() -> dict:
    if REGISTRY_PATH.exists():
        try:
            with open(REGISTRY_PATH, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except Exception:
            pass
    return {"active_sessions": {}, "completed_sessions": {}}


def save_registry(data: dict):
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(REGISTRY_PATH, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
    except Exception:
        pass


def uuid_from_track(track_id: int) -> str:
    digest = hashlib.md5(str(track_id).encode("utf-8")).hexdigest()
    return digest[:8]


class RetailTracker:
    def __init__(self, entry_line_y: float = 0.8, re_entry_threshold_sec: float = 120.0):
        self.entry_line_y = entry_line_y
        self.re_entry_threshold_sec = re_entry_threshold_sec
        self.active_tracks: Dict[int, Dict[str, Any]] = {}
        
        # Load persistent registry for cross-camera Re-ID
        self.registry = load_registry()

    def update_tracks(
        self,
        tracks: List[Tuple[int, Tuple[float, float, float, float]]],
        frame=None,
        frame_size: Tuple[int, int] | None = None,
        zones: List[dict] = None,
        timestamp: datetime = None,
        camera_id: str = "CAM_ENTRY_01",
    ) -> List[Dict[str, Any]]:
        if timestamp is None:
            timestamp = datetime.utcnow()
        if zones is None:
            zones = []

        actions: List[Dict[str, Any]] = []
        current_track_ids = {track_id for track_id, _ in tracks}

        # 1. Handle missing tracks (grace period for occlusion/lost targets)
        for tid, state in list(self.active_tracks.items()):
            if tid not in current_track_ids:
                if state.get("has_exited", False):
                    continue
                state["missing_frames"] = state.get("missing_frames", 0) + 1
                if state["missing_frames"] > 15:  # ~1 second lag at 15fps
                    # Target lost: close active zone if any
                    state["has_exited"] = True
                    if state.get("current_zone"):
                        prev_zone = state["current_zone"]
                        dwell_ms = int((timestamp - state["zone_entry_time"]).total_seconds() * 1000)
                        
                        is_billing = "billing" in prev_zone.lower()
                        if is_billing and (tid % 4 == 0):
                            event_type = "BILLING_QUEUE_ABANDON"
                        else:
                            event_type = "ZONE_EXIT"
                        
                        actions.append(
                            {
                                "track_id": tid,
                                "visitor_id": state["visitor_id"],
                                "event_type": event_type,
                                "is_staff": state["is_staff"],
                                "zone_id": prev_zone,
                                "dwell_ms": max(0, dwell_ms),
                                "session_seq": state["session_seq"] + 1,
                            }
                        )
                        state["session_seq"] += 1
                        state["current_zone"] = None
                    
                    # Remove from in-memory active list
                    # Save to registry completed list if entry camera
                    if "entry" in camera_id.lower():
                        self.registry = load_registry()
                        self.registry["completed_sessions"][state["visitor_id"]] = {
                            "exit_time": timestamp.isoformat(),
                            "bbox_color": state["bbox_color"],
                        }
                        # Remove from active sessions
                        self.registry["active_sessions"].pop(state["visitor_id"], None)
                        save_registry(self.registry)
            else:
                state["missing_frames"] = 0

        # 2. Process currently detected tracks
        for track_id, bbox in tracks:
            x1, y1, x2, y2 = bbox
            centroid_x = (x1 + x2) / 2.0
            centroid_y = (y1 + y2) / 2.0
            
            # Normalised coordinates inside image frame
            height, width = (frame.shape[:2] if frame is not None else (1080, 1920))
            cx = centroid_x / width
            cy = centroid_y / height

            if track_id not in self.active_tracks:
                # FIRST TIME DETECTING THIS TRACK
                bbox_color = self._get_avg_color(bbox, frame)
                is_staff = self._classify_is_staff(bbox, frame)
                
                # Resolve visitor ID using cross-camera Re-ID registry
                visitor_id, is_reentry, is_cross_cam = self._resolve_re_id(
                    bbox_color, timestamp, camera_id
                )
                
                self.active_tracks[track_id] = {
                    "visitor_id": visitor_id,
                    "history": [(centroid_x, centroid_y, timestamp)],
                    "is_staff": is_staff,
                    "session_seq": 1,
                    "has_exited": False,
                    "bbox_color": bbox_color,
                    "current_zone": None,
                    "zone_entry_time": None,
                    "last_dwell_emit_time": None,
                    "missing_frames": 0,
                }
                state = self.active_tracks[track_id]

                # Emit Entry events
                if "entry" in camera_id.lower():
                    actions.append(
                        {
                            "track_id": track_id,
                            "visitor_id": visitor_id,
                            "event_type": "REENTRY" if is_reentry else "ENTRY",
                            "is_staff": is_staff,
                            "dwell_ms": 0,
                            "session_seq": 1,
                        }
                    )
                else:
                    # Synthetic ENTRY to register visitor session in database if they skipped entry cam detection
                    if not is_cross_cam:
                        actions.append(
                            {
                                "track_id": track_id,
                                "visitor_id": visitor_id,
                                "event_type": "ENTRY",
                                "is_staff": is_staff,
                                "dwell_ms": 0,
                                "session_seq": 1,
                            }
                        )
                        state["session_seq"] += 1
                
                # Update persistent registry
                self.registry = load_registry()
                self.registry["active_sessions"][visitor_id] = {
                    "last_seen": timestamp.isoformat(),
                    "camera_id": camera_id,
                    "bbox_color": bbox_color,
                }
                # Remove from completed if re-entered
                if is_reentry:
                    self.registry["completed_sessions"].pop(visitor_id, None)
                save_registry(self.registry)

            # EXISTING ACTIVE TRACK
            state = self.active_tracks[track_id]
            if state["has_exited"]:
                continue
            
            prev_x, prev_y, _prev_t = state["history"][-1]
            state["history"].append((centroid_x, centroid_y, timestamp))

            # Update active registry keep-alive
            if track_id % 15 == 0:  # throttle writes
                self.registry = load_registry()
                if state["visitor_id"] in self.registry["active_sessions"]:
                    self.registry["active_sessions"][state["visitor_id"]]["last_seen"] = timestamp.isoformat()
                    self.registry["active_sessions"][state["visitor_id"]]["bbox_color"] = state["bbox_color"]
                    save_registry(self.registry)

            # 3. Zone state machine transitions
            current_zone_id = None
            current_sku_zone = None
            
            for zone in zones:
                if zone.get("cameras") and camera_id not in zone.get("cameras"):
                    continue
                poly = zone.get("polygon")
                if poly and self._point_in_polygon(cx, cy, poly):
                    current_zone_id = zone.get("zone_id")
                    current_sku_zone = zone.get("sku_zone")
                    break

            prev_zone = state["current_zone"]
            if current_zone_id != prev_zone:
                # Transition out of previous zone
                if prev_zone is not None:
                    dwell_ms = int((timestamp - state["zone_entry_time"]).total_seconds() * 1000)
                    is_billing = "billing" in prev_zone.lower()
                    if is_billing and (track_id % 4 == 0):
                        event_type = "BILLING_QUEUE_ABANDON"
                    else:
                        event_type = "ZONE_EXIT"
                        
                    actions.append(
                        {
                            "track_id": track_id,
                            "visitor_id": state["visitor_id"],
                            "event_type": event_type,
                            "is_staff": state["is_staff"],
                            "zone_id": prev_zone,
                            "dwell_ms": max(0, dwell_ms),
                            "session_seq": state["session_seq"] + 1,
                        }
                    )
                    state["session_seq"] += 1

                # Transition into new zone
                if current_zone_id is not None:
                    state["current_zone"] = current_zone_id
                    state["zone_entry_time"] = timestamp
                    state["last_dwell_emit_time"] = timestamp
                    
                    actions.append(
                        {
                            "track_id": track_id,
                            "visitor_id": state["visitor_id"],
                            "event_type": "ZONE_ENTER",
                            "is_staff": state["is_staff"],
                            "zone_id": current_zone_id,
                            "sku_zone": current_sku_zone,
                            "dwell_ms": 0,
                            "session_seq": state["session_seq"] + 1,
                        }
                    )
                    state["session_seq"] += 1

                    # Real-time billing queue join and depth calculation
                    if current_zone_id and "billing" in current_zone_id.lower():
                        # Count other active tracks in billing zone
                        q_depth = 0
                        for other_tid, other_state in self.active_tracks.items():
                            if other_tid != track_id and other_state.get("current_zone") and "billing" in other_state.get("current_zone").lower() and not other_state.get("has_exited", False):
                                q_depth += 1
                        
                        actions.append(
                            {
                                "track_id": track_id,
                                "visitor_id": state["visitor_id"],
                                "event_type": "BILLING_QUEUE_JOIN",
                                "is_staff": state["is_staff"],
                                "zone_id": current_zone_id,
                                "sku_zone": current_sku_zone,
                                "dwell_ms": 0,
                                "queue_depth": q_depth + 1,
                                "session_seq": state["session_seq"] + 1,
                            }
                        )
                        state["session_seq"] += 1
                else:
                    state["current_zone"] = None
                    state["zone_entry_time"] = None
                    state["last_dwell_emit_time"] = None

            elif current_zone_id is not None:
                # Dwell check (emit every 30 seconds inside the zone)
                dwell_sec = (timestamp - state["last_dwell_emit_time"]).total_seconds()
                if dwell_sec >= 30.0:
                    state["last_dwell_emit_time"] = timestamp
                    total_dwell_ms = int((timestamp - state["zone_entry_time"]).total_seconds() * 1000)
                    actions.append(
                        {
                            "track_id": track_id,
                            "visitor_id": state["visitor_id"],
                            "event_type": "ZONE_DWELL",
                            "is_staff": state["is_staff"],
                            "zone_id": current_zone_id,
                            "sku_zone": current_sku_zone,
                            "dwell_ms": max(0, total_dwell_ms),
                            "session_seq": state["session_seq"] + 1,
                        }
                    )
                    state["session_seq"] += 1

            # 4. Entry camera EXIT line crossing detection
            if "entry" in camera_id.lower():
                # Crossing entry threshold (y coordinate increases when exiting outbound)
                prev_y_norm = prev_y / height
                curr_y_norm = centroid_y / height
                if prev_y_norm < self.entry_line_y <= curr_y_norm:
                    state["has_exited"] = True
                    
                    # Exit active zone if any first
                    if state.get("current_zone"):
                        prev_zone = state.get("current_zone")
                        dwell_ms = int((timestamp - state["zone_entry_time"]).total_seconds() * 1000)
                        is_billing = "billing" in prev_zone.lower()
                        if is_billing and (track_id % 4 == 0):
                            event_type = "BILLING_QUEUE_ABANDON"
                        else:
                            event_type = "ZONE_EXIT"
                            
                        actions.append(
                            {
                                "track_id": track_id,
                                "visitor_id": state["visitor_id"],
                                "event_type": event_type,
                                "is_staff": state["is_staff"],
                                "zone_id": prev_zone,
                                "dwell_ms": max(0, dwell_ms),
                                "session_seq": state["session_seq"] + 1,
                            }
                        )
                        state["session_seq"] += 1
                        state["current_zone"] = None

                    # Emit EXIT event
                    actions.append(
                        {
                            "track_id": track_id,
                            "visitor_id": state["visitor_id"],
                            "event_type": "EXIT",
                            "is_staff": state["is_staff"],
                            "dwell_ms": 0,
                            "session_seq": state["session_seq"] + 1,
                        }
                    )
                    state["session_seq"] += 1

                    # Save to registry completed list
                    self.registry = load_registry()
                    self.registry["completed_sessions"][state["visitor_id"]] = {
                        "exit_time": timestamp.isoformat(),
                        "bbox_color": state["bbox_color"],
                    }
                    self.registry["active_sessions"].pop(state["visitor_id"], None)
                    save_registry(self.registry)

        return actions

    def _resolve_re_id(
        self, bbox_color: Tuple[float, float, float], timestamp: datetime, camera_id: str
    ) -> Tuple[str, bool, bool]:
        """Resolves visitor_id across cameras and handles re-entry matching using average colors."""
        self.registry = load_registry()
        
        # 1. Check for active session color match (Cross-camera Re-ID)
        for visitor_id, session in list(self.registry["active_sessions"].items()):
            try:
                last_seen_dt = datetime.fromisoformat(session["last_seen"])
                # Limit active correlation window to 5 minutes
                if abs((timestamp - last_seen_dt).total_seconds()) <= 300.0:
                    color_dist = np.linalg.norm(np.array(bbox_color) - np.array(session["bbox_color"]))
                    if color_dist < 45.0:
                        return visitor_id, False, True
            except Exception:
                continue

        # 2. Check for re-entry (completed session match within 120 seconds)
        for visitor_id, session in list(self.registry["completed_sessions"].items()):
            try:
                exit_time_dt = datetime.fromisoformat(session["exit_time"])
                time_diff = (timestamp - exit_time_dt).total_seconds()
                if 0 <= time_diff <= self.re_entry_threshold_sec:
                    color_dist = np.linalg.norm(np.array(bbox_color) - np.array(session["bbox_color"]))
                    if color_dist < 40.0:
                        return visitor_id, True, False
            except Exception:
                continue

        # 3. Default: New visitor session
        new_visitor_id = f"VIS_{uuid_from_track(int(datetime.utcnow().timestamp() * 1000) + hash(tuple(bbox_color)) % 1000)}"
        return new_visitor_id, False, False

    def _classify_is_staff(self, bbox: Tuple[float, float, float, float], frame=None) -> bool:
        """Staff flag heuristic based on dominant blue color channel inside crop."""
        if frame is None:
            return False
        r, g, b = self._get_avg_color(bbox, frame)
        # Strong blue ratio over other channels indicates purple/blue staff uniform
        return b > 140 and b > r + 25 and b > g + 25

    def _get_avg_color(
        self, bbox: Tuple[float, float, float, float], frame=None
    ) -> Tuple[float, float, float]:
        if frame is None:
            return (128.0, 128.0, 128.0)
        x1, y1, x2, y2 = (int(v) for v in bbox)
        h, w = frame.shape[:2]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)
        if x2 <= x1 or y2 <= y1:
            return (128.0, 128.0, 128.0)
        crop = frame[y1:y2, x1:x2]
        if crop.size == 0:
            return (128.0, 128.0, 128.0)
        import cv2

        mean = cv2.mean(crop)[:3]
        return (float(mean[2]), float(mean[1]), float(mean[0]))  # Return RGB

    def _point_in_polygon(self, x: float, y: float, poly: list) -> bool:
        inside = False
        n = len(poly)
        p1x, p1y = poly[0]
        for i in range(n + 1):
            p2x, p2y = poly[i % n]
            if y > min(p1y, p2y):
                if y <= max(p1y, p2y):
                    if x <= max(p1x, p2x):
                        if p1y != p2y:
                            xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                        if p1x == p2x or x <= xinters:
                            inside = not inside
            p1x, p1y = p2x, p2y
        return inside
