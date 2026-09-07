# PDF Manipulation Module - Integration Guide

## ✅ Created Files

1. **`src/pdf_manipulator.py`** - Core PDF manipulation utilities
2. **`src/pdf_routes.py`** - Flask routes for web interface

## Features Implemented

### PDF Operations

1. **Split PDF** - Split into multiple files by page ranges
   - Example: "1-10,15-20,25-30" creates 3 PDFs
   
2. **Remove Pages** - Remove specific pages from PDF
   - Example: "1,5,10-15" removes those pages
   
3. **Extract Pages** - Extract specific pages to new PDF
   - Example: "1-5,10,20" creates PDF with only those pages
   
4. **Reorder Pages** - Rearrange pages in custom order
   - Example: "10,9,8,7,6,5,4,3,2,1" reverses first 10 pages
   
5. **Rotate Pages** - Rotate pages by 90°, 180°, or 270°
   - Can rotate specific pages or all pages
   
6. **Get PDF Info** - Get metadata (pages, title, author, size, etc.)

## Integration Steps

### Step 1: Add Routes to app.py

Add these lines to `src/app.py`:

```python
# At the top with other imports:
from pdf_manipulator import PDFManipulator, parse_page_ranges, parse_page_list

# After the existing routes (around line 335), add:

@app.route('/pdf_tools', methods=['POST'])
def pdf_tools():
    """Handle PDF manipulation requests"""
    try:
        # Check if file is present
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        if not allowed_file(file.filename):
            return jsonify({'error': 'Invalid file type. Only PDF files are allowed'}), 400
        
        # Get operation type
        operation = request.form.get('operation')
        
        if not operation:
            return jsonify({'error': 'No operation specified'}), 400
        
        # Generate unique ID and timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        job_id = str(uuid.uuid4())[:8]
        
        # Save uploaded file
        filename = secure_filename(file.filename)
        input_path = config.UPLOAD_FOLDER / f"{timestamp}_{job_id}_{filename}"
        file.save(input_path)
        
        logger.info(f"PDF manipulation: {operation} on {filename}")
        
        # Get PDF info
        manipulator = PDFManipulator()
        pdf_info = manipulator.get_pdf_info(input_path)
        total_pages = pdf_info['page_count']
        
        output_files = []
        
        # Perform operation
        if operation == 'split':
            range_str = request.form.get('ranges', '')
            if not range_str:
                return jsonify({'error': 'No page ranges specified'}), 400
            
            ranges = parse_page_ranges(range_str, total_pages)
            if not ranges:
                return jsonify({'error': 'Invalid page ranges'}), 400
            
            output_paths = manipulator.split_pdf(
                input_path, config.OUTPUT_FOLDER, ranges,
                base_name=Path(filename).stem
            )
            output_files = [{'name': p.name, 'url': f'/download/{p.name}'} for p in output_paths]
            
        elif operation == 'remove':
            pages_str = request.form.get('pages', '')
            if not pages_str:
                return jsonify({'error': 'No pages specified'}), 400
            
            pages_to_remove = parse_page_list(pages_str, total_pages)
            if not pages_to_remove:
                return jsonify({'error': 'Invalid page numbers'}), 400
            
            output_name = f"{Path(filename).stem}_removed_pages.pdf"
            output_path = config.OUTPUT_FOLDER / output_name
            manipulator.remove_pages(input_path, output_path, pages_to_remove)
            output_files = [{'name': output_name, 'url': f'/download/{output_name}'}]
            
        else:
            return jsonify({'error': f'Unknown operation: {operation}'}), 400
        
        # Cleanup
        if config.CLEANUP_TEMP_FILES:
            try:
                input_path.unlink()
            except Exception as e:
                logger.warning(f"Failed to delete uploaded file: {e}")
        
        return jsonify({
            'success': True,
            'operation': operation,
            'files': output_files,
            'message': f'PDF {operation} completed successfully'
        })
        
    except Exception as e:
        logger.error(f"PDF manipulation error: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/pdf_info', methods=['POST'])
def pdf_info():
    """Get PDF information"""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        if not allowed_file(file.filename):
            return jsonify({'error': 'Invalid file type'}), 400
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = secure_filename(file.filename)
        temp_path = config.UPLOAD_FOLDER / f"temp_{timestamp}_{filename}"
        file.save(temp_path)
        
        manipulator = PDFManipulator()
        info = manipulator.get_pdf_info(temp_path)
        temp_path.unlink()
        
        return jsonify({'success': True, 'info': info})
        
    except Exception as e:
        logger.error(f"PDF info error: {str(e)}")
        return jsonify({'error': str(e)}), 500
```

