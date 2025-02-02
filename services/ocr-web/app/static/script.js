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

        // Upload file
        const response = await fetch('/upload', {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            throw new Error(`Upload failed: ${response.statusText}`);
        }

        const responseData = await response.json();
        console.log('Upload response:', responseData);

        // Get job ID from response
        const jobId = responseData.job_id;
        if (!jobId) {
            throw new Error('No job ID received from server');
        }

        // Show initial processing message
        updateProgress(processingProgress, 0, 'PDF uploaded, starting processing...');
        updateProgress(uploadProgress, 100, 'Upload complete');

        // Start polling for status
        const pollInterval = setInterval(async () => {
            try {
                const statusResponse = await fetch(`/status/${jobId}`);
                if (!statusResponse.ok) {
                    throw new Error('Failed to get status');
                }
                const statusData = await statusResponse.json();
                
                const percent = (statusData.progress.completed_chunks / statusData.progress.total_chunks) * 100;
                const statusMessage = `Processing chunks: ${statusData.progress.completed_chunks}/${statusData.progress.total_chunks}`;
                updateProgress(processingProgress, percent, statusMessage);

                if (statusData.status === 'completed') {
                    clearInterval(pollInterval);
                    
                    // Get final results
                    const resultResponse = await fetch(`/result/${jobId}`);
                    if (!resultResponse.ok) {
                        throw new Error('Failed to get results');
                    }
                    const resultData = await resultResponse.json();
                    
                    // Display results
                    result.style.display = 'block';
                    result.innerHTML = `
                        <h3>Results:</h3>
                        <p>File: ${resultData.file_name}</p>
                        <pre>${JSON.stringify(resultData.results, null, 2)}</pre>
                    `;

                    // Clear progress displays
                    updateProgress(uploadProgress, 100, 'Upload complete');
                    updateProgress(processingProgress, 100, 'Processing complete');
                } else if (statusData.status === 'error') {
                    clearInterval(pollInterval);
                    throw new Error(statusData.error || 'Processing failed');
                }
            } catch (error) {
                clearInterval(pollInterval);
                console.error('Status check error:', error);
                updateProgress(processingProgress, 100, `Error: ${error.message}`);
            }
        }, 1000);

    } catch (error) {
        console.error('Error:', error);
        updateProgress(uploadProgress, 100, `Error: ${error.message}`);
    }
}
