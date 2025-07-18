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
});
