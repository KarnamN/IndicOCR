import sys
from pathlib import Path

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

import os
from file_duplicate_finder.tree_builder import build_folder_tree
from file_duplicate_finder.content_generator import save_content_html

# We will use the existing test_telugu_folder
test_dir = Path("test_telugu_folder")
if not test_dir.exists():
    print("Please run demo_folder_scanner.py first to create the test folder!")
    sys.exit(1)

print(f"Building folder tree for: {test_dir.resolve()}")
tree = build_folder_tree(str(test_dir))

print("Generating content.html...")
output_path = save_content_html(
    tree=tree,
    root_path=str(test_dir),
    duplicate_count=0,
    original_count=0,
    total_files=6,
    wasted_str="0 B",
    scan_done=False
)

print(f"✓ Generated content.html successfully at: {output_path}")

# Verify file contents
if os.path.exists(output_path):
    with open(output_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Check that Telugu and English transliterations exist in the html
    print("Checking HTML file for expected transliterations:")
    # "తెలుగు_పుస్తకాలు" should have its english transliteration: "telugu_pustakalu"
    # "English_Books" should have its telugu transliteration: "ఎంగ్లిష్_బూక్స్" or similar
    
    # File checks (should be found)
    file_checks = {
        "భారతదేశం_చరిత్ర": "భారతదేశం_చరిత్ర file name",
        "bharatadesham_charitra": "భారతదేశం_చరిత్ర transliteration (file)",
        "సమ్ప్ల్_బూక్": "sample_book transliteration (file)",
    }
    
    for key, desc in file_checks.items():
        found = key in content.lower() or key in content
        status = "✓ Found" if found else "✗ Missing"
        print(f"  {status}: {desc} ({key})")

    # Folder checks (should NOT be found)
    folder_checks = {
        "telugu_pustakalu": "తెలుగు_పుస్తకాలు transliteration (folder)",
        "ఎన్గ్లిశ్_బూక్స్": "English_Books transliteration (folder)",
    }
    
    print("\nChecking that folder names are NOT transliterated:")
    for key, desc in folder_checks.items():
        found = key in content.lower() or key in content
        status = "✓ Not Found (Correct)" if not found else "✗ Found (Incorrect)"
        print(f"  {status}: {desc} ({key})")
else:
    print("✗ HTML file was not created!")
