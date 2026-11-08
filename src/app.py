import os
import shutil
# Force disable MKLDNN globally to prevent PIR oneDNN crashes on CPU
os.environ["FLAGS_use_mkldnn"] = "0"
os.environ["FLAGS_mkldnn_cache_capacity"] = "0"
os.environ["PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT"] = "0"
os.environ["FLAGS_enable_pir_api"] = "0"
os.environ["FLAGS_enable_pir_in_executor"] = "0"

# Pillow's decompression-bomb guard (default limit ~179M pixels) is meant for
# untrusted third-party images; this app renders the user's own PDF pages, and an
# oversized scan (e.g. a large physical page or a double-page spread) legitimately
# exceeds it -- hit in practice while splitting a real book. Raise it process-wide,
# before anything else imports PIL, rather than patching every Image.open() call site.
from PIL import Image as _PILImage
_PILImage.MAX_IMAGE_PIXELS = None

"""
Flask Web Application for PDF to EPUB Converter
"""
from flask import Flask, render_template, request, send_file, jsonify, flash, redirect, url_for
from flask_socketio import SocketIO, emit
from werkzeug.utils import secure_filename
import os
from pathlib import Path
import logging
import uuid
from datetime import datetime
from threading import Thread
import platform

# ── OCR Engine Mode Toggle ───────────────────────────────────────────────────
# On Windows CPU, PaddleOCR is extremely slow, so we default to Tesseract-primary.
# On Linux/WSL, we enable PP-OCRv5 primary with automatic Tesseract fallback.
USE_PADDLE_V5 = platform.system() != 'Windows'

import sys
if USE_PADDLE_V5:
    import config_v5 as config   # PP-OCRv5 primary + Tesseract fallback
    sys.modules['config'] = config
else:
    import config                 # Tesseract primary + Gemini rescue (original)
# OptimizedPDFToEPUBConverter is imported lazily inside convert_pdf_background()
# to avoid loading cv2/numpy/AdaptiveOCRFactory at Flask startup time.
from mobi_converter import MOBIConverter
from filename_utils import generate_output_filenames
import fitz  # For checking PDF page count
from pdf_manipulator import PDFManipulator, parse_page_ranges, parse_page_list

# ── Paddle model pre-warm (background, non-blocking) ────────────────────────
# Start loading the heavy PP-OCRv5 models immediately at server startup in a
# daemon thread so they are in memory by the time the first user uploads a PDF.
# Without this, the 28-second model load happens inside the first worker thread
# and blocks that conversion job from starting.
if USE_PADDLE_V5 and getattr(config, 'ENABLE_PADDLE_OCR', False):
    def _prewarm_paddle_models():
        try:
            from paddle_v5_processor import _get_rec_engine, _get_det_engine
            import logging as _log
            _pw = _log.getLogger('paddle_prewarm')
            _pw.info("⏳ Pre-warming Paddle models in background…")
            _t0 = __import__('time').time()
            _get_rec_engine(config)
            _get_det_engine(config)
            _pw.info(f"✅ Paddle models ready in {__import__('time').time() - _t0:.1f}s")
        except Exception as _e:
            import logging as _log
            _log.getLogger('paddle_prewarm').warning(f"Pre-warm failed (non-fatal): {_e}")

    _prewarm_thread = Thread(target=_prewarm_paddle_models, daemon=True, name="paddle-prewarm")
    _prewarm_thread.start()


from logging_config import get_logger
logger = get_logger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = config.SECRET_KEY
app.config['UPLOAD_FOLDER'] = config.UPLOAD_FOLDER
app.config['OUTPUT_FOLDER'] = config.OUTPUT_FOLDER
app.config['MAX_CONTENT_LENGTH'] = config.MAX_FILE_SIZE
# socketio.run(debug=...) below does NOT set app.debug the way plain
# app.run(debug=True) does, so Jinja's template auto-reload (which keys off
# app.debug) never activates on its own -- every template edit needs a full
# server restart otherwise, silently serving stale HTML/CSS/JS with no error.
# Set explicitly so template changes take effect on the next request.
app.config['TEMPLATES_AUTO_RELOAD'] = config.DEBUG

# Initialize SocketIO with threading mode and increased timeouts
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading', ping_timeout=120, ping_interval=25)

# Ensure directories exist
config.UPLOAD_FOLDER.mkdir(exist_ok=True)
config.OUTPUT_FOLDER.mkdir(exist_ok=True)

# Job tracking
conversion_jobs = {}
audit_jobs = {} 
ALLOWED_EXTENSIONS = {'pdf', 'epub', 'mobi'}


def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in config.ALLOWED_EXTENSIONS


def progress_callback(job_id, stage, current, total):
    """Progress callback for conversion"""
    percentage = int((current / total) * 100) if total > 0 else 0
    
    # Update job status
    if job_id in conversion_jobs:
        conversion_jobs[job_id]['progress'] = percentage
        conversion_jobs[job_id]['stage'] = stage
    
    # Emit progress via WebSocket
    socketio.emit('progress', {
        'job_id': job_id,
        'stage': stage,
        'percentage': percentage
    }, room=job_id)
    
    # Check if stage message contains page analysis data (JSON-encoded)
    if isinstance(stage, str) and stage.startswith('{"page_analysis"'):
        import json
        try:
            data = json.loads(stage)
            socketio.emit('page_analysis', {
                'job_id': job_id,
                **data['page_analysis']
            }, room=job_id)
        except (json.JSONDecodeError, KeyError):
            pass
    
    logger.info(f"Job {job_id}: {stage} - {percentage}%")


def emit_page_analysis(job_id, page_data):
    """Emit per-page complexity analysis data via WebSocket"""
    socketio.emit('page_analysis', {
        'job_id': job_id,
        **page_data
    }, room=job_id)


