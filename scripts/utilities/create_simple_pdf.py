import struct

def create_simple_pdf(filename, text_content):
    """Create a simple PDF with actual text content that can be extracted"""
    
    # PDF header
    pdf_content = b"%PDF-1.4\n"
    
    # Define objects
    objects = []
    
    # Object 1: Catalog
    objects.append(b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")
    
    # Object 2: Pages
    objects.append(b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n")
    
    # Object 3: Page
    objects.append(b"3 0 obj\n<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 4 0 R >> >> /MediaBox [0 0 612 792] /Contents 5 0 R >>\nendobj\n")
    
    # Object 4: Font
    objects.append(b"4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n")
    
    # Object 5: Content stream
    # Build the text operations
    text_operations = b"BT\n/F1 12 Tf\n50 750 Td\n"
    
    # Split text into lines and add each line
    lines = text_content.split('\n')
    for i, line in enumerate(lines):
        if i > 0:
            text_operations += b"0 -15 Td\n"  # Move down 15 units
        # Escape parentheses in the text
        escaped_line = line.replace('(', '\\(').replace(')', '\\)').replace('\\', '\\\\')
        text_operations += f"({escaped_line}) Tj\n".encode('latin-1')
    
    text_operations += b"ET\n"
    
    # Create content stream object
    content_length = len(text_operations)
    content_obj = f"5 0 obj\n<< /Length {content_length} >>\nstream\n".encode()
    content_obj += text_operations
    content_obj += b"endstream\nendobj\n"
    objects.append(content_obj)
    
    # Build the PDF
    pdf_content += b"".join(objects)
    
    # Cross-reference table
    xref = b"xref\n0 6\n"
    xref += b"0000000000 65535 f \n"
    
    # Calculate byte offsets for each object
    offset = len(b"%PDF-1.4\n")
    for i in range(5):
        xref += f"{offset:010d} 00000 n \n".encode()
        offset += len(objects[i])
    
    pdf_content += xref
    
    # Trailer
    trailer = b"trailer\n<< /Size 6 /Root 1 0 R >>\n"
    pdf_content += trailer
    
    # Start xref
    pdf_content += b"startxref\n"
    pdf_content += str(len(b"%PDF-1.4\n") + sum(len(obj) for obj in objects)).encode()
    pdf_content += b"\n%%EOF"
    
    # Write to file
    with open(filename, 'wb') as f:
        f.write(pdf_content)
    
    print(f"Created {filename} with {len(lines)} lines of text")

if __name__ == "__main__":
    # Create test content
    test_text = """Naive RAG System Documentation

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

This document contains sufficient text to test the chunking algorithm and ensure proper processing through all pipeline stages."""
    
    create_simple_pdf("test_with_content.pdf", test_text)