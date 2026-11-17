from fastapi.testclient import TestClient
from pickloop.server import create_app

def test_health_and_invalid_requests(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        assert client.get('/api/health').json()['mode']=='live'
        assert client.post('/api/jobs',json={'seed':-1}).status_code==422
        assert client.post('/api/jobs',json={'fault':'invented'}).status_code==422
        assert client.get('/api/jobs/missing').status_code==404
        assert client.post('/api/jobs/missing/cancel').status_code==404
        assert client.post('/api/jobs',json={},headers={'origin':'https://untrusted.invalid'}).status_code==403

def test_restart_reports_interrupted_job_without_resubmission(tmp_path):
    from pickloop.journal import JobStore
    s=JobStore(tmp_path/'jobs.sqlite');s.begin('interrupted',{'seed':4},'run-interrupted');s.transition('interrupted','TRANSPORT');s.close()
    with TestClient(create_app(tmp_path)) as client:
        response=client.get('/api/jobs/interrupted')
        assert response.status_code==200
        assert response.json()['status']=='HOLD_RECOVERY_REQUIRED'
