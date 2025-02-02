const dropZone = document.getElementById('dropZone');
const fileInput = document.getElementById('fileInput');
const uploadProgress = document.getElementById('uploadProgress');
const processingProgress = document.getElementById('processingProgress');
const result = document.getElementById('result');

// Prevent default drag behaviors
['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
    dropZone.addEventListener(eventName, preventDefaults, false);
    document.body.addEventListener(eventName, preventDefaults, false);
});

function preventDefaults (e) {
    e.preventDefault();
    e.stopPropagation();
}

// Handle drop zone events
dropZone.addEventListener('dragenter', () => {
    console.log('File dragged over drop zone');
    dropZone.classList.add('dragover');
});

dropZone.addEventListener('dragleave', () => {
    console.log('File left drop zone');
    dropZone.classList.remove('dragover');
});

dropZone.addEventListener('drop', (e) => {
    console.log('File dropped');
    dropZone.classList.remove('dragover');
    const dt = e.dataTransfer;
    const files = dt.files;
    console.log('Dropped files:', files);
    if (files.length > 0) {
        handleFile(files[0]);
    }
});

// Handle click-to-select
dropZone.addEventListener('click', (e) => {
    // Prevent click from triggering twice when clicking the button
    if (e.target !== dropZone.querySelector('.btn')) {
        fileInput.click();
    }
});

dropZone.querySelector('.btn').addEventListener('click', (e) => {
    e.stopPropagation();  // Prevent event from bubbling to dropZone
    fileInput.click();
});

fileInput.addEventListener('change', (e) => {
    console.log('File selected:', e.target.files);
    if (e.target.files.length > 0) {
        handleFile(e.target.files[0]);
    }
});

function updateProgress(container, progress, status) {
    container.style.display = 'block';
    container.querySelector('.progress-bar').style.width = `${progress}%`;
    if (status) {
        container.querySelector('.status').textContent = status;
    }
}

async function handleFile(file) {
    console.log('Handling file:', file);
    if (!file.name.toLowerCase().endsWith('.pdf')) {
        alert('Please select a PDF file');
        return;
    }

    try {
        // Reset progress displays
        uploadProgress.style.display = 'block';
        processingProgress.style.display = 'none';
        result.style.display = 'none';
        
        // Show initial upload status
        updateProgress(uploadProgress, 0, 'Starting file upload...');
        
        const formData = new FormData();
        formData.append('file', file);

        // Create XMLHttpRequest for upload progress tracking
        const xhr = new XMLHttpRequest();
        const promise = new Promise((resolve, reject) => {
            xhr.upload.onprogress = (event) => {
                if (event.lengthComputable) {
                    const percent = (event.loaded / event.total) * 100;
                    updateProgress(uploadProgress, percent, `Uploading: ${Math.round(percent)}%`);
                }
            };
            
            xhr.onload = () => {
                if (xhr.status >= 200 && xhr.status < 300) {
                    resolve(xhr.response);
                } else {
                    reject(new Error(`HTTP error! status: ${xhr.status}`));
                }
            };
            
            xhr.onerror = () => {
                reject(new Error('Network error occurred'));
            };
        });

        // Open and send the request
        xhr.open('POST', '/api/extract');
        xhr.setRequestHeader('Accept', 'application/json');
        xhr.responseType = 'json';
        xhr.send(formData);

        // Wait for the upload to complete
        const response = await promise;

        // Get job ID and start progress monitoring
        const jobId = xhr.getResponseHeader('X-Job-ID');
        if (!jobId) {
            throw new Error('No job ID received from server');
        }

        // Show initial processing message
        processingProgress.style.display = 'block';
        updateProgress(processingProgress, 0, 'PDF uploaded, initializing OCR processing...');
        updateProgress(uploadProgress, 100, 'Upload complete, processing started');

        // Connect to SSE stream for progress updates
        const eventSource = new EventSource(`/api/progress-stream/${jobId}`);
        
        eventSource.onopen = () => {
            console.log('Progress stream connected');
        };
        
        eventSource.onerror = (error) => {
            console.error('Progress stream error:', error);
            eventSource.close();
            updateProgress(processingProgress, 100, 'Error connecting to progress stream');
        };
        
        // Store the response data
        const responseData = response;
        
        // Set up progress event handling
        eventSource.addEventListener('progress', async (e) => {
            console.log('Progress event received:', e.data);
            const progress = JSON.parse(e.data);
            let statusMessage = `Processing page ${progress.processed} of ${progress.total}`;
            if (progress.estimated_time) {
                statusMessage += ` (${progress.estimated_time.toFixed(1)}s remaining)`;
            }
            statusMessage += '\n\nThis may take several minutes for large documents.';
            statusMessage += '\nTesseract OCR engine is actively processing your document.';
            statusMessage += '\nPlease do not close this window.';
            
            updateProgress(processingProgress, progress.percent, statusMessage);

            if (progress.status === 'completed') {
                console.log('Processing completed, getting results...');
                eventSource.close();
                
                try {
                    // Use the stored response data
                    const data = responseData;
                    console.log('Response data received:', data);
                    
                    // Display results
                    result.style.display = 'block';
                    result.innerHTML = `
                        <h3>Results:</h3>
                        <p>Pages: ${data.metadata.num_pages}</p>
                        <p>Confidence: ${(data.confidence * 100).toFixed(1)}%</p>
                        <p>Processing Time: ${data.processing_time.toFixed(2)}s</p>
                        <h4>Extracted Text:</h4>
                        <pre>${data.text}</pre>
                    `;

                    // Clear progress displays
                    updateProgress(uploadProgress, 100, 'Upload complete');
                    updateProgress(processingProgress, 100, 'Processing complete');
                } catch (error) {
                    console.error('Error getting results:', error);
                    updateProgress(processingProgress, 100, 'Error getting results: ' + error.message);
                }
            }
        });

        // Log initial connection
        console.log('Starting OCR processing with job ID:', jobId);

    } catch (error) {
        console.error('Error:', error);
        uploadProgress.querySelector('.status').textContent = `Error: ${error.message}`;
        uploadProgress.querySelector('.status').classList.add('error');
    }
}
