import numpy as np
from typing import List
import hashlib


class MockEmbeddingLLM:
    def __init__(self, dimension: int = 384):
        self.dimension = dimension
    
    def generate_embedding(self, text: str) -> List[float]:
        hash_obj = hashlib.md5(text.encode())
        seed = int(hash_obj.hexdigest(), 16) % (2**32)
        np.random.seed(seed)
        
        embedding = np.random.randn(self.dimension)
        embedding = embedding / np.linalg.norm(embedding)
        
        return embedding.tolist()
    
    def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        return [self.generate_embedding(text) for text in texts]


class MockChatLLM:
    def __init__(self):
        self.responses = {
            "default": "Esta é uma resposta mockada do sistema RAG. Em produção, aqui estaria a resposta real do LLM baseada no contexto fornecido.",
            "greeting": "Olá! Sou um assistente RAG mockado. Como posso ajudá-lo hoje?",
            "error": "Desculpe, não consegui processar sua solicitação no momento."
        }
    
    def generate_response(self, prompt: str, context: str = "") -> str:
        prompt_lower = prompt.lower()
        
        if any(greeting in prompt_lower for greeting in ["olá", "oi", "hello", "hi"]):
            return self.responses["greeting"]
        
        if context:
            return f"Baseado no contexto fornecido: {context[:100]}... {self.responses['default']}"
        
        return self.responses["default"]