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
