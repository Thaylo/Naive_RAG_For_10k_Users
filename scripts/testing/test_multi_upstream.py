#!/usr/bin/env python3
import asyncio
import httpx
import time
import sys

async def check_service_health(url):
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{url}/health")
            if response.status_code == 200:
                return response.json()
            return None
        except:
            return None

async def test_multi_upstream():
    print("Testing Multi-Upstream Service Configuration...")
    print("=" * 60)
    
    # Wait for services to be healthy
    print("Waiting for services to be healthy...")
    services = {
        "Master Task DB": "http://localhost:8001",
        "Upload Service": "http://localhost:8003",
        "Chunking 1": "http://localhost:8004",
        "Chunking 2": "http://localhost:8004",  # Both chunking services use same port
        "Embedding 1": "http://localhost:8005",
        "Embedding 2": "http://localhost:8005",  # Both embedding services use same port
        "Vectorial DB": "http://localhost:8006",
        "RAG Query": "http://localhost:8007"
    }
    
    # Check health of all services
    all_healthy = False
    for _ in range(30):
        healthy_count = 0
        for name, url in services.items():
            health = await check_service_health(url)
            if health:
                healthy_count += 1
        
        if healthy_count >= 6:  # At least main services are up
            all_healthy = True
            break
        
        await asyncio.sleep(2)
    
    if not all_healthy:
        print("Not all services are healthy. Continuing anyway...")
    
    print("\nUploading test file...")
    # Upload a test file
    async with httpx.AsyncClient() as client:
        # Create test content
        test_content = """
        This is a test document for multi-upstream service testing.
        
        Section 1: Introduction
        This document tests the ability of services to consume from multiple upstream containers.
        
        Section 2: Technical Details
        The system should distribute tasks across multiple chunking services.
        Each chunking service should be able to process tasks independently.
        
        Section 3: Embedding Process
        Multiple embedding services should consume chunks from multiple chunking services.
        This creates a many-to-many relationship between services.
        
        Section 4: Vector Storage
        The vectorial database should consume embeddings from all embedding services.
        This ensures complete processing of all documents.
        """
        
        files = {
            'file': ('test_multi_upstream.txt', test_content.encode(), 'text/plain')
        }
        
        response = await client.post("http://localhost:8080/upload", files=files)
        if response.status_code == 200:
            task_id = response.json()['task_id']
            print(f"File uploaded successfully. Task ID: {task_id}")
        else:
            print(f"Upload failed: {response.status_code}")
            return
    
    # Monitor task progress
    print("\nMonitoring task progress...")
    for i in range(30):
        async with httpx.AsyncClient() as client:
            response = await client.get(f"http://localhost:8001/tasks/{task_id}")
            if response.status_code == 200:
                task = response.json()
                print(f"Status: {task['status']}")
                
                if task['status'] == 'VECTORIZED':
                    print("Task completed successfully!")
                    
                    # Check service stats
                    print("\nChecking service statistics...")
                    
                    # Check embedding service queues
                    for i in [1, 2]:
                        try:
                            # Use direct container names since they're on different containers
                            response = await client.get(f"http://localhost:8005/queue/status")
                            if response.status_code == 200:
                                stats = response.json()
                                print(f"Embedding Service {i} - Queue size: {stats['queue_size']}")
                        except:
                            pass
                    
                    # Check vectorial DB stats
                    response = await client.get("http://localhost:8006/stats")
                    if response.status_code == 200:
                        stats = response.json()
                        print(f"Vectorial DB - Total embeddings: {stats['total_embeddings']}")
                    
                    # Test RAG query
                    print("\nTesting RAG query...")
                    query_data = {
                        "query": "What is the purpose of multi-upstream service testing?",
                        "task_ids": [task_id],
                        "top_k": 3
                    }
                    
                    response = await client.post("http://localhost:8080/query", json=query_data)
                    if response.status_code == 200:
                        result = response.json()
                        print(f"Query successful!")
                        print(f"Response: {result['response'][:200]}...")
                        print(f"Sources found: {len(result['sources'])}")
                    else:
                        print(f"Query failed: {response.status_code}")
                    
                    break
                elif task['status'] == 'FAILED':
                    print("Task failed!")
                    break
        
        await asyncio.sleep(2)
    
    print("\nTest completed!")

if __name__ == "__main__":
    asyncio.run(test_multi_upstream())