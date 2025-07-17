#!/bin/bash

echo "=== Testing RAG Pipeline with CV PDF ===="
echo

# 1. Check all services are healthy
echo "1. Checking service health..."
for service in 8001 8002 8003 8006 8007; do
    status=$(curl -s http://localhost:$service/health | jq -r .status 2>/dev/null || echo "failed")
    echo "   Port $service: $status"
done
echo

# 2. Upload the CV PDF
echo "2. Uploading CV PDF..."
response=$(curl -s -X POST http://localhost:8080/upload/upload \
    -F "files=@Data/CV Thaylo de Freitas en-us.pdf" | jq .)
echo "$response"
task_id=$(echo "$response" | jq -r '.results[0].task_id // "none"')
echo "Task ID: $task_id"
echo

# 3. Monitor task progress
if [ "$task_id" != "none" ]; then
    echo "3. Monitoring task progress..."
    for i in {1..30}; do
        status=$(curl -s http://localhost:8001/tasks/$task_id | jq -r .status 2>/dev/null || echo "not found")
        echo "   Attempt $i: Status = $status"
        
        if [ "$status" == "VECTORIZED" ] || [ "$status" == "vectorized" ]; then
            echo "   ✓ Task completed successfully!"
            
            # 4. Test the query endpoint
            echo
            echo "4. Testing query endpoint..."
            
            # Query about experience
            echo "Query 1: What is Thaylo's work experience?"
            query_response=$(curl -s -X POST http://localhost:8080/rag-query/query \
                -H "Content-Type: application/json" \
                -d '{
                    "query": "What is Thaylo'\''s work experience?",
                    "task_ids": ["'$task_id'"],
                    "top_k": 3
                }' | jq .)
            echo "$query_response"
            
            echo
            echo "Query 2: What programming languages does Thaylo know?"
            query_response=$(curl -s -X POST http://localhost:8080/rag-query/query \
                -H "Content-Type: application/json" \
                -d '{
                    "query": "What programming languages does Thaylo know?",
                    "task_ids": ["'$task_id'"],
                    "top_k": 3
                }' | jq .)
            echo "$query_response"
            
            break
        elif [ "$status" == "FAILED" ] || [ "$status" == "failed" ]; then
            echo "   ✗ Task failed!"
            curl -s http://localhost:8001/tasks/$task_id | jq .
            
            # Check the chunks
            echo
            echo "Checking chunks for debugging..."
            curl -s http://localhost:8003/chunks/$task_id | jq . || echo "No chunks endpoint"
            break
        fi
        sleep 3
    done
fi

# 5. Check final statistics
echo
echo "5. System statistics:"
echo "Vector DB stats:"
curl -s http://localhost:8006/stats | jq .

echo
echo "Test complete!"