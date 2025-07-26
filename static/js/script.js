document.addEventListener('DOMContentLoaded', function() {
    // Check if we're on the main page (not login page)
    if (document.getElementById('youtubeLink')) {
        // Select elements for video processing
        const generateBtn = document.getElementById('generateBtn');

        // Generate summary function
        async function generateSummary(videoUrl) {
            if (!videoUrl) {
                alert("Please enter a YouTube video link.");
                return;
            }

            generateBtn.disabled = true;
            generateBtn.textContent = "Generating...";

            try {
                const response = await fetch('/summarize', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ url: videoUrl })
                });

                const data = await response.json();

                if (data.error) {
                    alert(data.error);
                } else {
                    document.getElementById('resultBox').style.display = 'flex';
                    document.getElementById('transcript-content').textContent = data.transcript;
                    document.getElementById('summary-content').textContent = data.summary;
                    
                    // Scroll to results
                    document.getElementById('resultBox').scrollIntoView({ 
                        behavior: 'smooth' 
                    });
                }
            } catch (error) {
                alert("An error occurred. Please try again.");
                console.error('Error generating summary:', error);
            } finally {
                generateBtn.disabled = false;
                generateBtn.textContent = "Generate Summary";
            }
        }

        // Handle generate button click
        generateBtn.addEventListener('click', async () => {
            const urlToProcess = document.getElementById('youtubeLink').value.trim();
            if (!urlToProcess) {
                alert("Please enter a YouTube video link.");
                return;
            }

            await generateSummary(urlToProcess);
        });
    }

    // Login/Signup toggle functionality (for login page)
    if (document.getElementById('toggle-login')) {
        const toggleLogin = document.getElementById('toggle-login');
        const toggleRegister = document.getElementById('toggle-register');
        const formHeading = document.getElementById('form-heading');
        const loginForm = document.getElementById('login-form');
        const registerForm = document.getElementById('register-form');

        toggleLogin.addEventListener('click', () => {
            loginForm.classList.add('active');
            registerForm.classList.remove('active');
            toggleLogin.classList.add('active');
            toggleRegister.classList.remove('active');
            formHeading.textContent = 'Login';
        });

        toggleRegister.addEventListener('click', () => {
            loginForm.classList.remove('active');
            registerForm.classList.add('active');
            toggleLogin.classList.remove('active');
            toggleRegister.classList.add('active');
            formHeading.textContent = 'Register';
        });
    }

    // Close modal when clicking outside
    document.addEventListener('click', function(event) {
        const modal = document.getElementById('playlist-modal');
        if (event.target === modal) {
            closePlaylistModal();
        }
    });

    // Close modal with Escape key
    document.addEventListener('keydown', function(event) {
        if (event.key === 'Escape') {
            closePlaylistModal();
        }
    });
});

// Global variables and functions (outside DOMContentLoaded)
let currentMode = 'video';

// Toggle between video and playlist modes - MUST be global for onclick to work
function toggleMode(mode) {
    console.log('toggleMode called with:', mode); // Debug line
    currentMode = mode;
    
    // Update button states
    const videoBtn = document.getElementById('video-btn');
    const playlistBtn = document.getElementById('playlist-btn');
    
    if (videoBtn && playlistBtn) {
        videoBtn.classList.toggle('active', mode === 'video');
        playlistBtn.classList.toggle('active', mode === 'playlist');
    }
    
    // Update content visibility
    const videoMode = document.getElementById('video-mode');
    const playlistMode = document.getElementById('playlist-mode');
    
    if (videoMode && playlistMode) {
        videoMode.classList.toggle('active', mode === 'video');
        playlistMode.classList.toggle('active', mode === 'playlist');
    }
}

