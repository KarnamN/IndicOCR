"""
Demo script to test folder scanner with Telugu filenames
"""
import sys
from pathlib import Path

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

import os
import subprocess

# Create a test directory structure with Telugu names
test_dir = Path("test_telugu_folder")
test_dir.mkdir(exist_ok=True)

# Create some test files and folders with Telugu names
test_structure = {
    "తెలుగు_పుస్తకాలు": {  # Telugu books folder
        "భారతదేశం_చరిత్ర.txt": "History of India content",
        "తెలుగు_వ్యాకరణం.pdf": "Telugu grammar content",
    },
    "English_Books": {
        "sample_book.txt": "Sample English book",
        "హైదరాబాద్_గైడ్.txt": "Hyderabad guide content",
    },
    "మిశ్రమ_Mixed_Folder": {
        "readme.txt": "Readme file",
        "విజయవాడ.txt": "Vijayawada content",
    }
}

print("Creating test folder structure with Telugu names...")
print("=" * 60)

for folder_name, files in test_structure.items():
    folder_path = test_dir / folder_name
    folder_path.mkdir(exist_ok=True)
    print(f"📁 Created: {folder_name}")
    
    for file_name, content in files.items():
        file_path = folder_path / file_name
        file_path.write_text(content, encoding='utf-8')
        print(f"   📄 Created: {file_name}")

print("\n" + "=" * 60)
print("✓ Test structure created successfully!")
print("=" * 60)
print()

# Run the folder scanner
print("Running folder scanner...")
print()

# Get the src directory path
src_dir = Path(__file__).parent.parent / 'src'
scanner_path = src_dir / 'folder_scanner.py'

result = subprocess.run(
    ["python3", str(scanner_path), str(test_dir), "-o", "telugu_folder_report.txt", "-j", "telugu_folder_report.json", "-p"],
    capture_output=False,
    text=True
)

print()
print("=" * 60)
print("✓ Demo completed!")
print("=" * 60)
print()
print("Generated files:")
print("  📄 telugu_folder_report.txt  - Text report")
print("  📄 telugu_folder_report.json - JSON report")
print()
print("Test folder created at:", test_dir.absolute())
