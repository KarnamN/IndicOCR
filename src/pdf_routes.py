"""
Flask routes for PDF manipulation tools
Add these routes to your app.py
"""

# Add these imports to app.py:
# from pdf_manipulator import PDFManipulator, parse_page_ranges, parse_page_list

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
            # Split PDF into multiple parts
            range_str = request.form.get('ranges', '')
            
            if not range_str:
                return jsonify({'error': 'No page ranges specified'}), 400
            
            # Parse ranges
            ranges = parse_page_ranges(range_str, total_pages)
            
            if not ranges:
                return jsonify({'error': 'Invalid page ranges'}), 400
            
            # Split
            output_paths = manipulator.split_pdf(
                input_path,
                config.OUTPUT_FOLDER,
                ranges,
                base_name=Path(filename).stem
            )
            
            output_files = [{'name': p.name, 'url': f'/download/{p.name}'} for p in output_paths]
            
        elif operation == 'remove':
            # Remove specific pages
            pages_str = request.form.get('pages', '')
            
            if not pages_str:
                return jsonify({'error': 'No pages specified'}), 400
            
            # Parse page list
            pages_to_remove = parse_page_list(pages_str, total_pages)
            
            if not pages_to_remove:
                return jsonify({'error': 'Invalid page numbers'}), 400
            
            # Remove pages
            output_name = f"{Path(filename).stem}_removed_pages.pdf"
            output_path = config.OUTPUT_FOLDER / output_name
            
            manipulator.remove_pages(input_path, output_path, pages_to_remove)
            
            output_files = [{'name': output_name, 'url': f'/download/{output_name}'}]
            
        elif operation == 'extract':
            # Extract specific pages
            pages_str = request.form.get('pages', '')
            
            if not pages_str:
                return jsonify({'error': 'No pages specified'}), 400
            
            # Parse page list
            pages_to_extract = parse_page_list(pages_str, total_pages)
            
            if not pages_to_extract:
                return jsonify({'error': 'Invalid page numbers'}), 400
            
            # Extract pages
            output_name = f"{Path(filename).stem}_extracted_pages.pdf"
            output_path = config.OUTPUT_FOLDER / output_name
            
            manipulator.extract_pages(input_path, output_path, pages_to_extract)
            
            output_files = [{'name': output_name, 'url': f'/download/{output_name}'}]
            
        elif operation == 'reorder':
            # Reorder pages
            order_str = request.form.get('order', '')
            
            if not order_str:
                return jsonify({'error': 'No page order specified'}), 400
            
            # Parse page order
            new_order = parse_page_list(order_str, total_pages)
            
            if not new_order:
                return jsonify({'error': 'Invalid page order'}), 400
            
            # Reorder
            output_name = f"{Path(filename).stem}_reordered.pdf"
            output_path = config.OUTPUT_FOLDER / output_name
            
            manipulator.reorder_pages(input_path, output_path, new_order)
            
            output_files = [{'name': output_name, 'url': f'/download/{output_name}'}]
            
        elif operation == 'rotate':
            # Rotate pages
            pages_str = request.form.get('pages', '')
            rotation = int(request.form.get('rotation', '90'))
            
            # Parse page list (empty = all pages)
            pages_to_rotate = parse_page_list(pages_str, total_pages) if pages_str else []
            
            # Rotate
            output_name = f"{Path(filename).stem}_rotated.pdf"
            output_path = config.OUTPUT_FOLDER / output_name
            
            manipulator.rotate_pages(input_path, output_path, pages_to_rotate, rotation)
            
            output_files = [{'name': output_name, 'url': f'/download/{output_name}'}]
            
        else:
            return jsonify({'error': f'Unknown operation: {operation}'}), 400
        
        # Cleanup uploaded file
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
        
        # Save temporarily
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = secure_filename(file.filename)
        temp_path = config.UPLOAD_FOLDER / f"temp_{timestamp}_{filename}"
        file.save(temp_path)
        
        # Get info
        manipulator = PDFManipulator()
        info = manipulator.get_pdf_info(temp_path)
        
        # Cleanup
        temp_path.unlink()
        
        return jsonify({
            'success': True,
            'info': info
        })
        
    except Exception as e:
        logger.error(f"PDF info error: {str(e)}")
        return jsonify({'error': str(e)}), 500
