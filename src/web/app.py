"""
Flask web application for PDF to EPUB conversion
"""
import os
import uuid
import logging
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file, Response
from flask_cors import CORS
from werkzeug.utils import secure_filename
import threading
import json

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.converter import PDFToEPUBConverter
from src.logging_config import get_logger
from src.config import (
    UPLOAD_FOLDER,
    OUTPUT_FOLDER,
    MAX_CONTENT_LENGTH,
    allowed_file,
    SECRET_KEY
)
logger = get_logger(__name__)

# Create Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = SECRET_KEY
app.config['UPLOAD_FOLDER'] = str(UPLOAD_FOLDER)
app.config['OUTPUT_FOLDER'] = str(OUTPUT_FOLDER)
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH

CORS(app)

# Store conversion tasks
conversion_tasks = {}


class ConversionTask:
    """Track conversion task progress"""
    
    def __init__(self, task_id: str, pdf_path: str, output_path: str):
        self.task_id = task_id
        self.pdf_path = pdf_path
        self.output_path = output_path
        self.status = 'pending'  # pending, processing, complete, error
        self.progress = {
            'stage': '',
            'current': 0,
            'total': 0,
            'percentage': 0
        }
        self.error = None
        self.result_file = None
    
    def update_progress(self, stage: str, current: int, total: int):
        """Update task progress"""
        self.progress = {
            'stage': stage,
            'current': current,
            'total': total,
            'percentage': (current / total * 100) if total > 0 else 0
        }
        logger.debug(f"Task {self.task_id}: {stage} {current}/{total}")
    
    def to_dict(self):
        """Convert to dictionary for JSON response"""
        return {
            'task_id': self.task_id,
            'status': self.status,
            'progress': self.progress,
            'error': self.error,
            'result_file': self.result_file
        }


def run_conversion(task: ConversionTask, options: dict):
    """Run conversion in background thread"""
    try:
        task.status = 'processing'
        logger.info(f"Starting conversion for task {task.task_id}")
        
        # Create converter
        converter = PDFToEPUBConverter(options)
        
        # Convert with progress callback
        result = converter.convert(
            pdf_path=task.pdf_path,
            output_path=task.output_path,
            title=options.get('title'),
            author=options.get('author', 'Unknown'),
            progress_callback=task.update_progress
        )
        
        task.status = 'complete'
        task.result_file = Path(result).name
        logger.info(f"Conversion complete for task {task.task_id}")
        
    except Exception as e:
        task.status = 'error'
        task.error = str(e)
        logger.error(f"Conversion failed for task {task.task_id}: {e}", exc_info=True)


@app.route('/')
def index():
    """Main page"""
    return render_template('index.html')


@app.route('/upload', methods=['POST'])
def upload_file():
    """Handle file upload"""
    try:
        # Check if file is present
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        if not allowed_file(file.filename):
            return jsonify({'error': 'Invalid file type. Only PDF files are allowed.'}), 400
        
        # Save uploaded file
        filename = secure_filename(file.filename)
        task_id = str(uuid.uuid4())
        upload_path = Path(app.config['UPLOAD_FOLDER']) / f"{task_id}_{filename}"
        file.save(str(upload_path))
        
        logger.info(f"File uploaded: {filename} (task: {task_id})")
        
        # Get metadata from form
        title = request.form.get('title') or Path(filename).stem
        author = request.form.get('author', 'Unknown')
        language = request.form.get('language', 'te')
        pages_per_chapter = int(request.form.get('pages_per_chapter', 10))
        
        # Prepare output path
        output_filename = f"{Path(filename).stem}.epub"
        output_path = Path(app.config['OUTPUT_FOLDER']) / f"{task_id}_{output_filename}"
        
        # Create conversion task
        task = ConversionTask(task_id, str(upload_path), str(output_path))
        conversion_tasks[task_id] = task
        
        # Start conversion in background
        options = {
            'title': title,
            'author': author,
            'language': language,
            'pages_per_chapter': pages_per_chapter
        }
        
        thread = threading.Thread(target=run_conversion, args=(task, options))
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'task_id': task_id,
            'filename': filename,
            'message': 'Upload successful. Conversion started.'
        })
        
    except Exception as e:
        logger.error(f"Upload failed: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/status/<task_id>')
def get_status(task_id):
    """Get conversion status"""
    task = conversion_tasks.get(task_id)
    
    if not task:
        return jsonify({'error': 'Task not found'}), 404
    
    return jsonify(task.to_dict())


@app.route('/progress/<task_id>')
def progress_stream(task_id):
    """Server-Sent Events stream for progress updates"""
    task = conversion_tasks.get(task_id)
    
    if not task:
        return jsonify({'error': 'Task not found'}), 404
    
    def generate():
        """Generate SSE events"""
        last_progress = None
        
        while True:
            current_progress = task.to_dict()
            
            # Send update if progress changed
            if current_progress != last_progress:
                yield f"data: {json.dumps(current_progress)}\n\n"
                last_progress = current_progress
            
            # Stop if task is complete or errored
            if task.status in ['complete', 'error']:
                break
            
            # Wait before next check
            import time
            time.sleep(0.5)
    
    return Response(generate(), mimetype='text/event-stream')


@app.route('/download/<task_id>')
def download_file(task_id):
    """Download generated EPUB file"""
    task = conversion_tasks.get(task_id)
    
    if not task:
        return jsonify({'error': 'Task not found'}), 404
    
    if task.status != 'complete':
        return jsonify({'error': 'Conversion not complete'}), 400
    
    file_path = Path(task.output_path)
    
    if not file_path.exists():
        return jsonify({'error': 'File not found'}), 404
    
    return send_file(
        str(file_path),
        as_attachment=True,
        download_name=task.result_file
    )


@app.route('/cleanup/<task_id>', methods=['POST'])
def cleanup_task(task_id):
    """Clean up task files"""
    task = conversion_tasks.get(task_id)
    
    if not task:
        return jsonify({'error': 'Task not found'}), 404
    
    try:
        # Delete uploaded PDF
        if Path(task.pdf_path).exists():
            Path(task.pdf_path).unlink()
        
        # Delete generated EPUB
        if Path(task.output_path).exists():
            Path(task.output_path).unlink()
        
        # Remove from tasks
        del conversion_tasks[task_id]
        
        logger.info(f"Cleaned up task {task_id}")
        return jsonify({'message': 'Cleanup successful'})
        
    except Exception as e:
        logger.error(f"Cleanup failed: {e}")
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    # Ensure directories exist
    Path(app.config['UPLOAD_FOLDER']).mkdir(exist_ok=True)
    Path(app.config['OUTPUT_FOLDER']).mkdir(exist_ok=True)
    
    # Run app
    app.run(debug=True, host='0.0.0.0', port=5001, threaded=True)
