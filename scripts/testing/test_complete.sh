#!/bin/bash

echo "=== Complete RAG Pipeline Test ==="
echo

# 1. Check all services are healthy
echo "1. Checking service health..."
for service in 8001 8002 8003 8006 8007; do
    status=$(curl -s http://localhost:$service/health | jq -r .status 2>/dev/null || echo "failed")
    echo "   Port $service: $status"
done
echo

# 2. Create a test PDF with actual content using Python
echo "2. Creating test PDF with content..."
python3 -c "
from pypdf import PdfWriter, PdfReader
from io import BytesIO

# Create a writer
writer = PdfWriter()

# Create a page with text
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter

# Create a BytesIO buffer
buffer = BytesIO()
c = canvas.Canvas(buffer, pagesize=letter)

# Add substantial text content
y_position = 750
texts = [
    'Naive RAG System Test Document',
    '',
    'This is a comprehensive test document for validating the Naive RAG pipeline.',
    'The system architecture includes multiple microservices:',
    '',
    '1. Upload Service - Handles document uploads and file management',
    '2. Chunking Service - Splits documents into processable chunks',
    '3. Embedding Service - Generates vector embeddings using mock LLMs',
    '4. Vectorial Database - Stores and retrieves embeddings efficiently',
    '5. RAG Query Service - Processes user queries and generates responses',
    '',
    'Key Features:',
    '- Scalable to 10,000 concurrent users',
    '- Microservices architecture for independent scaling',
    '- Mock LLM integration for testing',
    '- Comprehensive logging and monitoring',
    '- Docker-based deployment',
    '',
    'This document contains enough text to properly test the chunking algorithm',
    'and ensure that all services in the pipeline work correctly together.',
    'The system should process this document through all stages successfully.'
]

for text in texts:
    c.drawString(50, y_position, text)
    y_position -= 20

c.save()

# Write the PDF
buffer.seek(0)
with open('test_content.pdf', 'wb') as f:
    f.write(buffer.read())

print('Created test_content.pdf with actual text content')
" 2>/dev/null || {
    # Fallback: Create a simple text file and convert it
    echo "Creating test document with text content..." > test_content.txt
    echo "" >> test_content.txt
    echo "This is a test document for the Naive RAG system." >> test_content.txt
    echo "The system processes documents through multiple stages:" >> test_content.txt
    echo "1. Upload - Files are uploaded and stored" >> test_content.txt
    echo "2. Chunking - Documents are split into chunks" >> test_content.txt
    echo "3. Embedding - Chunks are converted to vectors" >> test_content.txt
    echo "4. Storage - Vectors are stored in the database" >> test_content.txt
    echo "5. Query - Users can search the content" >> test_content.txt
    echo "" >> test_content.txt
    echo "This document has enough content to test the entire pipeline." >> test_content.txt
    
    # Try to convert to PDF using available tools
    if command -v ps2pdf &> /dev/null; then
        # Convert text to PostScript then to PDF
        enscript -p - test_content.txt 2>/dev/null | ps2pdf - test_content.pdf 2>/dev/null
    elif command -v cupsfilter &> /dev/null; then
        # Use CUPS to convert
        cupsfilter test_content.txt > test_content.pdf 2>/dev/null
    else
        # Create a minimal PDF with the text content
        cat > test_content.pdf << 'PDFEOF'
%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 4 0 R >> >> /MediaBox [0 0 612 792] /Contents 5 0 R >>
endobj
4 0 obj
<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>
endobj
5 0 obj
<< /Length 400 >>
stream
BT
/F1 12 Tf
50 750 Td
(Test Document for Naive RAG System) Tj
0 -20 Td
(This document tests the complete pipeline:) Tj
0 -20 Td
(1. Upload Service processes the file) Tj
0 -20 Td
(2. Chunking Service splits the content) Tj
0 -20 Td
(3. Embedding Service creates vectors) Tj
0 -20 Td
(4. Vector Database stores embeddings) Tj
0 -20 Td
(5. Query Service enables searching) Tj
ET
endstream
endobj
xref
0 6
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000229 00000 n 
0000000307 00000 n 
trailer
<< /Size 6 /Root 1 0 R >>
startxref
756
%%EOF
PDFEOF
    fi
    
    echo "Created test_content.pdf"
}

# 3. Upload the PDF
echo
echo "3. Uploading PDF..."
response=$(curl -s -X POST http://localhost:8080/upload/upload \
    -F "files=@test_content.pdf" | jq .)
echo "$response"
task_id=$(echo "$response" | jq -r '.results[0].task_id // "none"')
echo "Task ID: $task_id"
echo

# 4. Monitor task progress
if [ "$task_id" != "none" ]; then
    echo "4. Monitoring task progress..."
    for i in {1..20}; do
        status=$(curl -s http://localhost:8001/tasks/$task_id | jq -r .status 2>/dev/null || echo "not found")
        echo "   Attempt $i: Status = $status"
        
        if [ "$status" == "VECTORIZED" ] || [ "$status" == "vectorized" ]; then
            echo "   ✓ Task completed successfully!"
            
            # 5. Test the query endpoint
            echo
            echo "5. Testing query endpoint..."
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

# 6. Check final statistics
echo
echo "6. System statistics:"
echo "Vector DB stats:"
curl -s http://localhost:8006/stats | jq .

# Cleanup
rm -f test_content.txt test_content.pdf

echo
echo "Test complete!"