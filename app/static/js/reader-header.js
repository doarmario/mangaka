const readerHeader = document.querySelector('.reader-header');
if (readerHeader) {
    const controls = readerHeader.querySelectorAll('.nav-shell > :not(.brand), .mobile-nav');
    const brand = readerHeader.querySelector('.brand');
    let scheduled = false;
    const updateHeader = () => {
        scheduled = false;
        const reading = window.scrollY > 0;
        // Keep the header's geometry so changing state cannot move the page or
        // shift the original logo position, including the mobile search row.
        readerHeader.classList.toggle('is-reading', reading);
        controls.forEach(control => {
            if (reading && control.contains(document.activeElement)) {
                brand.focus({ preventScroll: true });
            }
            control.inert = reading;
        });
    };
    const schedule = () => {
        if (!scheduled) {
            scheduled = true;
            requestAnimationFrame(updateHeader);
        }
    };
    window.addEventListener('scroll', schedule, { passive: true });
    window.addEventListener('pageshow', schedule);
    updateHeader();
}
