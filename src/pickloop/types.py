from dataclasses import dataclass
import time
import numpy as np

@dataclass(frozen=True)
class Observation:
    run_id: str
    observation_id: str
    sim_time: float
    received_ns: int
    rgb: np.ndarray
    depth: np.ndarray
    K: np.ndarray
    T_base_camera: np.ndarray
    calibration_id: str

    def validate(self, now_sim_time, max_age=.35):
        if now_sim_time-self.sim_time > max_age or self.sim_time>now_sim_time+.001:
            raise ValueError("OBSERVATION_STALE")
        if (time.monotonic_ns()-self.received_ns)/1e9 > 5:
            raise ValueError("TRANSPORT_STALE")
        if self.rgb.shape[:2] != self.depth.shape or self.rgb.shape[-1] != 3:
            raise ValueError("SENSOR_SHAPE")

@dataclass(frozen=True)
class Detection:
    sku: str
    confidence: float
    position: np.ndarray
    bbox: tuple
    depth_valid_ratio: float
    observation_id: str
    uncertainty_m: float
    distance: float = 0.

class OperationError(RuntimeError):
    def __init__(self, code, detail=None):
        self.code=code; self.detail=detail or {}
        super().__init__(code)
