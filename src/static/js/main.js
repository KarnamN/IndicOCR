// Main JavaScript for PDF to EPUB Converter with WebSocket Support

let socket = null;
let currentJobId = null;

document.addEventListener('DOMContentLoaded', function () {
    // Initialize Socket.IO
    initializeSocket();
    
    // Initial Quota Check
    refreshGeminiUsage();

    // Elements
    const uploadForm = document.getElementById('uploadForm');
    const fileInput = document.getElementById('fileInput');
    const fileName = document.getElementById('fileName');
    const submitBtn = document.getElementById('submitBtn');
    const progressSection = document.getElementById('progressSection');
    const progressText = document.getElementById('progressText');
    const progressFill = document.getElementById('progressFill');
    const progressPercentage = document.getElementById('progressPercentage');
    const resultSection = document.getElementById('resultSection');
    const successCard = document.getElementById('successCard');
    const errorCard = document.getElementById('errorCard');
    const downloadEpubBtn = document.getElementById('downloadEpubBtn');
    const downloadMobiBtn = document.getElementById('downloadMobiBtn');
    const convertAnotherBtn = document.getElementById('convertAnotherBtn');
    const tryAgainBtn = document.getElementById('tryAgainBtn');
    const statusBtn = document.getElementById('statusBtn');
    const statusModal = document.getElementById('statusModal');
    const modalClose = document.getElementById('modalClose');
    const statusContent = document.getElementById('statusContent');
    const errorMessage = document.getElementById('errorMessage');

    // Complexity Dashboard Elements
    const complexityDashboard = document.getElementById('complexityDashboard');
    const avgComplexity = document.getElementById('avgComplexity');
    const paddleCount = document.getElementById('easyocrCount');   // reuse the easyocr slot for Paddle
    const tesseractCount = document.getElementById('tesseractCount');
    const easyocrCount = document.getElementById('easyocrCount');
    const geminiCount = document.getElementById('geminiCount');
    const pagesAnalyzed = document.getElementById('pagesAnalyzed');
    const complexityTableBody = document.getElementById('complexityTableBody');

    // Stats tracking
    let statsData = {
        totalComplexity: 0,
        pages: 0,
        engines: { paddle: 0, tesseract: 0, easyocr: 0, gemini: 0 }
    };

    // HTTP fallback for job status. Long conversions (an hour or more for a
    // few-hundred-page book) can outlive a single WebSocket connection —
    // laptop sleep, a proxy's idle timeout, a flaky network — and once the
    // socket reconnects with a new session it's no longer in the job's room
    // (see the 'connect' handler above), so a missed 'complete' or
    // 'pending_review' emit previously left the UI stuck on "Converting..."
    // forever with no way to notice the job had actually finished. Polling
    // /job/<id> is the source of truth regardless of socket state.
    let statusPollTimer = null;

    function startStatusPolling(jobId) {
        stopStatusPolling();
        statusPollTimer = setInterval(async () => {
            try {
                const res = await fetch(`/job/${jobId}`);
                if (!res.ok) return;
                const job = await res.json();
                if (job.job_id !== undefined && job.job_id !== jobId) return;

                if (job.status === 'pending_review') {
                    stopStatusPolling();
                    window.location.href = job.correction_url || `/correction/${jobId}`;
                } else if (job.status === 'completed') {
                    stopStatusPolling();
                    showSuccess(job.epub_url, job.mobi_url, job.usage_report);
                    refreshGeminiUsage();
                } else if (job.status === 'failed') {
                    stopStatusPolling();
                    showError(job.error || 'Conversion failed');
                } else if (job.status === 'cancelled') {
                    stopStatusPolling();
                    showError('⛔ Conversion stopped. No incomplete files were created.');
                } else if (typeof job.progress === 'number') {
                    updateProgress(job.stage || 'Processing...', job.progress);
                }
            } catch (e) {
                // Transient network error — just try again on the next tick.
                console.warn('Status poll failed:', e);
            }
        }, 20000);
    }

    function stopStatusPolling() {
        if (statusPollTimer) {
            clearInterval(statusPollTimer);
            statusPollTimer = null;
        }
    }

    // Initialize WebSocket
    function initializeSocket() {
        socket = io();

        socket.on('connect', function () {
            console.log('WebSocket connected');
            // Re-join the job's room after a reconnect (network blip, laptop
            // sleep, long-running job outliving a proxy's idle timeout) — the
            // server's room membership is tied to the socket session, so a
            // fresh connection means future room-scoped emits (progress,
            // pending_review, complete) would otherwise silently never
            // reach this client again, leaving the UI stuck on "Converting...".
            if (currentJobId) {
                socket.emit('join', { job_id: currentJobId });
            }
        });

        socket.on('progress', function (data) {
            if (data.job_id === currentJobId) {
                updateProgress(data.stage, data.percentage);
            }
        });

        socket.on('page_analysis', function (data) {
            if (data.job_id === currentJobId) {
                updatePageAnalysis(data);
            }
        });

        socket.on('complete', function (data) {
            if (data.job_id === currentJobId) {
                stopStatusPolling();
                if (data.success) {
                    showSuccess(data.epub_url, data.mobi_url, data.usage_report);
                    refreshGeminiUsage(); // Update quota after completion
                } else if (data.cancelled) {
                    showError('⛔ Conversion stopped. No incomplete files were created.');
                } else {
                    showError(data.error || 'Conversion failed');
                }
            }
        });

        // Fired instead of 'complete' when dictionary spell-corrections need a
        // human look before the book is built — see
        // docs/TELUGU_SPELL_CORRECTION_TODO.md. No EPUB/MOBI exists yet at this
        // point, so send the user straight to the correction dashboard rather
        // than showing a download/error card that doesn't apply.
        socket.on('pending_review', function (data) {
            if (data.job_id === currentJobId) {
                stopStatusPolling();
                window.location.href = data.correction_url;
            }
        });

        socket.on('disconnect', function () {
            console.log('WebSocket disconnected');
        });

        socket.on('cancelling', function (data) {
            if (data.job_id === currentJobId) {
                const progressText = document.getElementById('progressText');
                if (progressText) {
                    progressText.textContent = '🛑 Stopping after current batch...';
                }
                const stopBtn = document.getElementById('stopBtn');
                if (stopBtn) {
                    stopBtn.disabled = true;
                    stopBtn.querySelector('span').textContent = 'Stopping...';
                }
            }
        });

        socket.on('health_alert', function (data) {
            if (data.job_id === currentJobId) {
                showHealthAlert(data);
            }
        });
    }

    // Update progress
    function updateProgress(stage, percentage) {
        progressText.textContent = stage;
        progressFill.style.width = percentage + '%';
        progressPercentage.textContent = percentage + '%';
    }

    // Show PaddleOCR health alert banner
    function showHealthAlert(data) {
        // Remove any existing alert
        const existing = document.getElementById('healthAlertBanner');
        if (existing) existing.remove();

        const isCritical = data.severity === 'critical';
        const bgColor = isCritical ? '#7f1d1d' : '#78350f';
        const borderColor = isCritical ? '#ef4444' : '#f59e0b';
        const icon = isCritical ? '🚨' : '⚠️';

        const banner = document.createElement('div');
        banner.id = 'healthAlertBanner';
        banner.style.cssText = `
            position: fixed; top: 80px; left: 50%; transform: translateX(-50%);
            background: ${bgColor}; border: 2px solid ${borderColor};
            border-radius: 12px; padding: 20px 28px; max-width: 600px; width: 90%;
            z-index: 9999; box-shadow: 0 8px 32px rgba(0,0,0,0.5);
            font-family: inherit; color: #fff; animation: slideDown 0.3s ease;
        `;

        banner.innerHTML = `
            <div style="display:flex; align-items:flex-start; gap:14px;">
                <span style="font-size:28px; flex-shrink:0;">${icon}</span>
                <div style="flex:1;">
                    <div style="font-weight:700; font-size:16px; margin-bottom:6px;">
                        ${isCritical ? 'PaddleOCR Engine Failure' : 'High Gemini Usage Detected'}
                    </div>
                    <div style="font-size:13px; line-height:1.6; opacity:0.9; margin-bottom:14px;">${data.message}</div>
                    ${ data.hard_crashes !== undefined ? `
                    <div style="font-size:12px; opacity:0.7; margin-bottom:12px;">
                        Hard crashes: <b>${data.hard_crashes}</b> &nbsp;|&nbsp;
                        Soft fails: <b>${data.soft_fails || 0}</b>
                    </div>` : `
                    <div style="font-size:12px; opacity:0.7; margin-bottom:12px;">
                        Gemini pages: <b>${data.gemini_pages}</b> / ${data.total_processed} processed 
                        (<b>${data.percentage}%</b>)
                    </div>`}
                    <div style="display:flex; gap:10px; flex-wrap:wrap;">
                        <button id="healthAlertStop"
                            style="background:#ef4444; border:none; border-radius:8px; color:#fff;
                                   padding:8px 18px; font-weight:600; cursor:pointer; font-size:13px;">
                            🛑 Stop Job
                        </button>
                        <button id="healthAlertContinue"
                            style="background:rgba(255,255,255,0.15); border:1px solid rgba(255,255,255,0.3);
                                   border-radius:8px; color:#fff; padding:8px 18px;
                                   font-weight:600; cursor:pointer; font-size:13px;">
                            ▶️ Continue Anyway
                        </button>
                    </div>
                </div>
            </div>
        `;

        document.body.appendChild(banner);

        document.getElementById('healthAlertStop').addEventListener('click', function() {
            fetch(`/api/job/${currentJobId}/respond`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ action: 'stop' })
            });
            banner.remove();
        });

        document.getElementById('healthAlertContinue').addEventListener('click', function() {
            fetch(`/api/job/${currentJobId}/respond`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ action: 'continue' })
            });
            banner.remove();
        });
    }

    // Update Page Analysis Dashboard
    let processedPages = {}; // Track pages to handle updates instead of duplicates

    function updatePageAnalysis(data) {
        if (!complexityDashboard) return;

        // Show dashboard if hidden
        if (complexityDashboard.style.display === 'none') {
            complexityDashboard.style.display = 'block';
        }

        // Check if we've seen this page before
        const pageNum = data.page_num;
        const rawEngine = data.engine ? data.engine.toLowerCase() : 'tesseract';
        
        // Map raw engine string to standard keys: paddle, tesseract, gemini, easyocr
        let engine = 'tesseract';
        if (rawEngine.includes('paddle') || rawEngine.includes('merged') || rawEngine.includes('mixed')) {
            engine = 'paddle';
        } else if (rawEngine.includes('gemini')) {
            engine = 'gemini';
        } else if (rawEngine.includes('easyocr')) {
            engine = 'easyocr';
        } else if (rawEngine.includes('tesseract')) {
            engine = 'tesseract';
        }
        
        if (processedPages[pageNum]) {
            // It's an update! Remove the old stats
            const oldData = processedPages[pageNum];
            statsData.totalComplexity -= oldData.complexity_score;
            if (statsData.engines[oldData.engine] !== undefined) {
                statsData.engines[oldData.engine]--;
            }
        } else {
            // It's a new page
            statsData.pages++;
        }

        // Add new stats
        statsData.totalComplexity += data.complexity_score;
        if (statsData.engines[engine] !== undefined) {
            statsData.engines[engine]++;
        }
        
        // Save current data for future updates
        processedPages[pageNum] = {
            complexity_score: data.complexity_score,
            engine: engine
        };

        // Update UI stats
        const avgScore = statsData.pages > 0 ? (statsData.totalComplexity / statsData.pages).toFixed(1) : 0;
        if (avgComplexity) {
            avgComplexity.textContent = avgScore;
            avgComplexity.className = 'stat-value ' + getComplexityClass(avgScore);
        }

        if (tesseractCount) tesseractCount.textContent = statsData.engines.tesseract;
        if (easyocrCount) easyocrCount.textContent = statsData.engines.paddle || statsData.engines.easyocr;
        if (geminiCount) geminiCount.textContent = statsData.engines.gemini;
        if (pagesAnalyzed) pagesAnalyzed.textContent = statsData.pages;

        // Add row to table
        if (!complexityTableBody) return;

        const row = document.createElement('tr');

        // Features badges
        let features = [];
        if (data.has_table) features.push('<span class="badge badge-table">Table</span>');
        if (data.has_illustrations) features.push('<span class="badge badge-image">Image</span>');
        if (data.is_multicolumn) features.push('<span class="badge badge-column">Columns</span>');
        if (data.has_mixed_content) features.push('<span class="badge badge-mixed">Mixed</span>');

        const engineIcon = engine === 'gemini' ? '🤖' : (engine === 'paddle' ? '🏏' : '🔧');
        const engineName = engine === 'paddle' ? 'Paddle' : engine.charAt(0).toUpperCase() + engine.slice(1);

        const rowHtml = `
            <td>Page ${data.page_num}</td>
            <td><span class="score-badge ${getComplexityClass(data.complexity_score)}">${data.complexity_score.toFixed(1)}</span></td>
            <td><span class="engine-badge engine-${engine}">${engineIcon} ${engineName}</span></td>
            <td class="features-cell">${features.join(' ') || '-'}</td>
            <td class="reason-cell">${data.reasoning || '-'}</td>
            <td>
                <a href="/correction/${currentJobId}?page=${data.page_num}" target="_blank" class="edit-link">Edit</a>
            </td>
        `;

        // Check if row exists
        const existingRow = document.getElementById(`page-row-${pageNum}`);
        if (existingRow) {
            existingRow.innerHTML = rowHtml;
        } else {
            const row = document.createElement('tr');
            row.id = `page-row-${pageNum}`;
            row.innerHTML = rowHtml;
            // Add to top of table
            if (complexityTableBody.firstChild) {
                complexityTableBody.insertBefore(row, complexityTableBody.firstChild);
            } else {
                complexityTableBody.appendChild(row);
            }
        }
    }

    function getComplexityClass(score) {
        if (score > 80) return 'score-red';
        if (score > 60) return 'score-orange';
        if (score > 40) return 'score-yellow';
        return 'score-green';
    }

    // File input change handler
    fileInput.addEventListener('change', function (e) {
        if (e.target.files.length > 0) {
            const file = e.target.files[0];
            fileName.textContent = file.name;

            // Validate file size
            const maxSize = 1000 * 1024 * 1024; // 1000 MB (1 GB)
            if (file.size > maxSize) {
                showError('File too large. Maximum size is 1000 MB');
                fileInput.value = '';
                fileName.textContent = 'No file selected';
            }
        } else {
            fileName.textContent = 'No file selected';
        }
    });

    // Drag and drop support
    const fileLabel = document.querySelector('.file-label');

    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        fileLabel.addEventListener(eventName, preventDefaults, false);
    });

    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }

    ['dragenter', 'dragover'].forEach(eventName => {
        fileLabel.addEventListener(eventName, highlight, false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
        fileLabel.addEventListener(eventName, unhighlight, false);
    });

    function highlight(e) {
        fileLabel.style.borderColor = 'rgba(102, 126, 234, 0.8)';
        fileLabel.style.background = 'rgba(102, 126, 234, 0.15)';
    }

    function unhighlight(e) {
        fileLabel.style.borderColor = '';
        fileLabel.style.background = '';
    }

    fileLabel.addEventListener('drop', handleDrop, false);

    function handleDrop(e) {
        const dt = e.dataTransfer;
        const files = dt.files;

        if (files.length > 0) {
            fileInput.files = files;
            fileName.textContent = files[0].name;
        }
    }

    // Form submission
    uploadForm.addEventListener('submit', async function (e) {
        e.preventDefault();

        // Validate file
        if (!fileInput.files || fileInput.files.length === 0) {
            showError('Please select a PDF file');
            return;
        }

        // Prepare form data
        const formData = new FormData();
        formData.append('file', fileInput.files[0]);
        formData.append('title', document.getElementById('title').value);
        formData.append('author', document.getElementById('author').value);
        formData.append('language', document.getElementById('language').value);
        formData.append('dpi', document.getElementById('dpi').value);
        // Send 'on' or 'off' to match Python backend expectations
        formData.append('detect_tables', document.getElementById('detectTables').checked ? 'on' : 'off');
        formData.append('preserve_images', document.getElementById('preserveImages').checked ? 'on' : 'off');
        formData.append('enable_rescue', document.getElementById('enableRescue').checked ? 'on' : 'off');

        // Skip OCR pages (image only)
        const skipOcrPages = document.getElementById('skipOcrPages');
        if (skipOcrPages && skipOcrPages.value.trim()) {
            formData.append('skip_ocr_pages', skipOcrPages.value.trim());
        }

        // Only process specific pages
        const onlyPages = document.getElementById('onlyPages');
        if (onlyPages && onlyPages.value.trim()) {
            formData.append('only_pages', onlyPages.value.trim());
        }

        // Show progress
        const bookTitle = document.getElementById('title').value || fileInput.files[0].name;
        showProgress(bookTitle);

        try {
            const response = await fetch('/upload', {
                method: 'POST',
                body: formData
            });

            const result = await response.json();

            if (response.ok && result.success) {
                // Store job ID and join WebSocket room
                currentJobId = result.job_id;
                socket.emit('join', { job_id: currentJobId });
                startStatusPolling(currentJobId);
            } else {
                showError(result.error || 'Upload failed');
            }
        } catch (error) {
            console.error('Error:', error);
            showError('Network error. Please try again.');
        }
    });

    // Show progress
    function showProgress(bookTitle) {
        uploadForm.parentElement.style.display = 'none';
        progressSection.style.display = 'block';
        resultSection.style.display = 'none';
        submitBtn.disabled = true;

        // Reset progress
        const startTime = new Date().toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
        const bookInfoEl = document.getElementById('progressBookInfo');
        if (bookInfoEl) {
            bookInfoEl.textContent = `📖 ${bookTitle} (Started at ${startTime})`;
        }
        
        updateProgress('Initializing...', 0);

        // Reset dashboard
        if (complexityDashboard) {
            complexityDashboard.style.display = 'none';
            if (complexityTableBody) complexityTableBody.innerHTML = '';
            statsData = {
                totalComplexity: 0,
                pages: 0,
                engines: { paddle: 0, tesseract: 0, easyocr: 0, gemini: 0 }
            };
            if (avgComplexity) {
                avgComplexity.textContent = '—';
                avgComplexity.className = 'stat-value';
            }
            processedPages = {}; // Reset processed pages tracking
            if (tesseractCount) tesseractCount.textContent = '0';
            if (easyocrCount) easyocrCount.textContent = '0';
            if (geminiCount) geminiCount.textContent = '0';
            if (pagesAnalyzed) pagesAnalyzed.textContent = '0';
        }
        
        // Hide previous usage report
        const usageReport = document.getElementById('usageReport');
        if (usageReport) usageReport.style.display = 'none';
    }

    // Show success
    function showSuccess(epubUrl, mobiUrl, usageReportData) {
        progressSection.style.display = 'none';
        resultSection.style.display = 'block';
        successCard.style.display = 'block';
        errorCard.style.display = 'none';
        submitBtn.disabled = false;

        // Render Usage Report if available
        if (usageReportData) {
            const reportEl = document.getElementById('usageReport');
            if (reportEl) {
                reportEl.style.display = 'block';
                document.getElementById('reportPaddle').textContent   = usageReportData.paddle_pages || 0;
                document.getElementById('reportTesseract').textContent = usageReportData.tesseract_pages || 0;
                document.getElementById('reportRescue').textContent    = usageReportData.gemini_rescue_pages || 0;
                document.getElementById('reportDirect').textContent    = usageReportData.gemini_direct_pages || 0;
                document.getElementById('reportImage').textContent     = usageReportData.image_only_pages || 0;
                document.getElementById('reportTotal').textContent     = usageReportData.total_pages || 0;
            }
        }

        // Set download URLs
        downloadEpubBtn.href = epubUrl;

        const correctBtn = document.getElementById('correctBtn');
        if (correctBtn) {
            correctBtn.href = `/correction/${currentJobId}`;
        }

        if (mobiUrl) {
            downloadMobiBtn.href = mobiUrl;
            downloadMobiBtn.style.display = 'inline-flex';
        } else {
            downloadMobiBtn.style.display = 'none';
        }

        // Scroll to result
        resultSection.scrollIntoView({ behavior: 'smooth' });
    }

    // Show error
    function showError(message) {
        progressSection.style.display = 'none';
        resultSection.style.display = 'block';
        successCard.style.display = 'none';
        errorCard.style.display = 'block';
        submitBtn.disabled = false;

        errorMessage.textContent = message;

        // Scroll to result
        resultSection.scrollIntoView({ behavior: 'smooth' });
    }

    // Convert another file
    convertAnotherBtn.addEventListener('click', function () {
        resetForm();
    });

    tryAgainBtn.addEventListener('click', function () {
        resetForm();
    });

    function resetForm() {
        uploadForm.reset();
        fileName.textContent = 'No file selected';
        uploadForm.parentElement.style.display = 'block';
        progressSection.style.display = 'none';
        resultSection.style.display = 'none';
        currentJobId = null;

        // Scroll to top
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }

    // Status modal
    statusBtn.addEventListener('click', async function () {
        statusModal.classList.add('active');
        statusContent.innerHTML = '<div class="loading">Loading status...</div>';

        try {
            const response = await fetch('/status');
            const status = await response.json();

            statusContent.innerHTML = `
                <div class="status-grid">
                    <div class="status-item">
                        <span class="status-label">OCR Status</span>
                        <span class="status-value ${status.telugu_support ? 'success' : 'error'}">
                            ${status.telugu_support ? '✓ Configured' : 'Missing Support'}
                        </span>
                    </div>
                    <div class="status-item">
                        <span class="status-label">Gemini Vision</span>
                        <span class="status-value ${status.gemini_available ? 'success' : 'warning'}">
                            ${status.gemini_available ? '✓ Available' : 'Not Configured'}
                        </span>
                    </div>
                    <div class="status-item">
                        <span class="status-label">LangChain</span>
                        <span class="status-value ${status.langchain_enabled ? 'success' : 'neutral'}">
                            ${status.langchain_enabled ? '✓ Enabled' : 'Disabled'}
                        </span>
                    </div>
                    <div class="status-item">
                        <span class="status-label">MOBI Format</span>
                        <span class="status-value ${status.mobi_conversion ? 'success' : 'warning'}">
                            ${status.mobi_conversion ? '✓ Available' : 'Not installed'}
                        </span>
                    </div>
                    <div class="status-item">
                        <span class="status-label">Max File Size</span>
                        <span class="status-value info">${(status.max_file_size / (1024 * 1024)).toFixed(0)} MB</span>
                    </div>
                    <div class="status-item">
                        <span class="status-label">Languages</span>
                        <span class="status-value info">${status.available_languages.join(', ')}</span>
                    </div>
                </div>
            `;
        } catch (error) {
            console.error('Error fetching status:', error);
            statusContent.innerHTML = '<div style="color: #ef4444; text-align: center;">Failed to load status</div>';
        }
    });

    modalClose.addEventListener('click', function () {
        statusModal.classList.remove('active');
    });

    statusModal.addEventListener('click', function (e) {
        if (e.target === statusModal) {
            statusModal.classList.remove('active');
        }
    });

    // Keyboard shortcuts
    document.addEventListener('keydown', function (e) {
        // Escape to close modal
        if (e.key === 'Escape' && statusModal.classList.contains('active')) {
            statusModal.classList.remove('active');
        }
    });

    // Add smooth animations on scroll
    const observerOptions = {
        threshold: 0.1,
        rootMargin: '0px 0px -50px 0px'
    };

    const observer = new IntersectionObserver(function (entries) {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.style.opacity = '1';
                entry.target.style.transform = 'translateY(0)';
            }
        });
    }, observerOptions);

    // Observe feature cards
    document.querySelectorAll('.feature-card').forEach(card => {
        card.style.opacity = '0';
        card.style.transform = 'translateY(20px)';
        card.style.transition = 'opacity 0.6s ease, transform 0.6s ease';
        observer.observe(card);
    });

    // Refresh Gemini Usage from Status API
    async function refreshGeminiUsage() {
        try {
            const response = await fetch('/status');
            const data = await response.json();
            
            if (data.gemini_usage) {
                const calls = data.gemini_usage.calls || 0;
                const quota = data.gemini_usage.quota || 1500;
                const percentage = (calls / quota * 100).toFixed(0);
                
                const usageValue = document.getElementById('geminiUsageValue');
                const usageFill = document.getElementById('geminiUsageFill');
                
                if (usageValue) usageValue.textContent = `${calls}/${quota}`;
                if (usageFill) usageFill.style.width = `${Math.min(percentage, 100)}%`;
                
                // Color coding
                if (percentage > 90) usageFill.style.background = 'var(--error-color)';
                else if (percentage > 70) usageFill.style.background = 'var(--warning-color)';
            }
        } catch (e) {
            console.error("Failed to refresh usage:", e);
        }
    }

    // --- PDF TOOLS LOGIC ---
    const pdfToolsForm = document.getElementById('pdfToolsForm');
    if (pdfToolsForm) {
        pdfToolsForm.addEventListener('submit', handlePdfToolsSubmit);
    }

    // --- BOOK REPAIR LOGIC ---
    const repairForm = document.getElementById('repairForm');
    if (repairForm) {
        repairForm.addEventListener('submit', handleRepairSubmit);
    }

    // --- RESUME FROM FOLDER LOGIC ---
    const resumeForm = document.getElementById('resumeForm');
    if (resumeForm) {
        resumeForm.addEventListener('submit', handleResumeSubmit);
    }
});