// Generate summary function - MUST be global for onclick to work
function generateSummary() {
    const resultBox = document.getElementById('resultBox');
    const transcriptContent = document.getElementById('transcript-content');
    const summaryContent = document.getElementById('summary-content');
    const youtubeLink = document.getElementById('youtubeLink').value;

    if (!youtubeLink) {
        alert('Please enter a YouTube URL');
        return;
    }

    // Show result box and loading states
    resultBox.style.display = 'flex';
    transcriptContent.innerHTML = 'Generating transcript...';
    summaryContent.innerHTML = 'Generating summary...';

    // Change button to show loading state
    const generateBtn = document.getElementById('generateBtn');
    const originalText = generateBtn.innerHTML;
    generateBtn.innerHTML = 'Generating...';
    generateBtn.disabled = true;

    fetch('/summarize', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ url: youtubeLink })
    })
    .then(response => response.json())
    .then(data => {
        if (data.error) {
            transcriptContent.innerHTML = `Error: ${data.error}`;
            summaryContent.innerHTML = `Error: ${data.error}`;
        } else {
            transcriptContent.innerHTML = data.transcript || 'No transcript available';
            summaryContent.innerHTML = data.summary || 'No summary available';
        }
    })
    .catch(error => {
        console.error('Error:', error);
        transcriptContent.innerHTML = 'An error occurred while generating the summary.';
        summaryContent.innerHTML = 'An error occurred while generating the summary.';
    })
    .finally(() => {
        // Reset button state
        generateBtn.innerHTML = originalText;
        generateBtn.disabled = false;
    });
}

// Load playlist function - MUST be global for onclick to work
function loadPlaylist() {
    const playlistUrl = document.getElementById('playlistLink').value;
    if (!playlistUrl) {
        alert('Please enter a YouTube playlist URL');
        return;
    }
    
    showPlaylistModal();
    showLoading();
    
    fetch('/get-playlist', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ url: playlistUrl })
    })
    .then(response => response.json())
    .then(data => {
        if (data.error) {
            showError(data.error);
        } else {
            displayPlaylistVideos(data.videos);
        }
    })
    .catch(error => {
        console.error('Error:', error);
        showError('An error occurred while loading the playlist.');
    });
}

// Playlist modal functions - MUST be global
function showPlaylistModal() {
    const modal = document.getElementById('playlist-modal');
    if (modal) {
        modal.classList.add('active');
    }
}

function closePlaylistModal() {
    const modal = document.getElementById('playlist-modal');
    if (modal) {
        modal.classList.remove('active');
    }
}

function showLoading() {
    const container = document.getElementById('playlist-videos');
    if (container) {
        container.innerHTML = `
            <div class="loading">
                <i class="fas fa-spinner"></i>
                <p>Loading playlist videos...</p>
            </div>
        `;
    }
}

function showError(message) {
    const container = document.getElementById('playlist-videos');
    if (container) {
        container.innerHTML = `
            <div class="loading">
                <p style="color: red;">Error: ${message}</p>
            </div>
        `;
    }
}

function displayPlaylistVideos(videos) {
    const container = document.getElementById('playlist-videos');
    
    if (!container) return;
    
    if (!videos || videos.length === 0) {
        container.innerHTML = '<div class="loading"><p>No videos found in this playlist.</p></div>';
        return;
    }
    
    container.innerHTML = videos.map(video => `
        <div class="video-item" onclick="selectPlaylistVideo('${video.url}')">
            <img src="${video.thumbnail}" alt="${video.title}" class="video-thumbnail">
            <div class="video-info">
                <div class="video-title">${video.title}</div>
                <div class="video-duration">${video.duration || 'Unknown duration'}</div>
            </div>
        </div>
    `).join('');
}

function selectPlaylistVideo(videoUrl) {
    closePlaylistModal();
    
    // Set the video URL 
    const youtubeInput = document.getElementById('youtubeLink');
    if (youtubeInput) {
        youtubeInput.value = videoUrl;
    }
    
    // Switch to video mode if not already
    if (currentMode !== 'video') {
        toggleMode('video');
    }
    
    // Generate summary for selected video
    generateSummary();
}
