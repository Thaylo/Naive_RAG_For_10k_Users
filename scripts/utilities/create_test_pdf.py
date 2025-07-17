from pypdf import PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
import io

# Create a PDF with actual text content
def create_test_pdf(filename):
    # Create a PDF in memory
    packet = io.BytesIO()
    can = canvas.Canvas(packet, pagesize=letter)
    
    # Add text to the PDF
    text = """
    This is a test PDF document for the Naive RAG system.
    
    The system is designed to handle 10,000 concurrent users and process documents efficiently.
    It uses a microservices architecture with the following components:
    
    1. Upload Service - Handles file uploads
    2. Chunking Service - Splits documents into manageable chunks
    3. Embedding Service - Creates vector embeddings
    4. Vectorial Database - Stores and searches embeddings
    5. RAG Query Service - Handles user queries
    
    Each service is designed to scale independently and handle high loads.
    The system uses mock LLMs for testing purposes, making it easy to validate
    the pipeline without requiring actual AI models.
    
    This document contains enough text to be properly chunked and processed
    by the entire pipeline, ensuring that all services work correctly together.
    """
    
    # Write the text
    textobject = can.beginText(50, 750)
    for line in text.strip().split('\n'):
        textobject.textLine(line.strip())
    can.drawText(textobject)
    
    # Save the canvas
    can.save()
    
    # Move to the beginning of the BytesIO buffer
    packet.seek(0)
    
    # Write to file
    with open(filename, 'wb') as f:
        f.write(packet.getvalue())

if __name__ == "__main__":
    create_test_pdf("test_with_content.pdf")
    print("Created test_with_content.pdf")