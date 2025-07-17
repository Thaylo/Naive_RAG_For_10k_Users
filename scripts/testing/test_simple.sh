#!/bin/bash

echo "=== Simple RAG Pipeline Test ===="
echo

# 1. Create a simple text file with substantial content
echo "Creating test.txt with content..."
cat > test.txt << 'EOF'
Naive RAG System Documentation

This is a comprehensive test document for the Naive RAG system designed to handle 10,000 concurrent users.

System Architecture Overview:
The system uses a microservices architecture with the following components:

1. Upload Service
   - Handles file uploads and validation
   - Stores files in a distributed storage system
   - Manages file metadata and task creation

2. Chunking Service
   - Processes uploaded documents
   - Splits content into manageable chunks
   - Supports multiple file formats including PDF, TXT, and DOCX

3. Embedding Service
   - Creates vector embeddings for text chunks
   - Uses mock LLM for testing purposes
   - Generates 768-dimensional embeddings

4. Vectorial Database Service
   - Stores and indexes vector embeddings
   - Provides fast similarity search
   - Supports cosine similarity metrics

5. RAG Query Service
   - Processes user queries
   - Retrieves relevant document chunks
   - Generates responses using retrieved context

Key Features:
- Scalable to 10,000 concurrent users
- Microservices architecture for independent scaling
- Comprehensive logging and monitoring
- Docker-based deployment
- RESTful API design
- Asynchronous processing

Performance Characteristics:
- Sub-second query response times
- Handles documents up to 100MB
- Processes multiple file formats
- Efficient vector search algorithms

This document contains sufficient text to test the chunking algorithm and ensure proper processing through all pipeline stages.
The system should successfully chunk this text file and process it through embedding and vectorization.
Each chunk will be converted to a vector representation that can be searched efficiently.
The query service will then be able to find relevant chunks based on user queries.
EOF

# 2. Upload the text file
echo
echo "Uploading test.txt..."
response=$(curl -s -X POST http://localhost:8080/upload/upload \
    -F "files=@test.txt" | jq .)
echo "$response"
task_id=$(echo "$response" | jq -r '.results[0].task_id // "none"')
echo "Task ID: $task_id"
echo

# 3. Monitor task progress
if [ "$task_id" != "none" ]; then
    echo "Monitoring task progress..."
    for i in {1..20}; do
        status=$(curl -s http://localhost:8001/tasks/$task_id | jq -r .status 2>/dev/null || echo "not found")
        echo "   Attempt $i: Status = $status"
        
        if [ "$status" == "VECTORIZED" ] || [ "$status" == "vectorized" ]; then
            echo "   ✓ Task completed successfully!"
            
            # 4. Test the query endpoint
            echo
            echo "Testing query endpoint..."
            query_response=$(curl -s -X POST http://localhost:8080/rag-query/query \
                -H "Content-Type: application/json" \
                -d '{
                    "query": "What services are included in the RAG system?",
                    "task_ids": ["'$task_id'"],
                    "top_k": 3
                }' | jq .)
            echo "Query response:"
            echo "$query_response"
            
            break
        elif [ "$status" == "FAILED" ] || [ "$status" == "failed" ]; then
            echo "   ✗ Task failed!"
            curl -s http://localhost:8001/tasks/$task_id | jq .
            break
        fi
        sleep 3
    done
fi

# 5. Check final statistics
echo
echo "System statistics:"
echo "Vector DB stats:"
curl -s http://localhost:8006/stats | jq .

# Cleanup
rm -f test.txt

echo
echo "Test complete!"