async function handleResumeSubmit(e) {
    e.preventDefault();

    const form = e.target;
    const submitBtn = document.getElementById('resumeSubmitBtn');
    const loader = submitBtn.querySelector('.btn-loader');
    const btnText = submitBtn.querySelector('span');
    const resultArea = document.getElementById('resumeResult');
    const errorEl = document.getElementById('resumeError');

    resultArea.style.display = 'none';
    submitBtn.disabled = true;
    loader.style.display = 'block';
    const originalBtnText = btnText.textContent;
    btnText.textContent = 'Opening...';

    try {
        // multipart/form-data (not JSON) — the optional PDF upload needs it, and
        // a plain text field like 'folder' works the same way inside FormData.
        const formData = new FormData(form);

        const response = await fetch('/api/correction/resume', {
            method: 'POST',
            body: formData
        });
        const result = await response.json();

        if (response.ok && result.success) {
            // Straight to the correction dashboard — same destination as
            // resuming a normal in-progress pending-review job.
            window.location.href = result.correction_url;
        } else {
            resultArea.style.display = 'block';
            errorEl.textContent = result.error || 'Could not open that folder.';
        }
    } catch (error) {
        console.error('Error:', error);
        resultArea.style.display = 'block';
        errorEl.textContent = 'Network error. Please try again.';
    } finally {
        submitBtn.disabled = false;
        loader.style.display = 'none';
        btnText.textContent = originalBtnText;
    }
}