def convert_pdf_background(job_id, input_path, output_path, mobi_path, params):
    """Background task for PDF conversion"""
    # Lazy import: keeps startup fast — cv2/numpy/OCR chain only loads when a job starts
    from pdf_to_epub_converter_optimized_v2 import OptimizedPDFToEPUBConverter
    try:
        conversion_jobs[job_id]['status'] = 'processing'
        
        # Check PDF page count to determine which converter to use
        try:
            doc = fitz.open(input_path)
            page_count = len(doc)
            doc.close()
            logger.info(f"PDF has {page_count} pages")
        except Exception as e:
            logger.warning(f"Could not determine page count: {e}")
            page_count = 0
        
        # Always use v2 optimized converter (faster and better)
        logger.info(f"Using OPTIMIZED V2 converter for {page_count} pages")
        
        converter = OptimizedPDFToEPUBConverter(
            language=params.get('language'),
            dpi=params.get('dpi', config.OCR_DPI),
            detect_tables=params.get('detect_tables', True),
            preserve_images=params.get('preserve_images', True),
            skip_empty_cells=True,
            max_workers=params.get('max_workers', config.MAX_WORKERS),
            split_double_pages=params.get('split_pages', True),
            enable_parallel=params.get('enable_parallel', True),
            batch_size=params.get('batch_size'),
            skip_ocr_pages=params.get('skip_ocr_pages', []),
            only_pages=params.get('only_pages', []),
            session_id=job_id[:8],
            enable_rescue=params.get('enable_rescue', True),
            progress_callback=lambda stage, current, total: progress_callback(job_id, stage, current, total)
        )
        
        # Store converter reference for cancellation support
        conversion_jobs[job_id]['converter'] = converter

        # Wire health alert callback → emits WebSocket events to the UI
        def _health_alert_cb(alert_type, data):
            payload = {'job_id': job_id, 'alert_type': alert_type, **data}
            socketio.emit('health_alert', payload, room=job_id)
            logger.warning(f"🚨 Health Alert [{alert_type}] emitted to UI for job {job_id}")
        converter.alert_callback = _health_alert_cb
        
        # Convert using streaming method
        success = converter.convert_streaming(
            input_path,
            output_path,
            title=params.get('title'),
            author=params.get('author'),
            max_pages=None,
            skip_first_pages=params.get('skip_cover_pages', 2),
            only_pages=params.get('only_pages', [])
        )

        # Persist the uploaded PDF into the results folder as source.pdf so the
        # correction dashboard's per-page image (/api/correction/page/<job_id>/<n>)
        # has something to re-render from for regular pages, which don't keep
        # their own image in the .jbl (see that route's docstring). Without this,
        # a freshly-converted job (as opposed to one reopened via
        # /api/correction/resume with a re-uploaded PDF) never gets a source.pdf
        # and every non-cover page shows "No image available". Best-effort: a
        # missing preview image must never fail the conversion itself.
        results_dir = getattr(converter, 'temp_results_dir', None)
        if results_dir:
            try:
                shutil.copyfile(input_path, Path(results_dir) / "source.pdf")
            except Exception as e:
                logger.warning(f"Could not save source.pdf into {results_dir}: {e}")

        # Collect detailed usage report
        usage_report = {
            'paddle_pages':       getattr(converter, 'paddle_pages', 0),
            'tesseract_pages':    getattr(converter, 'tesseract_pages', 0),
            'image_only_pages':   getattr(converter, 'image_only_pages', 0),
            'gemini_direct_pages': converter.gemini_stats.get('direct', 0),
            'gemini_rescue_pages': converter.gemini_stats.get('rescue', 0),
            'total_pages': page_count
        }
        
        if not success:
            # Distinguish between cancellation and actual failure
            if conversion_jobs[job_id].get('status') == 'cancelling':
                conversion_jobs[job_id]['status'] = 'cancelled'
                logger.warning(f"🛑 Job {job_id} cancelled by user")
                socketio.emit('complete', {
                    'job_id': job_id,
                    'success': False,
                    'cancelled': True,
                    'error': 'Conversion was stopped by user. No files were created.'
                }, room=job_id)
            else:
                conversion_jobs[job_id]['status'] = 'failed'
                conversion_jobs[job_id]['error'] = 'EPUB conversion failed'
                socketio.emit('complete', {
                    'job_id': job_id,
                    'success': False,
                    'error': 'EPUB conversion failed'
                }, room=job_id)
            return

        # Dictionary-correction review gate (see docs/TELUGU_SPELL_CORRECTION_TODO.md):
        # convert_streaming() defers the EPUB/MOBI build and exposes which pages need
        # a human look via this attribute, same getattr-after-return convention as
        # paddle_pages/tesseract_pages above. The converter reference is deliberately
        # kept (not deleted in `finally`) so /api/correction/rebuild/<job_id> can use
        # it once review is done.
        pages_pending_review = getattr(converter, 'pages_pending_review', [])
        if pages_pending_review:
            conversion_jobs[job_id]['status'] = 'pending_review'
            conversion_jobs[job_id]['pages_pending_review'] = pages_pending_review
            logger.info(
                f"⏸️ Job {job_id}: {len(pages_pending_review)} page(s) need manual "
                f"review before the book can be built"
            )
            conversion_jobs[job_id]['correction_url'] = f'/correction/{job_id}'
            socketio.emit('pending_review', {
                'job_id': job_id,
                'pages_pending_review': pages_pending_review,
                'correction_url': f'/correction/{job_id}',
                'message': (
                    f'{len(pages_pending_review)} page(s) have automatic spell-corrections '
                    f'that need your review before the book is built.'
                )
            }, room=job_id)
            return

        # Convert to MOBI if enabled (always enabled by default)
        mobi_success = False
        if config.ENABLE_MOBI_CONVERSION:
            mobi_converter = MOBIConverter()
            if mobi_converter.is_available():
                mobi_success = mobi_converter.convert(
                    output_path,
                    mobi_path,
                    progress_callback=lambda stage, current, total: progress_callback(job_id, stage, current, total)
                )
                if mobi_success:
                    conversion_jobs[job_id]['mobi_file'] = mobi_path.name

        # Mark as complete
        conversion_jobs[job_id]['status'] = 'completed'
        conversion_jobs[job_id]['progress'] = 100
        conversion_jobs[job_id]['epub_url'] = f'/download/{output_path.name}'
        conversion_jobs[job_id]['mobi_url'] = f'/download/{mobi_path.name}' if mobi_success else None
        conversion_jobs[job_id]['usage_report'] = usage_report

        # Cleanup uploaded file
        if config.CLEANUP_TEMP_FILES:
            try:
                input_path.unlink()
            except Exception as e:
                logger.warning(f"Failed to delete uploaded file: {e}")

        # Emit completion
        socketio.emit('complete', {
            'job_id': job_id,
            'success': True,
            'epub_url': f'/download/{output_path.name}',
            'mobi_url': f'/download/{mobi_path.name}' if mobi_success else None,
            'usage_report': usage_report
        }, room=job_id)
        
    except Exception as e:
        logger.error(f"Conversion error for job {job_id}: {e}")
        conversion_jobs[job_id]['status'] = 'failed'
        conversion_jobs[job_id]['error'] = str(e)
        socketio.emit('complete', {
            'job_id': job_id,
            'success': False,
            'error': str(e)
        }, room=job_id)
    finally:
        # Clean up converter reference — EXCEPT when pending manual review, since
        # /api/correction/rebuild/<job_id> needs the same converter instance
        # (with its page_result_paths state) to build the book once review is done.
        if (job_id in conversion_jobs
                and 'converter' in conversion_jobs[job_id]
                and conversion_jobs[job_id].get('status') != 'pending_review'):
            del conversion_jobs[job_id]['converter']


@app.route('/')
def index():
    """Render main page"""
    return render_template('index.html')


