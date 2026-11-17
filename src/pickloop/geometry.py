"""Coordinate and bounded trajectory math; metres, radians, seconds."""
import cv2
import numpy as np

L1, L2, TCP_OFFSET_Z = .32, .28, .46
JOINT_LOWER = np.array([-2.9, -2.8, -.39, -3.14])
JOINT_UPPER = np.array([2.9, 2.8, -.02, 3.14])
VELOCITY = np.array([.9, .9, .22, 1.2])
ACCELERATION = np.array([1.5, 1.5, .35, 2.])


def camera_matrix(width, height, fovy):
    f = height / (2*np.tan(np.deg2rad(fovy)/2))
    return np.array([[f,0,width/2],[0,f,height/2],[0,0,1.]])


def backproject(uv, depth, K, T_base_camera):
    uv, depth = np.asarray(uv,float), np.asarray(depth,float)
    if not np.isfinite(depth).all() or np.any(depth <= 0):
        raise ValueError("DEPTH_INVALID")
    rays = np.column_stack([uv, np.ones(len(uv))]) @ np.linalg.inv(K).T
    p = rays * depth[:,None]
    return p @ T_base_camera[:3,:3].T + T_base_camera[:3,3]


def project(xyz, K, T_base_camera):
    p = (np.asarray(xyz)-T_base_camera[:3,3]) @ T_base_camera[:3,:3]
    if np.any(p[:,2] <= 0):
        raise ValueError("BEHIND_CAMERA")
    uvw = p @ K.T
    return uvw[:,:2]/uvw[:,2:3], p[:,2]


def estimate_extrinsics(world_points, image_points, K):
    xyz, uv = np.asarray(world_points,float), np.asarray(image_points,float)
    if len(xyz) < 6 or xyz.shape != (len(uv),3):
        raise ValueError("At least six matched calibration points required")
    ok, rvec, tvec = cv2.solvePnP(xyz,uv,K,None,flags=cv2.SOLVEPNP_ITERATIVE)
    if not ok:
        raise ValueError("CALIBRATION_FAILED")
    R, _ = cv2.Rodrigues(rvec)
    T = np.eye(4); T[:3,:3]=R.T; T[:3,3]=-R.T@tvec[:,0]
    reproj,_ = cv2.projectPoints(xyz,rvec,tvec,K,None)
    rms = float(np.sqrt(np.mean(np.sum((reproj[:,0]-uv)**2,axis=1))))
    if rms > 1.5:
        raise ValueError(f"CALIBRATION_REPROJECTION:{rms:.3f}")
    return T, rms


def scara_fk(q):
    a,b,z,_ = q
    return np.array([L1*np.cos(a)+L2*np.cos(a+b),L1*np.sin(a)+L2*np.sin(a+b),TCP_OFFSET_Z+z])


def scara_ik(xyz, yaw=0.):
    x,y,z = np.asarray(xyz,float)
    c=(x*x+y*y-L1*L1-L2*L2)/(2*L1*L2)
    if not np.isfinite([x,y,z]).all() or not -1 <= c <= 1:
        raise ValueError("IK_UNREACHABLE")
    b=np.arccos(c); a=np.arctan2(y,x)-np.arctan2(L2*np.sin(b),L1+L2*np.cos(b))
    q=np.array([a,b,z-TCP_OFFSET_Z,yaw-a-b])
    if np.any(q<JOINT_LOWER) or np.any(q>JOINT_UPPER):
        raise ValueError("JOINT_LIMIT")
    return q


def quintic_trajectory(q0,q1,dt=.005):
    q0,q1=np.asarray(q0,float),np.asarray(q1,float)
    if np.any(q1<JOINT_LOWER) or np.any(q1>JOINT_UPPER):
        raise ValueError("JOINT_LIMIT")
    delta=np.abs(q1-q0)
    duration=max(.15,float(np.max(1.875*delta/VELOCITY)),float(np.max(np.sqrt(5.78*delta/ACCELERATION))))
    n=int(np.ceil(duration/dt)); t=np.arange(n+1)*dt; u=t/t[-1]
    s=10*u**3-15*u**4+6*u**5
    return t,q0[None,:]+s[:,None]*(q1-q0)[None,:]
