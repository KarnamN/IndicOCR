// Main JavaScript for PDF to EPUB Converter

let selectedFile = null;
let currentTaskId = null;

// DOM Elements
const uploadArea = document.getElementById('upload-area');
const fileInput = document.getElementById('file-input');
const fileInfo = document.getElementById('file-info');
const metadataForm = document.getElementById('metadata-form');
const uploadSection = document.getElementById('upload-section');
const progressSection = document.getElementById('progress-section');
const resultSection = document.getElementById('result-section');
const errorSection = document.getElementById('error-section');

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    setupEventListeners();
});

function setupEventListeners() {
    // File input change
    fileInput.addEventListener('change', handleFileSelect);

    // Drag and drop
    uploadArea.addEventListener('dragover', handleDragOver);
    uploadArea.addEventListener('dragleave', handleDragLeave);
    uploadArea.addEventListener('drop', handleDrop);

    // Form submit
    metadataForm.addEventListener('submit', handleFormSubmit);

    // Buttons
    document.getElementById('convert-another-btn')?.addEventListener('click', resetForm);
    document.getElementById('try-again-btn')?.addEventListener('click', resetForm);
    document.getElementById('download-btn')?.addEventListener('click', downloadFile);
}

// File Selection
function handleFileSelect(event) {
    const file = event.target.files[0];
    if (file) {
        processFile(file);
    }
}

function handleDragOver(event) {
    event.preventDefault();
    uploadArea.classList.add('dragover');
}

function handleDragLeave(event) {
    event.preventDefault();
    uploadArea.classList.remove('dragover');
}

function handleDrop(event) {
    event.preventDefault();
    uploadArea.classList.remove('dragover');

    const file = event.dataTransfer.files[0];
    if (file && file.type === 'application/pdf') {
        processFile(file);
    } else {
        alert('Please drop a PDF file');
    }
}

function processFile(file) {
    selectedFile = file;

    // Display file info
    document.getElementById('filename').textContent = file.name;
    document.getElementById('filesize').textContent = formatFileSize(file.size);

    // Auto-fill title from filename
    const title = file.name.replace('.pdf', '');
    document.getElementById('title').value = title;

    // Show file info and form
    fileInfo.style.display = 'block';
    metadataForm.style.display = 'block';

    // Hide upload area
    uploadArea.style.display = 'none';
}

function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
}

// Form Submission
async function handleFormSubmit(event) {
    event.preventDefault();

    if (!selectedFile) {
        alert('Please select a file first');
        return;
    }

    // Prepare form data
    const formData = new FormData();
    formData.append('file', selectedFile);
    formData.append('title', document.getElementById('title').value);
    formData.append('author', document.getElementById('author').value);
    formData.append('language', document.getElementById('language').value);
    formData.append('pages_per_chapter', document.getElementById('pages-per-chapter').value);

    // Show progress section
    uploadSection.style.display = 'none';
    progressSection.style.display = 'block';

    try {
        // Upload file
        updateStatus('Uploading file...', 'upload', 0, 100);

        const response = await fetch('/upload', {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Upload failed');
        }

        const data = await response.json();
        currentTaskId = data.task_id;

        // Start monitoring progress
        monitorProgress(currentTaskId);

    } catch (error) {
        showError(error.message);
    }
}

// Progress Monitoring
function monitorProgress(taskId) {
    const eventSource = new EventSource(`/progress/${taskId}`);

    eventSource.onmessage = (event) => {
        const data = JSON.parse(event.data);

        if (data.status === 'processing') {
            const progress = data.progress;
            const stageNames = {
                'extract': 'Extracting pages from PDF',
                'ocr': 'Performing OCR on pages',
                'clean': 'Cleaning extracted text',
                'build': 'Building EPUB file'
            };

            const stageName = stageNames[progress.stage] || progress.stage;
            const percentage = Math.round(progress.percentage);

            updateStatus(
                'Converting...',
                stageName,
                progress.current,
                progress.total
            );

            updateProgressBar(percentage);

        } else if (data.status === 'complete') {
            eventSource.close();
            showSuccess(data.result_file);

        } else if (data.status === 'error') {
            eventSource.close();
            showError(data.error);
        }
    };

    eventSource.onerror = () => {
        eventSource.close();
        // Fallback to polling
        pollProgress(taskId);
    };
}

async function pollProgress(taskId) {
    const pollInterval = setInterval(async () => {
        try {
            const response = await fetch(`/status/${taskId}`);
            const data = await response.json();

            if (data.status === 'processing') {
                const progress = data.progress;
                const percentage = Math.round(progress.percentage);
                updateProgressBar(percentage);

            } else if (data.status === 'complete') {
                clearInterval(pollInterval);
                showSuccess(data.result_file);

            } else if (data.status === 'error') {
                clearInterval(pollInterval);
                showError(data.error);
            }
        } catch (error) {
            clearInterval(pollInterval);
            showError('Failed to get conversion status');
        }
    }, 1000);
}

function updateStatus(status, stage, current, total) {
    document.getElementById('status-text').textContent = status;
    document.getElementById('stage-text').textContent = stage;
    document.getElementById('progress-details').textContent =
        `${stage}: ${current}/${total}`;
}

function updateProgressBar(percentage) {
    const progressFill = document.getElementById('progress-fill');
    const progressPercentage = document.getElementById('progress-percentage');

    progressFill.style.width = `${percentage}%`;
    progressPercentage.textContent = `${percentage}%`;
}

// Success
function showSuccess(filename) {
    progressSection.style.display = 'none';
    resultSection.style.display = 'block';
}

// Error
function showError(message) {
    progressSection.style.display = 'none';
    errorSection.style.display = 'block';
    document.getElementById('error-message').textContent = message;
}

// Download
async function downloadFile() {
    if (!currentTaskId) return;

    try {
        window.location.href = `/download/${currentTaskId}`;

        // Clean up after a delay
        setTimeout(async () => {
            await fetch(`/cleanup/${currentTaskId}`, { method: 'POST' });
        }, 5000);

    } catch (error) {
        alert('Download failed: ' + error.message);
    }
}

// Reset
function resetForm() {
    selectedFile = null;
    currentTaskId = null;

    // Reset form
    metadataForm.reset();
    fileInput.value = '';

    // Hide all sections except upload
    fileInfo.style.display = 'none';
    metadataForm.style.display = 'none';
    progressSection.style.display = 'none';
    resultSection.style.display = 'none';
    errorSection.style.display = 'none';

    // Show upload area
    uploadArea.style.display = 'block';
    uploadSection.style.display = 'block';

    // Reset progress
    updateProgressBar(0);
}
