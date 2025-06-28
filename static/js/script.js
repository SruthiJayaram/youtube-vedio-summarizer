document.addEventListener("DOMContentLoaded", function () {
    const buttons = document.querySelectorAll('.link-btn');
    buttons.forEach(btn => {
        btn.addEventListener('click', () => {
            buttons.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
        });
    });

    const generateBtn = document.querySelector('.generate-btn');
    generateBtn.addEventListener('click', async () => {
        const urlInput = document.getElementById('youtubeLink').value;
        if (!urlInput) {
            alert("Please enter a YouTube link.");
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
                body: JSON.stringify({ url: urlInput })
            });

            const data = await response.json();

            if (data.error) {
                alert(data.error);
            } else {
                document.getElementById('resultBox').style.display = 'flex';
                document.getElementById('transcript-content').textContent = data.transcript;
                document.getElementById('summary-content').textContent = data.summary;
            }
        } catch (error) {
            alert("An error occurred. Please try again.");
        } finally {
            generateBtn.disabled = false;
            generateBtn.textContent = "Generate Summary";
        }
    });
});