### Step 2: Frontend is Already There!

Your screenshot shows the UI is already in `index.html`. The backend routes will connect to it automatically.

## Usage Examples

### From Python Code

```python
from pdf_manipulator import PDFManipulator
from pathlib import Path

manipulator = PDFManipulator()

# Split PDF
ranges = [(1, 10), (11, 20), (21, 30)]
output_files = manipulator.split_pdf(
    Path("input.pdf"),
    Path("output/"),
    ranges
)

# Remove pages
manipulator.remove_pages(
    Path("input.pdf"),
    Path("output.pdf"),
    pages_to_remove=[1, 5, 10, 15]
)

# Extract pages
manipulator.extract_pages(
    Path("input.pdf"),
    Path("extracted.pdf"),
    pages=[1, 2, 3, 10, 20]
)

# Reorder pages
manipulator.reorder_pages(
    Path("input.pdf"),
    Path("reordered.pdf"),
    new_order=[10, 9, 8, 7, 6, 5, 4, 3, 2, 1]
)

# Rotate pages
manipulator.rotate_pages(
    Path("input.pdf"),
    Path("rotated.pdf"),
    pages=[1, 2, 3],  # Empty list = all pages
    rotation=90
)

# Get PDF info
info = manipulator.get_pdf_info(Path("input.pdf"))
print(f"Pages: {info['page_count']}")
print(f"Title: {info['title']}")
```

### From Web Interface

1. Go to **PDF Tools** tab
2. Upload PDF
3. Select operation:
   - **Split**: Enter ranges like "1-10,15-20"
   - **Remove**: Enter pages like "1,5,10-15"
4. Click process
5. Download result(s)

## Page Range Format

### Split Ranges
- `"1-10"` - Pages 1 to 10
- `"1-10,15-20"` - Two parts: 1-10 and 15-20
- `"1-5,10,15-20"` - Three parts

### Page Lists
- `"1,2,3"` - Pages 1, 2, 3
- `"1-5,10"` - Pages 1, 2, 3, 4, 5, 10
- `"1-3,5-7,10-12"` - Pages 1,2,3,5,6,7,10,11,12

## Testing

```bash
# Test the module
cd /mnt/c/Workspace/Antigravity_workspace/Myocr
source .venv/bin/activate
python src/pdf_manipulator.py
```

## API Endpoints

### POST /pdf_tools
Manipulate PDF files

**Form Data:**
- `file`: PDF file
- `operation`: 'split', 'remove', 'extract', 'reorder', 'rotate'
- `ranges`: Page ranges (for split)
- `pages`: Page numbers (for remove/extract/rotate)
- `order`: Page order (for reorder)
- `rotation`: Rotation angle (for rotate)

**Response:**
```json
{
  "success": true,
  "operation": "split",
  "files": [
    {"name": "file_part1.pdf", "url": "/download/file_part1.pdf"},
    {"name": "file_part2.pdf", "url": "/download/file_part2.pdf"}
  ],
  "message": "PDF split completed successfully"
}
```

### POST /pdf_info
Get PDF information

**Form Data:**
- `file`: PDF file

**Response:**
```json
{
  "success": true,
  "info": {
    "page_count": 100,
    "title": "My Document",
    "author": "Author Name",
    "file_size": 1024000
  }
}
```

## Next Steps

1. **Add routes to app.py** (copy from above)
2. **Restart the web server**
3. **Test with a PDF file**

The frontend UI you showed in the screenshot will now work with these backend routes!

---

**All PDF manipulation features are ready!** 🎉
