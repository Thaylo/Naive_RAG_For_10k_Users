#!/bin/bash

echo "=== RAG Pipeline Test ==="
echo

# 1. Check all services are healthy
echo "1. Checking service health..."
for service in 8001 8002 8003 8006 8007; do
    status=$(curl -s http://localhost:$service/health | jq -r .status 2>/dev/null || echo "failed")
    echo "   Port $service: $status"
done
echo

# 2. Check current tasks
echo "2. Current tasks:"
curl -s http://localhost:8001/tasks/ | jq length
echo

# 3. Check chunk config
echo "3. Chunk configuration:"
curl -s http://localhost:8002/config | jq .
echo

# 4. Create a test PDF
echo "4. Creating test PDF..."
cat > test.pdf << 'EOF'
%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R >>
endobj
xref
0 4
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
trailer
<< /Size 4 /Root 1 0 R >>
startxref
164
%%EOF
EOF

# 5. Upload the PDF
echo "5. Uploading PDF..."
response=$(curl -s -X POST http://localhost:8080/upload/upload \
    -F "files=@test.pdf" | jq .)
echo "$response"
task_id=$(echo "$response" | jq -r '.results[0].task_id // "none"')
echo "Task ID: $task_id"
echo

# 6. Monitor task progress
if [ "$task_id" != "none" ]; then
    echo "6. Monitoring task progress..."
    for i in {1..10}; do
        status=$(curl -s http://localhost:8001/tasks/$task_id | jq -r .status 2>/dev/null || echo "not found")
        echo "   Attempt $i: Status = $status"
        if [ "$status" == "VECTORIZED" ] || [ "$status" == "vectorized" ]; then
            echo "   Task completed!"
            break
        elif [ "$status" == "FAILED" ] || [ "$status" == "failed" ]; then
            echo "   Task failed!"
            curl -s http://localhost:8001/tasks/$task_id | jq .
            break
        fi
        sleep 2
    done
fi

# 7. Check logs
echo
echo "7. Recent logs:"
echo "Upload logs:"
tail -5 logs/upload-service.log 2>/dev/null || echo "No logs"
echo
echo "Chunking logs:"
tail -5 logs/chunking-service.log 2>/dev/null || echo "No logs"

rm -f test.pdf