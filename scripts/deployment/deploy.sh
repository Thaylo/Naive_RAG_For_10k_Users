#!/bin/bash

echo "======================================="
echo "Naive RAG Deployment Script"
echo "======================================="

echo "Verificando Docker..."
if ! command -v docker &> /dev/null; then
    echo "Docker não está instalado. Por favor, instale o Docker primeiro."
    exit 1
fi

if ! docker info &> /dev/null; then
    echo "Docker daemon não está rodando. Por favor, inicie o Docker."
    exit 1
fi

echo "Parando containers existentes..."
docker compose down

echo "Removendo volumes antigos..."
docker compose down -v

echo "Criando diretório de uploads se não existir..."
mkdir -p storage/uploads

echo "Construindo imagens Docker..."
docker compose build --no-cache

echo "Iniciando serviços..."
docker compose up -d

echo "Aguardando serviços iniciarem..."
sleep 10

echo "Verificando status dos serviços..."
docker compose ps

echo "======================================="
echo "Serviços disponíveis:"
echo "- Upload Service: http://localhost:8003"
echo "- Chunk Config: http://localhost:8002"
echo "- RAG Query: http://localhost:8007"
echo "- Nginx Gateway: http://localhost:8080"
echo "======================================="

echo "Para ver os logs, use: docker compose logs -f"
echo "Para parar os serviços, use: docker compose down"