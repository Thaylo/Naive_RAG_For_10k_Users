from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import httpx
import os
from typing import List, Optional

from shared.utils.mock_llm import MockEmbeddingLLM, MockChatLLM
from shared.utils.logging_config import setup_logger, log_request, log_response, log_error


class QueryRequest(BaseModel):
    query: str
    task_ids: Optional[List[str]] = None
    top_k: int = 5


class QueryResponse(BaseModel):
    query: str
    response: str
    sources: List[dict]


class RAGQueryService:
    def __init__(self):
        self.logger = setup_logger("rag-query-service", os.getenv("LOG_LEVEL", "INFO"))
        self.embedding_llm = MockEmbeddingLLM()
        self.chat_llm = MockChatLLM()
        # Support multiple vectorial DB and chunking services
        vectorial_urls = os.getenv("VECTORIAL_DB_URLS", "http://vectorial-db:8006")
        self.vectorial_db_urls = [url.strip() for url in vectorial_urls.split(",")]
        chunking_urls = os.getenv("CHUNKING_SERVICE_URLS", "http://chunking-1:8004,http://chunking-2:8004")
        self.chunking_service_urls = [url.strip() for url in chunking_urls.split(",")]
        self.logger.info("RAGQueryService initialized")
        self.logger.info(f"URLs - Vectorial DBs: {self.vectorial_db_urls}, Chunking: {self.chunking_service_urls}")
    
    async def process_query(self, query_request: QueryRequest) -> QueryResponse:
        self.logger.info(f"Processing query: {query_request.query[:50]}...")
        query_embedding = self.embedding_llm.generate_embedding(query_request.query)
        self.logger.debug(f"Generated query embedding with dimension {len(query_embedding)}")
        
        async with httpx.AsyncClient() as client:
            # Try each vectorial DB until we get a successful response
            search_results = []
            for db_url in self.vectorial_db_urls:
                try:
                    search_response = await client.post(
                        f"{db_url}/search",
                        json={
                            "query_vector": query_embedding,
                            "top_k": query_request.top_k,
                            "task_ids": query_request.task_ids
                        }
                    )
                    
                    if search_response.status_code == 200:
                        search_results.extend(search_response.json()["results"])
                except Exception as e:
                    self.logger.warning(f"Failed to search in {db_url}: {e}")
            
            if not search_results:
                raise HTTPException(status_code=500, detail="Failed to search embeddings")
            
            # Sort all results by score and take top_k
            search_results.sort(key=lambda x: x["score"], reverse=True)
            search_results = search_results[:query_request.top_k]
            self.logger.info(f"Found {len(search_results)} matching results across all DBs")
            
            context_chunks = []
            for result in search_results:
                chunk_id = result["metadata"]["chunk_id"]
                task_id = result["metadata"]["task_id"]
                
                # Try each chunking service until we find the chunk
                chunk_found = False
                for chunking_url in self.chunking_service_urls:
                    if chunk_found:
                        break
                    try:
                        chunks_response = await client.get(
                            f"{chunking_url}/chunks/{task_id}"
                        )
                        if chunks_response.status_code == 200:
                            chunks = chunks_response.json()["chunks"]
                            for chunk in chunks:
                                if chunk["id"] == chunk_id:
                                    context_chunks.append(chunk["content"])
                                    chunk_found = True
                                    break
                    except Exception as e:
                        self.logger.debug(f"Chunk not in {chunking_url}: {e}")
                
                if not chunk_found:
                    self.logger.warning(f"Failed to find chunk {chunk_id} for task {task_id} in any service")
            
            context = "\n\n".join(context_chunks[:3])
            
            prompt = f"""
            Pergunta: {query_request.query}
            
            Contexto relevante:
            {context}
            
            Por favor, responda à pergunta baseando-se no contexto fornecido.
            """
            
            response = self.chat_llm.generate_response(prompt, context)
            self.logger.info(f"Generated response of length {len(response)}")
            
            sources = []
            for i, result in enumerate(search_results[:3]):
                sources.append({
                    "chunk_id": result["metadata"]["chunk_id"],
                    "task_id": result["metadata"]["task_id"],
                    "score": result["score"]
                })
            
            return QueryResponse(
                query=query_request.query,
                response=response,
                sources=sources
            )


rag_service = RAGQueryService()
app = FastAPI(title="RAG Query Service")


@app.post("/query", response_model=QueryResponse)
async def query_rag(query_request: QueryRequest):
    log_request(rag_service.logger, "POST", "/query", query=query_request.query[:50])
    try:
        response = await rag_service.process_query(query_request)
        log_response(rag_service.logger, "POST", "/query", 200)
        return response
    except Exception as e:
        log_error(rag_service.logger, e, "query_rag")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "rag_query"}