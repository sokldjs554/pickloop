"""Depth instance proposals + learned crop embeddings; no simulator imports."""
from dataclasses import asdict
import cv2
import numpy as np
from .geometry import backproject
from .types import Detection, OperationError
from .vision_model import AppearanceModel

class Perception:
    def __init__(self,model_path=None): self.model=AppearanceModel(model_path)

    @staticmethod
    def proposals(obs,now_sim_time):
        try: obs.validate(now_sim_time)
        except ValueError as e: raise OperationError(str(e)) from e
        height,width=obs.depth.shape
        v,u=np.indices((height,width)); valid=np.isfinite(obs.depth)&(obs.depth>.05)&(obs.depth<3)
        cloud=np.full((height,width,3),np.nan)
        cloud[valid]=backproject(np.column_stack([u[valid],v[valid]]),obs.depth[valid],obs.K,obs.T_base_camera)
        # Declared tabletop height ROI in base frame; not a simulator mask.
        roi=valid&(cloud[:,:,2]>.086)&(cloud[:,:,2]<.19)&(cloud[:,:,0]>.10)&(cloud[:,:,0]<.60)
        n,labels,stats,centroids=cv2.connectedComponentsWithStats(roi.astype(np.uint8))
        proposals=[]
        for label,(x,y,w,h,area) in enumerate(stats[1:],start=1):
            if not 140<=area<=1500 or not 16<=w<=55 or not 16<=h<=55: continue
            points=cloud[labels==label]
            top=np.quantile(points[:,2],.80)
            surface=points[points[:,2]>top-.002]
            if len(surface)<100: continue
            pos=np.median(surface,axis=0)
            if np.std(surface[:,2])>.003: continue
            x0,y0=max(0,x-1),max(0,y-1); x1,y1=min(width,x+w+1),min(height,y+h+1)
            crop=obs.rgb[y0:y1,x0:x1].copy()
            proposals.append({'crop':crop,'position':pos,'bbox':(int(x0),int(y0),int(x1-x0),int(y1-y0)),'depth_valid_ratio':float(np.mean(valid[y:y+h,x:x+w])),'uncertainty_m':float(np.std(surface[:,2])+.002)})
        return proposals

    def detect(self,obs,now_sim_time):
        proposals=self.proposals(obs,now_sim_time)
        if not proposals: return []
        predictions=self.model.predict([p['crop'] for p in proposals])
        return [Detection(sku=pred['sku'],confidence=float(pred['confidence']),position=p['position'],bbox=p['bbox'],depth_valid_ratio=p['depth_valid_ratio'],observation_id=obs.observation_id,uncertainty_m=p['uncertainty_m'],distance=float(pred['distance'])) for p,pred in zip(proposals,predictions)]

    def target(self,obs,now_sim_time,sku):
        detections=self.detect(obs,now_sim_time)
        selected=[d for d in detections if d.sku==sku]
        if len(selected)!=1:
            raise OperationError('TARGET_NOT_FOUND' if not selected else 'TARGET_AMBIGUOUS',{'detected':[d.sku for d in detections]})
        d=selected[0]
        if d.depth_valid_ratio<.8 or d.uncertainty_m>.006: raise OperationError('DEPTH_UNCERTAIN')
        return d,detections

    @staticmethod
    def serialize(d):
        result=asdict(d);result['position']=d.position.tolist();return result