async function handleRepairSubmit(e) {
    e.preventDefault();

    const form = e.target;
    const submitBtn = document.getElementById('repairSubmitBtn');
    const loader = submitBtn.querySelector('.btn-loader');
    const btnText = submitBtn.querySelector('span');
    const resultArea = document.getElementById('repairResult');
    const downloadArea = document.getElementById('repairDownloadLinks');

    // Reset state
    resultArea.style.display = 'none';
    downloadArea.innerHTML = '';
    submitBtn.disabled = true;
    loader.style.display = 'block';
    const originalBtnText = btnText.textContent;
    btnText.textContent = 'Repairing eBook...';

    try {
        const formData = new FormData(form);

        const response = await fetch('/repair', {
            method: 'POST',
            body: formData
        });

        const result = await response.json();

        if (response.ok) {
            resultArea.style.display = 'block';

            if (!result.files || result.files.length === 0) {
                downloadArea.innerHTML = `<p style="color: #f59e0b;">Repair completed, but no output file was found — please check the server log.</p>`;
            } else {
                result.files.forEach(file => {
                    const link = document.createElement('a');
                    link.href = file.url;
                    link.className = 'download-btn';
                    link.style.marginBottom = '10px';
                    link.innerHTML = `<span>Download Repaired ${file.name}</span>`;
                    downloadArea.appendChild(link);
                });
            }

            if (result.warning) {
                const warn = document.createElement('p');
                warn.style.cssText = 'color: #f59e0b; margin-top: 10px;';
                warn.textContent = '⚠️ ' + result.warning;
                downloadArea.appendChild(warn);
            }

            if (result.pages_needing_review && result.pages_needing_review.length > 0) {
                const note = document.createElement('p');
                note.style.cssText = 'color: #fbbf24; margin-top: 10px;';
                note.textContent = `⚠️ Automatic spell-correction changed text on page(s) ${result.pages_needing_review.join(', ')} — please double-check these in the repaired file (this one-shot repair flow doesn't have an interactive review step).`;
                downloadArea.appendChild(note);
            }

            // Scroll to result
            resultArea.scrollIntoView({ behavior: 'smooth' });
        } else {
            alert('Repair Error: ' + (result.error || 'Failed to repair eBook'));
        }
    } catch (error) {
        console.error('Error:', error);
        alert('Network error. Please try again.');
    } finally {
        submitBtn.disabled = false;
        loader.style.display = 'none';
        btnText.textContent = originalBtnText;
    }
}

