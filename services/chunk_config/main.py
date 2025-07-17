from fastapi import FastAPI, HTTPException
from typing import Dict, List
import asyncio
import os
from datetime import datetime

from shared.models.chunk import ChunkConfig
from shared.utils.logging_config import setup_logger, log_request, log_response, log_error


class ChunkConfigService:
    def __init__(self):
        self.logger = setup_logger("chunk-config-service", os.getenv("LOG_LEVEL", "INFO"))
        self.config = ChunkConfig()
        self.subscribers: List[str] = []
        self.update_history: List[Dict] = []
        self.logger.info("ChunkConfigService initialized")
        self.logger.info(f"Default config: chunk_size={self.config.chunk_size}, overlap={self.config.overlap_percentage}")
    
    async def get_config(self) -> ChunkConfig:
        return self.config
    
    async def update_config(self, new_config: ChunkConfig) -> ChunkConfig:
        old_config = self.config
        self.config = new_config
        self.update_history.append({
            "timestamp": datetime.utcnow().isoformat(),
            "config": new_config.dict()
        })
        self.logger.info(f"Config updated: chunk_size {old_config.chunk_size}->{new_config.chunk_size}, overlap {old_config.overlap_percentage}->{new_config.overlap_percentage}")
        await self.notify_subscribers()
        return self.config
    
    async def notify_subscribers(self):
        pass
    
    def subscribe(self, service_id: str):
        if service_id not in self.subscribers:
            self.subscribers.append(service_id)
            self.logger.info(f"Service {service_id} subscribed to config updates")
    
    def unsubscribe(self, service_id: str):
        if service_id in self.subscribers:
            self.subscribers.remove(service_id)
            self.logger.info(f"Service {service_id} unsubscribed from config updates")


config_service = ChunkConfigService()
app = FastAPI(title="Chunk Config Service")


@app.get("/config", response_model=ChunkConfig)
async def get_config():
    log_request(config_service.logger, "GET", "/config")
    config = await config_service.get_config()
    log_response(config_service.logger, "GET", "/config", 200)
    return config


@app.put("/config", response_model=ChunkConfig)
async def update_config(config: ChunkConfig):
    log_request(config_service.logger, "PUT", "/config", chunk_size=config.chunk_size, overlap=config.overlap_percentage)
    updated_config = await config_service.update_config(config)
    log_response(config_service.logger, "PUT", "/config", 200)
    return updated_config


@app.post("/subscribe")
async def subscribe(service_id: str):
    log_request(config_service.logger, "POST", "/subscribe", service_id=service_id)
    config_service.subscribe(service_id)
    log_response(config_service.logger, "POST", "/subscribe", 200)
    return {"status": "subscribed", "service_id": service_id}


@app.delete("/subscribe/{service_id}")
async def unsubscribe(service_id: str):
    config_service.unsubscribe(service_id)
    return {"status": "unsubscribed", "service_id": service_id}


@app.get("/subscribers")
async def get_subscribers():
    return {"subscribers": config_service.subscribers}


@app.get("/history")
async def get_update_history():
    return {"history": config_service.update_history}


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "chunk_config"}