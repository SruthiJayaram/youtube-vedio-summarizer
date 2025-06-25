document.addEventListener("DOMContentLoaded", function () {
    const buttons = document.querySelectorAll('.link-btn');
    buttons.forEach(btn => {
        btn.addEventListener('click', () => {
            buttons.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
        });
    });
});
