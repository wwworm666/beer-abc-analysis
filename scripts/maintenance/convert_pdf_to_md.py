#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import pdfplumber
from pathlib import Path

pdf_dir = r"c:\Users\wwwor\OneDrive\Документы\GitHub\beer-abc-analysis\Документация"
md_dir = r"c:\Users\wwwor\OneDrive\Документы\GitHub\beer-abc-analysis\Документация_MD"

# Create markdown directory if it doesn't exist
Path(md_dir).mkdir(parents=True, exist_ok=True)

# Get all PDF files
pdf_files = sorted([f for f in os.listdir(pdf_dir) if f.endswith('.pdf')])

print("=" * 80)
print("PDF to Markdown Conversion")
print("=" * 80)
print(f"\nFound {len(pdf_files)} PDF files")
print(f"Output directory: {md_dir}\n")

for pdf_file in pdf_files:
    pdf_path = os.path.join(pdf_dir, pdf_file)
    md_filename = pdf_file.replace('.pdf', '.md')
    md_path = os.path.join(md_dir, md_filename)

    print(f"[PROCESSING] {pdf_file}")

    try:
        with pdfplumber.open(pdf_path) as pdf:
            # Extract title from filename (make it look nice)
            title = pdf_file.replace('.pdf', '').replace('-', ' ').title()

            # Get number of pages
            num_pages = len(pdf.pages)

            # Extract text from all pages
            full_text = []
            full_text.append(f"# {title}\n")
            full_text.append(f"*Generated from PDF: {pdf_file}*\n")
            full_text.append(f"*Total pages: {num_pages}*\n")
            full_text.append("---\n")

            for page_num, page in enumerate(pdf.pages, 1):
                full_text.append(f"\n## Page {page_num}\n")

                text = page.extract_text()
                if text:
                    full_text.append(text)
                else:
                    full_text.append("(No text extracted from this page)\n")

                # Try to extract tables
                tables = page.extract_tables()
                if tables:
                    for table in tables:
                        full_text.append("\n\n### Table:\n")
                        # Simple table rendering
                        if table:
                            # Header
                            header = table[0]
                            full_text.append("| " + " | ".join(str(h) if h else "" for h in header) + " |\n")
                            full_text.append("|" + "|".join(["---"] * len(header)) + "|\n")

                            # Rows
                            for row in table[1:]:
                                full_text.append("| " + " | ".join(str(cell) if cell else "" for cell in row) + " |\n")

                full_text.append(f"\n---\n")

            # Write to markdown file
            with open(md_path, 'w', encoding='utf-8') as md_file:
                md_file.write('\n'.join(full_text))

            print(f"   [OK] Converted to {md_filename} ({num_pages} pages)")

    except Exception as e:
        print(f"   [ERROR] {str(e)}")

print("\n" + "=" * 80)
print("Conversion Complete")
print("=" * 80)
