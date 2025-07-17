import pytest
from fastapi.testclient import TestClient

from services.chunk_config.main import app, config_service
from shared.models.chunk import ChunkConfig


@pytest.fixture
def client():
    config_service.config = ChunkConfig()
    config_service.subscribers.clear()
    config_service.update_history.clear()
    return TestClient(app)


class TestChunkConfigService:
    @pytest.mark.asyncio
    async def test_get_config(self):
        service = config_service
        config = await service.get_config()
        
        assert isinstance(config, ChunkConfig)
        assert config.chunk_size == 1000
        assert config.overlap_percentage == 0.1
        assert config.strategy == "fixed_size"
    
    @pytest.mark.asyncio
    async def test_update_config(self):
        service = config_service
        new_config = ChunkConfig(
            chunk_size=2000,
            overlap_percentage=0.2,
            strategy="fixed_size"
        )
        
        updated = await service.update_config(new_config)
        
        assert updated.chunk_size == 2000
        assert updated.overlap_percentage == 0.2
        assert len(service.update_history) == 1
        assert service.update_history[0]["config"]["chunk_size"] == 2000
    
    def test_subscribe_unsubscribe(self):
        service = config_service
        
        service.subscribe("service-1")
        assert "service-1" in service.subscribers
        
        service.subscribe("service-1")
        assert service.subscribers.count("service-1") == 1
        
        service.subscribe("service-2")
        assert len(service.subscribers) == 2
        
        service.unsubscribe("service-1")
        assert "service-1" not in service.subscribers
        assert "service-2" in service.subscribers
        
        service.unsubscribe("non-existent")


class TestAPI:
    def test_get_config_endpoint(self, client):
        response = client.get("/config")
        assert response.status_code == 200
        data = response.json()
        assert data["chunk_size"] == 1000
        assert data["overlap_percentage"] == 0.1
        assert data["strategy"] == "fixed_size"
    
    def test_update_config_endpoint(self, client):
        new_config = {
            "chunk_size": 1500,
            "overlap_percentage": 0.15,
            "strategy": "fixed_size"
        }
        
        response = client.put("/config", json=new_config)
        assert response.status_code == 200
        data = response.json()
        assert data["chunk_size"] == 1500
        assert data["overlap_percentage"] == 0.15
        
        response = client.get("/config")
        assert response.json()["chunk_size"] == 1500
    
    def test_config_validation(self, client):
        invalid_configs = [
            {"chunk_size": 50, "overlap_percentage": 0.1},
            {"chunk_size": 6000, "overlap_percentage": 0.1},
            {"chunk_size": 1000, "overlap_percentage": -0.1},
            {"chunk_size": 1000, "overlap_percentage": 0.6},
        ]
        
        for config in invalid_configs:
            response = client.put("/config", json=config)
            assert response.status_code == 422
    
    def test_subscribe_endpoint(self, client):
        response = client.post("/subscribe?service_id=test-service")
        assert response.status_code == 200
        assert response.json()["status"] == "subscribed"
        assert response.json()["service_id"] == "test-service"
        
        response = client.get("/subscribers")
        assert "test-service" in response.json()["subscribers"]
    
    def test_unsubscribe_endpoint(self, client):
        client.post("/subscribe?service_id=test-service")
        
        response = client.delete("/subscribe/test-service")
        assert response.status_code == 200
        assert response.json()["status"] == "unsubscribed"
        
        response = client.get("/subscribers")
        assert "test-service" not in response.json()["subscribers"]
    
    def test_history_endpoint(self, client):
        client.put("/config", json={"chunk_size": 1200, "overlap_percentage": 0.1})
        client.put("/config", json={"chunk_size": 1300, "overlap_percentage": 0.2})
        
        response = client.get("/history")
        assert response.status_code == 200
        history = response.json()["history"]
        assert len(history) == 2
        assert history[0]["config"]["chunk_size"] == 1200
        assert history[1]["config"]["chunk_size"] == 1300
    
    def test_health_check_endpoint(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
        assert response.json()["service"] == "chunk_config"