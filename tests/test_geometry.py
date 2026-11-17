import numpy as np
import pytest
from pickloop.geometry import camera_matrix, backproject, project, estimate_extrinsics, quintic_trajectory, scara_ik, scara_fk


def test_optical_projection_roundtrip():
    K = camera_matrix(480, 480, 45)
    T = np.array([[1,0,0,.33],[0,-1,0,0],[0,0,-1,1.35],[0,0,0,1.]])
    points = np.array([[.33,-.2,.12],[.45,.15,.10]])
    uv, depth = project(points, K, T)
    assert np.allclose(backproject(uv, depth, K, T), points)


def test_external_calibration_from_correspondences():
    K = camera_matrix(480, 480, 45)
    T = np.array([[1,0,0,.33],[0,-1,0,0],[0,0,-1,1.35],[0,0,0,1.]])
    xyz = np.array([[x,y,.062] for y in [.25,-.25] for x in [.08,.33,.58]])
    uv, _ = project(xyz,K,T)
    estimated, error = estimate_extrinsics(xyz, uv, K)
    assert error < 1e-4
    assert np.allclose(estimated, T, atol=1e-5)


def test_bad_depth_rejected():
    with pytest.raises(ValueError):
        backproject(np.array([[20,20]]), np.array([np.nan]), np.eye(3), np.eye(4))


def test_ik_respects_workspace_and_roundtrip():
    for xyz in ([.32,-.20,.14],[.39,.19,.30]):
        q = scara_ik(np.array(xyz))
        assert np.linalg.norm(scara_fk(q)-xyz) < 1e-6
    with pytest.raises(ValueError):
        scara_ik(np.array([1.,0.,.1]))


def test_trajectory_velocity_acceleration_limits_and_endpoints():
    q0 = scara_ik(np.array([.32,-.20,.3])); q1 = scara_ik(np.array([.39,.19,.3]))
    times, q = quintic_trajectory(q0,q1,dt=.005)
    v = np.gradient(q,times,axis=0); a = np.gradient(v,times,axis=0)
    assert np.max(np.abs(v[:,:2])) <= 1.2 + .01
    assert np.max(np.abs(a[:,:2])) <= 3.0 + .05
    assert np.max(np.abs(v[:,2])) <= .3 + .01
    assert np.allclose(q[0],q0) and np.allclose(q[-1],q1)