function toggleToolOptions() {
    const operation = document.getElementById('pdfOperation').value;
    const container = document.getElementById('toolOptionsContainer');
    const label = document.getElementById('toolOptionsLabel');
    const input = document.getElementById('toolOptions');
    const hint = document.getElementById('toolOptionsHint');
    const forceSplitContainer = document.getElementById('forceSplitContainer');

    forceSplitContainer.style.display = operation === 'split_wide' ? 'block' : 'none';

    // Hide by default for split_wide
    if (operation === 'split_wide') {
        container.style.display = 'none';
        return;
    }

    container.style.display = 'block';

    switch (operation) {
        case 'split':
            label.textContent = 'Page Ranges';
            input.placeholder = 'e.g., 1-10, 20-30';
            hint.textContent = 'Split the PDF into multiple files based on these ranges.';
            break;
        case 'remove':
            label.textContent = 'Pages to Remove';
            input.placeholder = 'e.g., 5, 8, 12-15';
            hint.textContent = 'These pages will be deleted from the PDF.';
            break;
        case 'extract':
            label.textContent = 'Pages to Extract';
            input.placeholder = 'e.g., 1, 3, 5-10';
            hint.textContent = 'Only these pages will be kept in the new PDF.';
            break;
        case 'reorder':
            label.textContent = 'New Page Order';
            input.placeholder = 'e.g., 10, 1-5, 20-15';
            hint.textContent = 'Specify the exact order of pages for the new PDF.';
            break;
        case 'rotate':
            label.textContent = 'Rotation Angle';
            input.placeholder = '90, 180, or 270';
            hint.textContent = 'Angle to rotate the selected pages.';
            break;
    }
}