@app.route('/upload', methods=['POST'])
def upload_file():
    """Handle file upload and start conversion"""
    try:
        # Check if file is present
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        if not allowed_file(file.filename):
            return jsonify({'error': 'Invalid file type. Only PDF files are allowed'}), 400
        
        # Generate unique job ID and timestamp
        job_id = str(uuid.uuid4())
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Save uploaded file
        filename = secure_filename(file.filename)
        input_path = config.UPLOAD_FOLDER / f"{timestamp}_{job_id[:8]}_{filename}"
        file.save(input_path)
        
        logger.info(f"File uploaded: {input_path}")
        
        # Generate output filenames based on input PDF filename (use original for transliteration)
        output_filename, mobi_filename = generate_output_filenames(
            file.filename, 
            timestamp, 
            job_id
        )
        output_path = config.OUTPUT_FOLDER / output_filename
        mobi_path = config.OUTPUT_FOLDER / mobi_filename
        
        # Initialize job tracking
        conversion_jobs[job_id] = {
            'status': 'queued',
            'progress': 0,
            'message': 'Queued for conversion...',
            'input_file': str(input_path),
            'output_file': output_filename,
            'mobi_file': mobi_filename,
            'timestamp': timestamp
        }
        
        # Get configuration from form
        title = request.form.get('title', 'Converted Document')
        author = request.form.get('author', 'Unknown')
        # Persist onto the job record (not just the local `params` dict passed to
        # convert_streaming) so /api/correction/rebuild/<job_id> can retrieve the
        # same title/author later — previously it always saw None here and fell
        # back to config.EPUB_METADATA's generic placeholders on every rebuild.
        conversion_jobs[job_id]['title'] = title
        conversion_jobs[job_id]['author'] = author
        language = request.form.get('language', config.DEFAULT_OCR_LANGUAGE)
        dpi = int(request.form.get('dpi', '300'))
        detect_tables = request.form.get('detect_tables', 'on') == 'on'
        preserve_images = request.form.get('preserve_images', 'on') == 'on'
        
        # Parse skip_ocr_pages (e.g., "5,7,12-15")
        skip_ocr_pages_str = request.form.get('skip_ocr_pages', '').strip()
        logger.info(f"DEBUG: skip_ocr_pages_str received from form: '{skip_ocr_pages_str}'")
        skip_ocr_pages = []
        if skip_ocr_pages_str:
            try:
                skip_ocr_pages = parse_page_list(skip_ocr_pages_str, 9999)  # Max pages
                logger.info(f"✅ Skip OCR on pages: {skip_ocr_pages}")
            except Exception as e:
                logger.warning(f"Failed to parse skip_ocr_pages: {e}")
        else:
            logger.info("ℹ️ No pages specified to skip OCR")
        
        # Parse only_pages (e.g., "5,7,12-15")
        only_pages_str = request.form.get('only_pages', '').strip()
        logger.info(f"DEBUG: only_pages_str received from form: '{only_pages_str}'")
        only_pages = []
        if only_pages_str:
            try:
                only_pages = parse_page_list(only_pages_str, 9999)
                logger.info(f"🎯 ONLY process pages: {only_pages}")
            except Exception as e:
                logger.warning(f"Failed to parse only_pages: {e}")
        else:
            logger.info("ℹ️ No specific pages requested - processing full PDF")
        
        
        logger.info(f"Form parameters: preserve_images={preserve_images}, detect_tables={detect_tables}")
        
        # New v2 parameters
        split_pages = request.form.get('split_pages', 'true').lower() == 'true'
        skip_cover_pages = int(request.form.get('skip_cover_pages', '2'))  # Default: preserve first 2 pages as covers
        max_workers = int(request.form.get('max_workers', config.MAX_WORKERS))
        enable_parallel = request.form.get('enable_parallel', 'true').lower() == 'true'
        batch_size = request.form.get('batch_size')
        if batch_size:
            batch_size = int(batch_size)
        
        # Package parameters for background task
        params = {
            'language': language,
            'dpi': dpi,
            'detect_tables': detect_tables,
            'preserve_images': preserve_images,
            'title': title,
            'author': author,
            'split_pages': split_pages,
            'skip_cover_pages': skip_cover_pages,
            'max_workers': max_workers,
            'enable_parallel': enable_parallel,
            'batch_size': batch_size,
            'skip_ocr_pages': skip_ocr_pages,
            'only_pages': only_pages,
            'enable_rescue': request.form.get('enable_rescue') == 'on'
        }
        
        logger.info(f"Params dict: preserve_images={params['preserve_images']}")
        
        # Start conversion in background thread
        thread = Thread(
            target=convert_pdf_background,
            args=(
                job_id,
                input_path, 
                output_path, 
                mobi_path,
                params
            )
        )
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'success': True,
            'job_id': job_id,
            'message': 'File uploaded successfully',
            'status': 'queued'
        })
        
    except Exception as e:
        logger.error(f"Upload error: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/job/<job_id>')
def job_status(job_id):
    """Get job status"""
    if job_id not in conversion_jobs:
        return jsonify({'error': 'Job not found'}), 404

    # 'converter' holds a live OptimizedPDFToEPUBConverter instance (kept around
    # for cancel/rework/rebuild support — see convert_pdf_background's `finally`
    # block) and isn't JSON-serializable; strip it before returning.
    job = {k: v for k, v in conversion_jobs[job_id].items() if k != 'converter'}
    return jsonify(job)


@app.route('/download/<filename>')
def download_file(filename):
    """Download converted file"""
    try:
        file_path = config.OUTPUT_FOLDER / filename
        
        if not file_path.exists():
            return jsonify({'error': 'File not found'}), 404
        
        # Determine MIME type
        if filename.endswith('.epub'):
            mimetype = 'application/epub+zip'
        elif filename.endswith('.mobi'):
            mimetype = 'application/x-mobipocket-ebook'
        else:
            mimetype = 'application/octet-stream'
        
        return send_file(
            file_path,
            as_attachment=True,
            download_name=filename,
            mimetype=mimetype
        )
    
    except Exception as e:
        logger.error(f"Download error: {e}")
        return jsonify({'error': 'Download failed'}), 500


@app.route('/status')
def status():
    """Check system status"""
    from ocr_processor import OCRProcessor
    
    processor = OCRProcessor()
    mobi_converter = MOBIConverter()
    
    status_info = {
        'telugu_support': processor.verify_telugu_support(),
        'available_languages': processor.get_available_languages(),
        'mobi_conversion': mobi_converter.is_available(),
        'upload_folder': str(config.UPLOAD_FOLDER),
        'output_folder': str(config.OUTPUT_FOLDER),
        'max_file_size': config.MAX_FILE_SIZE,
        'default_dpi': config.DEFAULT_DPI,
        'gemini_available': getattr(config, 'GEMINI_AVAILABLE', False),
        'gemini_model': getattr(config, 'GEMINI_MODEL', 'N/A'),
        'gemini_threshold': getattr(config, 'GEMINI_COMPLEXITY_THRESHOLD', 80),
        'gemini_usage': __import__('usage_tracker').UsageTracker().get_usage('gemini'),
        'langchain_enabled': getattr(config, 'ENABLE_LANGCHAIN_PIPELINE', False),
    }
    
    return jsonify(status_info)


@socketio.on('connect')
def handle_connect():
    """Handle WebSocket connection"""
    logger.info("Client connected")


@socketio.on('join')
def handle_join(data):
    """Join a job room for progress updates"""
    job_id = data.get('job_id')
    if job_id:
        from flask_socketio import join_room
        join_room(job_id)
        logger.info(f"Client joined room: {job_id}")


@app.route('/cancel/<job_id>', methods=['POST'])
def cancel_job(job_id):
    """Cancel a running conversion job"""
    if job_id not in conversion_jobs:
        return jsonify({'error': 'Job not found'}), 404
    
    job = conversion_jobs[job_id]
    
    if job.get('status') != 'processing':
        return jsonify({'error': f'Job is not running (status: {job.get("status")})'}), 400
    
    converter = job.get('converter')
    if converter is None:
        return jsonify({'error': 'Converter not available'}), 400
    
    # Signal cancellation
    converter.cancel()
    job['status'] = 'cancelling'
    
    logger.warning(f"🛑 Cancel requested for job {job_id}")
    
    # Notify frontend
    socketio.emit('cancelling', {
        'job_id': job_id,
        'message': 'Cancellation requested — stopping after current batch...'
    }, room=job_id)
    
    return jsonify({
        'success': True,
        'message': 'Cancellation requested. Conversion will stop after the current batch completes.'
    })


@app.route('/api/job/<job_id>/respond', methods=['POST'])
def job_health_respond(job_id):
    """User responds to a health alert: {'action': 'stop' | 'continue'}"""
    job = conversion_jobs.get(job_id)
    if not job:
        return jsonify({'error': 'Job not found'}), 404

    action = request.json.get('action', 'continue').lower()

    if action == 'stop':
        converter = job.get('converter')
        if converter:
            converter.cancel()
        job['status'] = 'cancelling'
        logger.warning(f"🛑 User chose STOP after health alert for job {job_id}")
        socketio.emit('cancelling', {
            'job_id': job_id,
            'message': 'Job stopped by user after PaddleOCR health alert.'
        }, room=job_id)
        return jsonify({'success': True, 'action': 'stop'})
    else:
        # User chose continue — reset alert so next threshold can re-trigger
        try:
            from paddle_v5_processor import reset_crash_stats
            reset_crash_stats()
            converter = job.get('converter')
            if converter:
                converter._alert_emitted = False
        except Exception as e:
            logger.warning(f"reset_crash_stats error: {e}")
        logger.info(f"✅ User chose CONTINUE after health alert for job {job_id}")
        return jsonify({'success': True, 'action': 'continue'})


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
            
        elif operation == 'split_wide':
            # NEW: Split double/triple/quad-page spreads into portrait pages
            from split_pdf_pages_cli import split_pdf_pages
            output_name = f"{Path(filename).stem}_split.pdf"
            output_path = config.OUTPUT_FOLDER / output_name

            # When every wide page is known to be a genuine double-page spread,
            # skip the gutter/spine confirmation check — worn gutters, crease
            # shadows or skew can make a real spread fail that check and get
            # left unsplit (see page_splitter._has_central_spine).
            assume_double_page = request.form.get('assume_double_page_spreads') == 'on'

            success = split_pdf_pages(str(input_path), str(output_path), dpi=300,
                                       require_spine_confirmation=not assume_double_page)
            
            if success:
                output_files = [{'name': output_name, 'url': f'/download/{output_name}'}]
            else:
                return jsonify({'error': 'Failed to split wide pages'}), 500
            
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

@app.route('/audit', methods=['POST'])
def audit_epub():
    """Comparison audit: PDF vs Existing EPUB."""
    if 'pdf' not in request.files or 'epub' not in request.files:
        return jsonify({'error': 'Missing PDF or EPUB file'}), 400
        
    pdf_file = request.files['pdf']
    epub_file = request.files['epub']
    
    if pdf_file.filename == '' or epub_file.filename == '':
        return jsonify({'error': 'Empty filenames'}), 400
        
    job_id = str(uuid.uuid4())[:8]
    pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{job_id}_{secure_filename(pdf_file.filename)}")
    epub_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{job_id}_{secure_filename(epub_file.filename)}")
    
    pdf_file.save(pdf_path)
    epub_file.save(epub_path)
    
    from audit_engine import AuditEngine
    auditor = AuditEngine(Path(pdf_path), Path(epub_path))
    
    # Run audit (In a production app, this would be a background task with socket updates)
    results = auditor.run_audit()
    audit_jobs[job_id] = {
        'results': results,
        'pdf_path': pdf_path,
        'epub_path': epub_path,
        'auditor': auditor
    }
    
    return render_template('audit.html', job_id=job_id, results=results)

@app.route('/resolve/<job_id>/<int:page_num>', methods=['POST'])
def resolve_audit_discrepancy(job_id, page_num):
    """Run high-accuracy Gemini OCR for a specific flagged page."""
    if job_id not in audit_jobs:
        return jsonify({'error': 'Audit job not found'}), 404
        
    auditor = audit_jobs[job_id]['auditor']
    improved_text = auditor.resolve_discrepancy(page_num)
    
    return jsonify({
        'page_num': page_num,
        'improved_text': improved_text
    })

# --- PAGE CORRECTION UI ROUTES ---

def _rehydrate_job_from_disk(job_id):
    """Reconstruct an in-memory job entry from its on-disk results folder.

    conversion_jobs is in-memory only, so every server restart wipes it —
    a bookmarked/refreshed /correction/<job_id> URL from before the restart
    would otherwise 404 even though the actual results are still on disk.
    Mirrors resume_correction()'s job-entry shape exactly, so every other
    route keyed on conversion_jobs[job_id] keeps working unchanged once this
    has run — callers only need to invoke this once, at the page entry point.
    """
    if not config.TEMP_FOLDER.exists():
        return None
    for d in config.TEMP_FOLDER.iterdir():
        if d.is_dir() and d.name.endswith(job_id) and any(d.glob("page_*.jbl")):
            from pdf_to_epub_converter_optimized_v2 import OptimizedPDFToEPUBConverter
            converter = OptimizedPDFToEPUBConverter(preserve_images=True, detect_tables=True)
            converter.temp_results_dir = d
            converter.session_id = job_id
            source_pdf_path = d / "source.pdf"
            pdf_path = source_pdf_path if source_pdf_path.exists() else None
            job = {
                'status': 'completed',
                'converter': converter,
                'title': d.name.rsplit('_', 1)[0],
                'pdf_path': str(pdf_path) if pdf_path else None,
            }
            conversion_jobs[job_id] = job
            logger.info(f"📂 Auto-rehydrated job {job_id} from disk after server restart: {d}")
            return job
    return None


@app.route('/correction/<job_id>')
def correction_ui(job_id):
    """Render the manual correction dashboard for a job."""
    if job_id not in conversion_jobs and not _rehydrate_job_from_disk(job_id):
        return render_template('error.html', message="Job not found — it may not exist, or its results folder was moved/deleted."), 404
    return render_template('correction.html', job_id=job_id)


def _resolve_results_dir(job_id):
    """
    Locate a job's results directory under config.TEMP_FOLDER.

    Prefers the live converter's already-resolved temp_results_dir when one is
    on the job record. This matters because convert_streaming()'s "SMART
    RESUME" can silently reuse an OLDER folder (matched by title prefix only)
    whose name ends in a DIFFERENT 8-char session id than the current job_id —
    the folder-name-suffix search below would then never find it, even though
    the job completed successfully and real results exist on disk (see the
    "Also sync session_id if we want to be perfect" comment in convert_streaming,
    which flags this exact gap). Falls back to the suffix search for jobs
    without a live converter reference (e.g. still queued).
    """
    job = conversion_jobs.get(job_id)
    if job:
        converter = job.get('converter')
        results_dir = getattr(converter, 'temp_results_dir', None) if converter else None
        if results_dir and Path(results_dir).is_dir():
            return Path(results_dir)

    session_id = job_id[:8]
    if config.TEMP_FOLDER.exists():
        for d in config.TEMP_FOLDER.iterdir():
            if d.is_dir() and d.name.endswith(session_id):
                return d
    return None


@app.route('/api/correction/pages/<job_id>')
def get_correction_pages(job_id):
    """Get list of pages with status for correction UI."""
    if job_id not in conversion_jobs:
        return jsonify({'error': 'Job not found'}), 404

    job = conversion_jobs[job_id]

    # Locate the results directory in TEMP_FOLDER
    results_dir = _resolve_results_dir(job_id)

    if not results_dir:
        return jsonify({'error': 'Results directory not found. Job might still be starting or failed.'}), 404
    
    pages = []
    # Identify jbl files — named page_{page_num}_{sub_idx}.jbl (sub_idx is always
    # present, even 0, per _save_page_result; a bare page_num split without it
    # would raise on int() and silently drop every page via the except below).
    for f in sorted(results_dir.glob("page_*.jbl")):
        try:
            parts = f.stem.replace("page_", "").split("_")
            page_num = int(parts[0])
            sub_idx = int(parts[1]) if len(parts) > 1 else 0

            # Check if there's a text JSON for metadata
            json_file = results_dir / f"page_{page_num}_{sub_idx}_text.json"
            status = "ok"
            needs_review = False
            correction_count = 0
            if json_file.exists():
                import json
                with open(json_file, 'r', encoding='utf-8') as jf:
                    meta = json.load(jf)
                    # Image-only/cover pages are EXPECTED to have little or no OCR
                    # text (skipped_ocr / is_cover are set deliberately when there's
                    # nothing to extract — see _export_page_text_json) — flagging
                    # them via the low-text-length check below would fill the
                    # review queue with pages that have nothing to correct.
                    is_image_only = bool(meta.get('skipped_ocr')) or bool(meta.get('is_cover'))

                    # Flag pages with low text or unusual engines (genuine text
                    # pages only — see is_image_only above)
                    if not is_image_only and meta.get('text_length', 0) < 50:
                        status = "flagged"
                    # Flag pages with dictionary corrections needing review —
                    # see docs/TELUGU_SPELL_CORRECTION_TODO.md
                    if meta.get('needs_manual_review'):
                        status = "flagged"
                        needs_review = True
                        correction_count = len(meta.get('dictionary_corrections', []))

            pages.append({
                'page_num': page_num,
                'sub_idx': sub_idx,
                'status': status,
                'needs_review': needs_review,
                'correction_count': correction_count,
                'file': f.name
            })
        except Exception:
            continue

    # `sorted(results_dir.glob(...))` above sorts by filename text, not numeric
    # page number — "page_10_0.jbl" sorts before "page_2_0.jbl" lexicographically,
    # so the list built from it isn't actually in page order. Sort numerically here.
    pages.sort(key=lambda p: (p['page_num'], p['sub_idx']))

    return jsonify({
        'job_id': job_id,
        'pages': pages,
        'pending_review_count': sum(1 for p in pages if p['needs_review']),
        'results_dir': str(results_dir)
    })

@app.route('/api/correction/page/<job_id>/<int:page_num>')
def get_page_for_correction(job_id, page_num):
    """Fetch image and text for a specific page."""
    import joblib
    import base64
    from PIL import Image
    import io

    results_dir = _resolve_results_dir(job_id)
    if not results_dir:
        return jsonify({'error': 'Results not found'}), 404

    # Filenames always include sub_idx (page_{page_num}_{sub_idx}.jbl) — the
    # correction UI's URL scheme has no sub_idx, so fall back to the common
    # sub_idx=0 case, then to any match, rather than assuming a bare page_num.jbl.
    jbl_path = results_dir / f"page_{page_num}_0.jbl"
    if not jbl_path.exists():
        matches = sorted(results_dir.glob(f"page_{page_num}_*.jbl"))
        jbl_path = matches[0] if matches else results_dir / f"page_{page_num}.jbl"
    if not jbl_path.exists():
        return jsonify({'error': f'Page {page_num} result not found'}), 404

    try:
        data = joblib.load(jbl_path)
        text = data.get('text', '')

        # Get image (if multiple, take first)
        img_b64 = ""
        if data.get('images'):
            img = data['images'][0]
            # Convert PIL to base64
            buffered = io.BytesIO()
            img.save(buffered, format="JPEG")
            img_b64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
        else:
            # Regular pages don't persist their source image in the .jbl (keeps
            # results folders small) — re-render it from source.pdf on demand so
            # the correction dashboard's side-by-side view still works. Same
            # source.pdf a resumed job's REWORK button already depends on (see
            # /api/correction/resume's docstring), so this has no new requirement.
            source_pdf = results_dir / "source.pdf"
            if source_pdf.exists():
                try:
                    doc = fitz.open(source_pdf)
                    if 0 <= page_num < len(doc):
                        page = doc.load_page(page_num)
                        # Display-only render — full OCR DPI isn't needed for a
                        # human to visually compare against the OCR text.
                        zoom = 1600 / max(page.rect.width, page.rect.height)
                        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
                        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                        buffered = io.BytesIO()
                        img.save(buffered, format="JPEG", quality=85)
                        img_b64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
                    doc.close()
                except Exception as e:
                    logger.warning(f"Could not render page {page_num} from source.pdf: {e}")

        return jsonify({
            'page_num': page_num,
            'text': text,
            'image': img_b64,
            'engine': data.get('ocr_engine', 'unknown'),
            'complexity': data.get('complexity_score', 0),
            # Dictionary spell-correction review data — see
            # docs/TELUGU_SPELL_CORRECTION_TODO.md. Empty/False when the
            # feature is off or this page had no corrections.
            'dictionary_corrections': data.get('dictionary_corrections', []),
            'needs_manual_review': data.get('needs_manual_review', False),
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/correction/save/<job_id>/<int:page_num>', methods=['POST'])
def save_corrected_page(job_id, page_num):
    """Save corrected text back to the .jbl file."""
    import joblib
    
    new_text = request.json.get('text', '')

    results_dir = _resolve_results_dir(job_id)
    if not results_dir:
        return jsonify({'error': 'Results not found'}), 404

    jbl_path = results_dir / f"page_{page_num}_0.jbl"
    if not jbl_path.exists():
        matches = sorted(results_dir.glob(f"page_{page_num}_*.jbl"))
        jbl_path = matches[0] if matches else results_dir / f"page_{page_num}.jbl"
    if not jbl_path.exists():
        return jsonify({'error': f'Page {page_num} not found'}), 404

    try:
        data = joblib.load(jbl_path)
        data['text'] = new_text
        data['manual_correction'] = True
        # Reviewer has looked at this page (whether or not they edited the
        # text) — clear the pending-review flag so it drops out of the
        # correction dashboard's flagged list.
        data['needs_manual_review'] = False
        joblib.dump(data, jbl_path)

        # Also update the debug JSON
        json_path = jbl_path.with_name(jbl_path.stem + "_text.json")
        if json_path.exists():
            import json
            with open(json_path, 'r', encoding='utf-8') as f:
                meta = json.load(f)
            meta['text'] = new_text
            meta['text_length'] = len(new_text)
            meta['manual_correction'] = True
            meta['needs_manual_review'] = False
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)

        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def _iter_page_jbl_files(results_dir):
    """Yield (page_num, sub_idx, path) for every saved page, sorted by page_num.

    Mirrors get_correction_pages()'s own filename parsing exactly (page_{page_num}_{sub_idx}.jbl).
    """
    entries = []
    for f in results_dir.glob("page_*.jbl"):
        try:
            parts = f.stem.replace("page_", "").split("_")
            page_num = int(parts[0])
            sub_idx = int(parts[1]) if len(parts) > 1 else 0
            entries.append((page_num, sub_idx, f))
        except (ValueError, IndexError):
            continue
    entries.sort(key=lambda e: (e[0], e[1]))
    return entries


@app.route('/api/correction/find_all/<job_id>', methods=['POST'])
def find_all_pages(job_id):
    """Search every saved page's text for a literal substring.

    Book-wide counterpart to the single-page editor — browsers only ever have
    one page's text loaded at a time, so this has to run server-side over
    every page_*.jbl in the results folder rather than client-side.
    """
    query = (request.get_json(silent=True) or {}).get('query', '')
    if not query:
        return jsonify({'error': 'query is required'}), 400

    results_dir = _resolve_results_dir(job_id)
    if not results_dir:
        return jsonify({'error': 'Results not found'}), 404

    import joblib
    CONTEXT = 30  # chars of surrounding text on each side of a match, for the preview
    MAX_SNIPPETS_PER_PAGE = 3

    results = []
    total_matches = 0
    for page_num, sub_idx, jbl_path in _iter_page_jbl_files(results_dir):
        try:
            data = joblib.load(jbl_path)
        except Exception:
            continue
        text = data.get('text', '') or ''
        count = text.count(query)
        if count == 0:
            continue
        total_matches += count

        snippets = []
        start = 0
        for _ in range(min(count, MAX_SNIPPETS_PER_PAGE)):
            idx = text.find(query, start)
            if idx == -1:
                break
            snip_start = max(0, idx - CONTEXT)
            snip_end = min(len(text), idx + len(query) + CONTEXT)
            snippets.append(
                ('…' if snip_start > 0 else '') +
                text[snip_start:idx] + '⟦' + text[idx:idx + len(query)] + '⟧' + text[idx + len(query):snip_end] +
                ('…' if snip_end < len(text) else '')
            )
            start = idx + len(query)

        results.append({
            'page_num': page_num,
            'sub_idx': sub_idx,
            'count': count,
            'snippets': snippets,
        })

    return jsonify({
        'query': query,
        'total_matches': total_matches,
        'total_pages': len(results),
        'results': results,
    })


@app.route('/api/correction/replace_all/<job_id>', methods=['POST'])
def replace_all_pages(job_id):
    """Apply a literal find/replace across every saved page that contains a match.

    An explicit, user-directed bulk edit -- unlike the automated correction
    pass, this intentionally does NOT skip pages already flagged
    manual_correction=True; the human driving this action IS the manual
    correction. Marks every page it touches the same way save_corrected_page()
    does, so they behave identically afterwards (dropped from the flagged
    list, protected from any future automated re-correction pass).
    """
    body = request.get_json(silent=True) or {}
    query = body.get('query', '')
    replacement = body.get('replacement', '')
    page_nums = body.get('page_nums')  # optional: list of ints to limit scope

    if not query:
        return jsonify({'error': 'query is required'}), 400

    results_dir = _resolve_results_dir(job_id)
    if not results_dir:
        return jsonify({'error': 'Results not found'}), 404

    import joblib
    import json as _json

    pages_changed = 0
    total_replacements = 0
    changed_page_nums = []
    for page_num, sub_idx, jbl_path in _iter_page_jbl_files(results_dir):
        if page_nums is not None and page_num not in page_nums:
            continue
        try:
            data = joblib.load(jbl_path)
        except Exception:
            continue
        text = data.get('text', '') or ''
        count = text.count(query)
        if count == 0:
            continue

        new_text = text.replace(query, replacement)
        data['text'] = new_text
        # manual_correction=True protects this page from a future automated
        # re-correction pass overwriting the replacement. needs_manual_review
        # is deliberately left untouched -- unlike save_corrected_page() (a
        # full read-through of one page), a bulk find/replace says nothing
        # about whether the page's OTHER flagged dictionary_corrections were
        # actually looked at, so it must not silently clear that flag.
        data['manual_correction'] = True
        joblib.dump(data, jbl_path)

        json_path = jbl_path.with_name(jbl_path.stem + "_text.json")
        if json_path.exists():
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    meta = _json.load(f)
                meta['text'] = new_text
                meta['text_length'] = len(new_text)
                meta['manual_correction'] = True
                with open(json_path, 'w', encoding='utf-8') as f:
                    _json.dump(meta, f, ensure_ascii=False, indent=2)
            except Exception:
                pass

        pages_changed += 1
        total_replacements += count
        changed_page_nums.append(page_num)

    logger.info(
        f"🔎 Find & replace on job {job_id}: '{query}' -> '{replacement}' "
        f"({total_replacements} occurrence(s) across {pages_changed} page(s))"
    )
    return jsonify({
        'pages_changed': pages_changed,
        'total_replacements': total_replacements,
        'changed_page_nums': changed_page_nums,
    })


@app.route('/api/correction/rework/<job_id>/<int:page_num>', methods=['POST'])
def rework_page(job_id, page_num):
    """Re-run OCR for a specific page with a chosen engine."""
    if job_id not in conversion_jobs:
        return jsonify({'error': 'Job not found'}), 404

    body = request.get_json(silent=True) or {}
    engine_name = body.get('engine', 'gemini')
    # sub_idx isn't yet selectable from the correction UI (see
    # docs/TELUGU_SPELL_CORRECTION_TODO.md — only sub_idx 0 is reachable through
    # the dashboard today for double-page-split books), but accept it here so the
    # backend is ready once that's wired up, rather than hardcoding 0 twice.
    sub_idx = int(body.get('sub_idx', 0))
    job = conversion_jobs[job_id]
    converter = job['converter']
    pdf_path = job.get('pdf_path')

    if not pdf_path:
        return jsonify({'error': (
            'This job has no PDF on file (likely resumed from a results folder '
            'without one) — REWORK needs the original PDF to re-run OCR. Viewing, '
            'editing, and REBUILD EBOOK still work without it.'
        )}), 400

    try:
        new_result = converter.rework_page(Path(pdf_path), page_num, engine_name, sub_idx=sub_idx)

        return jsonify({
            'success': True,
            'text': new_result['text'],
            'engine': new_result['ocr_engine']
        })
    except Exception as e:
        logger.error(f"Rework failed for page {page_num}: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/correction/rebuild/<job_id>', methods=['POST'])
def rebuild_book(job_id):
    """Re-combine all results into a fresh EPUB and MOBI."""
    if job_id not in conversion_jobs:
        return jsonify({'error': 'Job not found'}), 404
        
    job = conversion_jobs[job_id]
    converter = job['converter']
    title = job.get('title')
    author = job.get('author')

    # Reuse the exact filename computed at upload time (generate_output_filenames —
    # transliterated from the original PDF name, no session-id suffix). That's the
    # real naming scheme actually used when writing the EPUB (see /upload), so it
    # must match here too — the previous session-id-suffixed glob never matched
    # anything real and silently fell back to a generic "book_<id>.epub" name.
    output_filename = job.get('output_file')
    if output_filename:
        output_path = config.OUTPUT_FOLDER / output_filename
    else:
        safe_title = "".join(c if c.isalnum() else "_" for c in (title or "book"))
        output_path = config.OUTPUT_FOLDER / f"{safe_title}_{job_id[:8]}.epub"

    try:
        success = converter.rebuild_book_from_results(output_path, title=title, author=author)

        if success:
            # /download/<filename> serves from config.OUTPUT_FOLDER directly (see
            # that route) — OUTPUT_FOLDER isn't under Flask's static folder, so
            # url_for('static', ...) built a URL that could never resolve.
            epub_url = f'/download/{output_path.name}'
            mobi_url = None
            mobi_file = output_path.with_suffix('.mobi')
            if mobi_file.exists():
                mobi_url = f'/download/{mobi_file.name}'

            # Keep the in-memory job record consistent with what actually got
            # built — a job stuck on 'pending_review' with no epub_url would
            # otherwise look unfinished to /job/<job_id> polling or a page reload,
            # even though a real EPUB/MOBI now exists on disk.
            job['status'] = 'completed'
            job['epub_url'] = epub_url
            job['mobi_url'] = mobi_url

            return jsonify({
                'success': True,
                'epub_url': epub_url,
                'mobi_url': mobi_url
            })
        else:
            return jsonify({'error': 'Failed to rebuild book'}), 500
    except Exception as e:
        logger.error(f"Rebuild failed: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/repair', methods=['POST'])
def repair_book():
    """Surgically repair an existing eBook."""
    if 'pdf_file' not in request.files or 'epub_file' not in request.files:
        return jsonify({'error': 'Missing files'}), 400

    pdf_file = request.files['pdf_file']
    epub_file = request.files['epub_file']
    pages_str = request.form.get('repair_pages', '').strip()

    if not pdf_file.filename or not epub_file.filename or not pages_str:
        return jsonify({'error': 'Invalid inputs'}), 400

    # repair_book() loads this via ebooklib.epub.read_epub(), which only
    # understands the EPUB (zip/OPF) format — a .mobi file would fail to parse.
    if not epub_file.filename.lower().endswith('.epub'):
        return jsonify({'error': 'Please upload the .epub file (MOBI is not supported for repair — only EPUB can be read back in and patched).'}), 400

    temp_pdf = config.TEMP_FOLDER / f"repair_{uuid.uuid4()}_{pdf_file.filename}"
    temp_epub = config.TEMP_FOLDER / f"repair_{uuid.uuid4()}_{epub_file.filename}"

    try:
        pdf_file.save(str(temp_pdf))
        epub_file.save(str(temp_epub))

        # Parse pages
        from pdf_manipulator import parse_page_ranges
        try:
            repair_pages = parse_page_ranges(pages_str)
        except Exception:
            return jsonify({'error': 'Invalid page format (use 5, 8, 10-12)'}), 400

        # Initialize converter
        from pdf_to_epub_converter_optimized_v2 import OptimizedPDFToEPUBConverter
        converter = OptimizedPDFToEPUBConverter(
            preserve_images=True,
            detect_tables=True
        )

        # output_basename: use the user's original filename for the output name,
        # not temp_epub's stem (which carries the "repair_<uuid>_" prefix added
        # above purely to avoid filename collisions between concurrent requests).
        original_stem = Path(epub_file.filename).stem
        result = converter.repair_book(temp_epub, temp_pdf, repair_pages, output_basename=original_stem)

        if result['success']:
            files = []
            if result['output_path']:
                files.append({
                    'name': result['output_path'].name,
                    'url': url_for('static', filename=f"output/{result['output_path'].name}")
                })
            if result['mobi_path']:
                files.append({
                    'name': result['mobi_path'].name,
                    'url': url_for('static', filename=f"output/{result['mobi_path'].name}")
                })

            return jsonify({
                'success': True,
                'files': files,
                'pages_needing_review': result['pages_needing_review'],
                'warning': result['warning'],
            })
        else:
            return jsonify({'error': result.get('warning') or 'Repair process failed'}), 500

    except Exception as e:
        logger.error(f"Repair route error: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        # Always clean up the temp copies, even if repair_book() raised —
        # previously these leaked on any exception path.
        if temp_pdf.exists():
            temp_pdf.unlink()
        if temp_epub.exists():
            temp_epub.unlink()


@app.route('/api/correction/resume', methods=['POST'])
def resume_correction():
    """
    Reopen an existing conversion's saved results folder (data/temp/<book>_<session>)
    for review/rebuild — without needing the original PDF/EPUB re-uploaded, and without
    needing the job to still be in this server process's memory (conversion_jobs is
    in-memory and is lost on every server restart).

    Unlike /repair, this doesn't re-OCR anything — it reuses the .jbl page results
    already saved on disk, so it also doesn't have /repair's page-numbering risk for
    books that went through double-page splitting (each .jbl file already carries its
    correct original page_num).

    Accepts an optional pdf_file upload (multipart) — viewing/editing/rebuilding all
    work from the saved results alone, but the REWORK (re-OCR with a different
    engine) button needs the original PDF. If provided, it's saved into the results
    folder itself as source.pdf, so a later resume of the same folder picks it up
    automatically without re-uploading every time.
    """
    folder_input = (request.form.get('folder') or (request.get_json(silent=True) or {}).get('folder', '')).strip()
    if not folder_input:
        return jsonify({'error': 'Folder name or path is required'}), 400

    # Accept a full path (Windows or WSL-style) or a bare folder name — always resolve
    # against config.TEMP_FOLDER by name only, so this can never read outside it
    # regardless of what the user pastes in.
    candidate_name = Path(folder_input.replace('\\', '/')).name
    if not candidate_name:
        return jsonify({'error': 'Invalid folder name'}), 400

    target_dir = (config.TEMP_FOLDER / candidate_name).resolve()
    temp_root = config.TEMP_FOLDER.resolve()
    if target_dir != temp_root and temp_root not in target_dir.parents:
        return jsonify({'error': 'Invalid folder'}), 400
    if not target_dir.is_dir():
        return jsonify({'error': f'Folder not found under {temp_root.name}/: {candidate_name}'}), 404

    page_files = list(target_dir.glob("page_*.jbl"))
    if not page_files:
        return jsonify({'error': 'No page results (page_*.jbl) found in this folder — is it a completed conversion?'}), 400

    # The folder is always named f"{title}_{session_id}" (see convert_streaming) with
    # an 8-char session_id — reuse that exact suffix as the resumed job_id so the
    # correction routes' existing `d.name.endswith(job_id[:8])` lookup keeps working
    # unchanged, rather than inventing a new ID and having to special-case lookup.
    resumed_job_id = candidate_name[-8:]
    if len(resumed_job_id) != 8:
        return jsonify({'error': f'Folder name does not end in an 8-character session ID: {candidate_name}'}), 400

    existing = conversion_jobs.get(resumed_job_id)
    if existing and existing.get('status') == 'processing':
        return jsonify({'error': 'This job is still actively converting — cannot resume it now.'}), 409

    # Optional PDF — see docstring. Persisted in the results folder so it's picked
    # up automatically on any future resume of this same folder.
    source_pdf_path = target_dir / "source.pdf"
    uploaded_pdf = request.files.get('pdf_file')
    if uploaded_pdf and uploaded_pdf.filename:
        uploaded_pdf.save(str(source_pdf_path))
    pdf_path = source_pdf_path if source_pdf_path.exists() else None

    from pdf_to_epub_converter_optimized_v2 import OptimizedPDFToEPUBConverter
    converter = OptimizedPDFToEPUBConverter(preserve_images=True, detect_tables=True)
    converter.temp_results_dir = target_dir
    converter.session_id = resumed_job_id
    # rebuild_book_from_results() repopulates page_result_paths from disk itself when
    # empty, so it doesn't need to be filled in here.

    conversion_jobs[resumed_job_id] = {
        'status': 'completed',
        'converter': converter,
        'title': candidate_name.rsplit('_', 1)[0],
        'pdf_path': str(pdf_path) if pdf_path else None,
    }

    logger.info(f"📂 Resumed job {resumed_job_id} from existing folder: {target_dir} (pdf={'yes' if pdf_path else 'no'})")
    return jsonify({
        'success': True,
        'job_id': resumed_job_id,
        'page_count': len(page_files),
        'correction_url': f'/correction/{resumed_job_id}',
        'has_pdf': pdf_path is not None,
    })


# ─────────────────────────────────────────────────────────────
# FILE DUPLICATE FINDER ROUTES
# ─────────────────────────────────────────────────────────────

# In-memory store for scan results (keyed by scan_id)
_dup_scan_store: dict = {}


@app.route('/duplicate/scan', methods=['POST'])
def duplicate_scan():
    """Scan a folder recursively for duplicate files."""
    try:
        data = request.get_json(force=True) or {}
        folder_path = data.get('folder_path', '').strip()
        if not folder_path:
            return jsonify({'error': 'folder_path is required'}), 400
        if not os.path.isdir(folder_path):
            return jsonify({'error': f'Folder not found: {folder_path}'}), 400

        from file_duplicate_finder.scanner import scan_directory
        from file_duplicate_finder.duplicate_detector import detect_duplicates
        import uuid as _uuid

        files = scan_directory(folder_path)
        result = detect_duplicates(files, folder_path)

        scan_id = str(_uuid.uuid4())[:12]
        _dup_scan_store[scan_id] = result

        # Auto-build tree and save content/content.html
        from file_duplicate_finder.tree_builder import build_folder_tree
        from file_duplicate_finder.content_generator import save_content_html

        dup_paths = set()
        orig_paths = set()
        for group in result.groups:
            orig_paths.add(group.original.path)
            for d in group.duplicates:
                dup_paths.add(d.path)

        tree = build_folder_tree(
            folder_path,
            duplicate_paths=dup_paths,
            original_paths=orig_paths,
        )
        content_html_path = save_content_html(
            tree=tree,
            root_path=folder_path,
            duplicate_count=result.total_duplicate_files,
            original_count=len(orig_paths),
            total_files=result.total_files,
            wasted_str=result.wasted_str,
            scan_done=True,
        )
        logger.info(f"Content HTML saved after scan: {content_html_path}")

        return jsonify({
            'success': True,
            'scan_id': scan_id,
            'content_html_path': content_html_path,
            **result.to_dict()
        })

    except Exception as e:
        logger.error(f"Duplicate scan error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/duplicate/tree', methods=['POST'])
def duplicate_tree():
    """
    Build and return a folder tree (folders → files with sizes).
    Optionally marks duplicates/originals if scan_id is provided.

    POST body:
        { "folder_path": "C:/...", "scan_id": "<optional>" }
    """
    try:
        data = request.get_json(force=True) or {}
        folder_path = data.get('folder_path', '').strip()
        if not folder_path:
            return jsonify({'error': 'folder_path is required'}), 400
        if not os.path.isdir(folder_path):
            return jsonify({'error': f'Folder not found: {folder_path}'}), 400

        from file_duplicate_finder.tree_builder import build_folder_tree

        # Collect duplicate/original paths from a previous scan (optional)
        dup_paths = set()
        orig_paths = set()
        scan_id = data.get('scan_id', '').strip()
        if scan_id and scan_id in _dup_scan_store:
            result = _dup_scan_store[scan_id]
            for group in result.groups:
                orig_paths.add(group.original.path)
                for d in group.duplicates:
                    dup_paths.add(d.path)

        tree = build_folder_tree(
            folder_path,
            duplicate_paths=dup_paths,
            original_paths=orig_paths,
        )

        # Auto-save content/content.html inside the chosen folder
        from file_duplicate_finder.content_generator import save_content_html
        scan_result = _dup_scan_store.get(scan_id)
        content_html_path = save_content_html(
            tree=tree,
            root_path=folder_path,
            duplicate_count=len(dup_paths),
            original_count=len(orig_paths),
            total_files=scan_result.total_files if scan_result else 0,
            wasted_str=scan_result.wasted_str if scan_result else '0 B',
            scan_done=bool(scan_result),
        )
        logger.info(f"Content HTML saved: {content_html_path}")

        return jsonify({'success': True, 'tree': tree, 'content_html_path': content_html_path})

    except Exception as e:
        logger.error(f"Duplicate tree error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/duplicate/move', methods=['POST'])
def duplicate_move():
    """Move duplicate files to a destination folder."""
    try:
        data = request.get_json(force=True) or {}
        scan_id = data.get('scan_id', '').strip()
        if not scan_id or scan_id not in _dup_scan_store:
            return jsonify({'error': 'Invalid or expired scan_id. Please scan again.'}), 400

        scan_result = _dup_scan_store[scan_id]
        dest_folder = data.get('dest_folder') or None
        dry_run = bool(data.get('dry_run', False))
        selected_keys = data.get('selected_keys') or None  # list of group_keys, or None = all

        from file_duplicate_finder.file_mover import move_duplicates
        moved, errors = move_duplicates(
            scan_result,
            dest_folder=dest_folder,
            dry_run=dry_run,
            selected_keys=selected_keys,
        )

        # Attach moved info to stored result for report
        _dup_scan_store[f"{scan_id}_moved"] = moved

        return jsonify({
            'success': True,
            'moved_count': len(moved),
            'error_count': len(errors),
            'moved': moved,
            'errors': errors,
            'dry_run': dry_run,
        })

    except Exception as e:
        logger.error(f"Duplicate move error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/duplicate/report/<scan_id>/<fmt>')
def duplicate_report(scan_id, fmt):
    """Download HTML or CSV report for a scan."""
    try:
        if scan_id not in _dup_scan_store:
            return jsonify({'error': 'Scan not found or expired'}), 404

        scan_result = _dup_scan_store[scan_id]
        moved = _dup_scan_store.get(f"{scan_id}_moved")

        if fmt == 'html':
            from file_duplicate_finder.report_generator import generate_html_report
            content = generate_html_report(scan_result, moved)
            from flask import Response
            return Response(
                content,
                mimetype='text/html',
                headers={'Content-Disposition': f'attachment; filename="duplicate_report_{scan_id}.html"'}
            )
        elif fmt == 'csv':
            from file_duplicate_finder.report_generator import generate_csv_report
            content = generate_csv_report(scan_result, moved)
            from flask import Response
            return Response(
                content,
                mimetype='text/csv',
                headers={'Content-Disposition': f'attachment; filename="duplicate_report_{scan_id}.csv"'}
            )
        else:
            return jsonify({'error': 'fmt must be html or csv'}), 400

    except Exception as e:
        logger.error(f"Duplicate report error: {e}")
        return jsonify({'error': str(e)}), 500
# ─────────────────────────────────────────────────────────────
# FILE SEARCH AND COPIER ROUTES
# ─────────────────────────────────────────────────────────────

@app.route('/api/file_search_copier/search', methods=['POST'])
def file_search_copier_search():
    """Search files recursively in a folder matching a word in filename."""
    try:
        data = request.get_json(force=True) or {}
        source_dir = data.get('source_dir', '').strip()
        query_word = data.get('query_word', '').strip()
        case_sensitive = bool(data.get('case_sensitive', False))

        if not source_dir:
            return jsonify({'error': 'Source folder path is required'}), 400
        if not query_word:
            return jsonify({'error': 'Search word is required'}), 400
        if not os.path.isdir(source_dir):
            return jsonify({'error': f'Source folder not found: {source_dir}'}), 400

        from file_search_copier import search_files_by_name
        results = search_files_by_name(
            source_dir=source_dir,
            query_word=query_word,
            case_sensitive=case_sensitive
        )

        return jsonify({
            'success': True,
            'files': results,
            'count': len(results),
            'total_size_bytes': sum(f['size'] for f in results)
        })

    except Exception as e:
        logger.error(f"File search error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/file_search_copier/copy', methods=['POST'])
def file_search_copier_copy():
    """Copy matched files to destination folder."""
    try:
        data = request.get_json(force=True) or {}
        files = data.get('files')
        dest_dir = data.get('dest_dir', '').strip()
        dry_run = bool(data.get('dry_run', False))
        rename_collisions = bool(data.get('rename_collisions', True))

        if not files or not isinstance(files, list):
            return jsonify({'error': 'A list of files to copy is required'}), 400
        if not dest_dir:
            return jsonify({'error': 'Destination folder path is required'}), 400

        from file_search_copier import copy_files_to_dest
        copied, errors = copy_files_to_dest(
            files_list=files,
            dest_dir=dest_dir,
            dry_run=dry_run,
            rename_collisions=rename_collisions
        )

        return jsonify({
            'success': True,
            'copied_count': len(copied),
            'error_count': len(errors),
            'copied': copied,
            'errors': errors,
            'dry_run': dry_run
        })

    except Exception as e:
        logger.error(f"File copy error: {e}")
        return jsonify({'error': str(e)}), 500


@app.errorhandler(413)
def too_large(e):
    """Handle file too large error"""
    return jsonify({
        'error': f'File too large. Maximum size is {config.MAX_FILE_SIZE / (1024*1024):.0f} MB'
    }), 413


@app.route('/api/test_ocr', methods=['GET'])
def test_ocr_endpoint():
    """Debug endpoint to test OCR output on specific files"""
    image_name = request.args.get('image', 'toc')
    if image_name == 'toc':
        img_path = "/mnt/c/Workspace/Antigravity_workspace/Latest_OCR/Myocr_New_08-02-2026/table of contents.png"
    elif image_name == 'stars':
        img_path = "/mnt/c/Workspace/Antigravity_workspace/Latest_OCR/Myocr_New_08-02-2026/star_chars_N_decoration_detections.png"
    else:
        return jsonify({'error': 'Invalid image parameter. Use toc or stars'}), 400

    if not os.path.exists(img_path):
        return jsonify({'error': f'Image file not found at {img_path}'}), 404

    try:
        from PIL import Image
        from paddle_v5_processor import PaddleV5Processor
        from page_complexity_analyzer import PageComplexityAnalyzer
        
        img = Image.open(img_path)
        
        # Run complexity analyzer to see page type
        analyzer = PageComplexityAnalyzer()
        analysis = analyzer.analyze(img)
        
        # Run PaddleOCR
        processor = PaddleV5Processor(language='te', config=config)
        text, boxes = processor._paddle_extract(img)
        
        return jsonify({
            'image': image_name,
            'analysis': {
                'page_type': analysis.get('page_type'),
                'num_columns': analysis.get('num_columns'),
                'is_multicolumn': analysis.get('is_multicolumn'),
                'column_gutter_x': analysis.get('column_gutter_x'),
                'estimated_lines': analysis.get('estimated_lines'),
                'complexity_score': analysis.get('complexity_score'),
            },
            'text': text,
            'boxes_count': len(boxes)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    logger.info(f"Starting Flask server on {config.HOST}:{config.PORT}")
    socketio.run(
        app,
        host=config.HOST,
        port=config.PORT,
        debug=config.DEBUG,
        allow_unsafe_werkzeug=True
    )
