import numpy as np
import pytest
from pickloop.perception import Perception
from pickloop.simulation import Cell
from pickloop.types import OperationError

def test_actual_rgbd_targets_and_unknown():
    with Cell(seed=2) as c:
        detections=Perception().detect(c.observe(),c.sim_time)
        assert {'SKU-RED-A','SKU-RED-B','UNKNOWN'} <= {d.sku for d in detections}
        target=next(d for d in detections if d.sku=='SKU-RED-A')
        truth=c.truth_summary()['objects'][0]['position']
        assert np.linalg.norm(target.position[:2]-truth[:2]) < .008
        assert abs(target.position[2]-(truth[2]+.025)) < .005

def test_missing_depth_rejects_target():
    with Cell(seed=2,fault='depth_missing') as c:
        with pytest.raises(OperationError,match='TARGET_NOT_FOUND'):
            Perception().target(c.observe(),c.sim_time,'SKU-RED-A')

def test_stale_frame_rejected():
    with Cell(seed=2,fault='stale_observation') as c:
        with pytest.raises(OperationError,match='OBSERVATION_STALE'):
            Perception().detect(c.observe(),c.sim_time)
