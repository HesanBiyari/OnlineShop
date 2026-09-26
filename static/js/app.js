document.addEventListener("DOMContentLoaded", () => {
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const reveal = [...document.querySelectorAll(".reveal")];
  if (!reduce && "IntersectionObserver" in window) {
    const io = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) { entry.target.classList.add("is-visible"); io.unobserve(entry.target); }
      });
    }, {threshold:.12});
    reveal.forEach(el => io.observe(el));
  } else reveal.forEach(el => el.classList.add("is-visible"));

  document.querySelectorAll("[data-dismiss-toast]").forEach(btn => btn.addEventListener("click", () => btn.closest(".toast")?.remove()));

  document.addEventListener("click", (event) => {
    const thumb = event.target.closest("[data-gallery-thumb]");
    if (!thumb) return;
    const gallery = thumb.closest("[data-product-gallery]");
    const main = gallery?.querySelector("[data-gallery-main]");
    if (!main) return;
    main.src = thumb.dataset.imageUrl;
    main.alt = thumb.dataset.imageAlt || main.alt;
    gallery.querySelectorAll("[data-gallery-thumb]").forEach(item => item.classList.toggle("is-active", item === thumb));
  });

  document.querySelectorAll("[data-parallax]").forEach(el => {
    if (reduce) return;
    el.addEventListener("pointermove", (e) => {
      const r = el.getBoundingClientRect(), x=(e.clientX-r.left)/r.width-.5, y=(e.clientY-r.top)/r.height-.5;
      el.style.transform=`perspective(900px) rotateY(${x*4}deg) rotateX(${-y*4}deg)`;
    });
    el.addEventListener("pointerleave", () => el.style.transform="");
  });
});