#!/usr/bin/env python3
from pypdf import PdfReader

# Test if we can extract text from the CV PDF
pdf_path = "Data/CV Thaylo de Freitas en-us.pdf"

try:
    reader = PdfReader(pdf_path)
    print(f"Number of pages: {len(reader.pages)}")
    
    full_text = ""
    for i, page in enumerate(reader.pages):
        page_text = page.extract_text()
        print(f"\nPage {i+1} - Text length: {len(page_text)} characters")
        if page_text:
            print(f"First 200 chars: {page_text[:200]}")
        else:
            print("No text extracted from this page")
        full_text += page_text + "\n"
    
    print(f"\nTotal text extracted: {len(full_text)} characters")
    
    if len(full_text.strip()) == 0:
        print("WARNING: No text could be extracted from this PDF!")
        print("The PDF might be image-based or have text extraction disabled.")
    
except Exception as e:
    print(f"Error reading PDF: {e}")