async function handlePdfToolsSubmit(e) {
    e.preventDefault();

    const form = e.target;
    const submitBtn = document.getElementById('toolsSubmitBtn');
    const loader = submitBtn.querySelector('.btn-loader');
    const btnText = submitBtn.querySelector('span');
    const resultArea = document.getElementById('toolsResult');
    const downloadArea = document.getElementById('toolsDownloadLinks');

    // Reset state
    resultArea.style.display = 'none';
    downloadArea.innerHTML = '';
    submitBtn.disabled = true;
    loader.style.display = 'block';
    btnText.textContent = 'Processing...';

    try {
        const formData = new FormData(form);

        // Map UI field 'options' to the specific field names the backend uses
        const op = formData.get('operation');
        const opts = formData.get('options');

        if (op === 'split') formData.append('ranges', opts);
        else if (op === 'remove' || op === 'extract' || op === 'rotate') formData.append('pages', opts);
        else if (op === 'reorder') formData.append('order', opts);

        if (op === 'rotate') formData.append('rotation', opts || '90');

        const response = await fetch('/pdf_tools', {
            method: 'POST',
            body: formData
        });

        const result = await response.json();

        if (response.ok) {
            resultArea.style.display = 'block';
            result.files.forEach(file => {
                const link = document.createElement('a');
                link.href = file.url;
                link.className = 'download-btn';
                link.style.marginBottom = '10px';
                link.innerHTML = `<span>Download ${file.name}</span>`;
                downloadArea.appendChild(link);
            });

            // Scroll to result
            resultArea.scrollIntoView({ behavior: 'smooth' });
        } else {
            alert('Error: ' + (result.error || 'Failed to process PDF'));
        }
    } catch (error) {
        console.error('Error:', error);
        alert('Network error. Please try again.');
    } finally {
        submitBtn.disabled = false;
        loader.style.display = 'none';
        btnText.textContent = 'Process PDF';
    }
}

// Global cancel function (called from onclick in HTML)
async function cancelConversion() {
    if (!currentJobId) {
        alert('No active conversion to cancel');
        return;
    }

    const stopBtn = document.getElementById('stopBtn');
    if (stopBtn) {
        stopBtn.disabled = true;
        stopBtn.querySelector('span').textContent = 'Stopping...';
    }

    try {
        const response = await fetch(`/cancel/${currentJobId}`, {
            method: 'POST'
        });

        const result = await response.json();

        if (response.ok && result.success) {
            console.log('Cancel requested:', result.message);
            const progressText = document.getElementById('progressText');
            if (progressText) {
                progressText.textContent = '🛑 Stopping after current batch...';
            }
        } else {
            console.error('Cancel failed:', result.error);
            if (stopBtn) {
                stopBtn.disabled = false;
                stopBtn.querySelector('span').textContent = 'Stop Conversion';
            }
        }
    } catch (error) {
        console.error('Cancel error:', error);
        if (stopBtn) {
            stopBtn.disabled = false;
            stopBtn.querySelector('span').textContent = 'Stop Conversion';
        }
    }
}


