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

// Variant selector: keeps the existing Django add_to_cart POST contract while making
// multi-option products explicit about price, stock and selection state.
document.addEventListener("DOMContentLoaded", () => {
  const form = document.querySelector("[data-buy-form]");
  const selected = form?.querySelector("[data-selected-variant]");
  const note = form?.querySelector("[data-selection-note]");
  const priceValue = document.querySelector("[data-price-value]");
  const qty = form?.querySelector("[name=quantity]");
  document.querySelectorAll(".variant-option:not(:disabled)").forEach(btn => btn.addEventListener("click", () => {
    document.querySelectorAll(".variant-option").forEach(x => x.classList.remove("is-selected"));
    btn.classList.add("is-selected");
    if (selected) selected.value = btn.dataset.variantId;
    if (priceValue) priceValue.textContent = Number(btn.dataset.price).toLocaleString("fa-IR");
    if (qty) { qty.max = btn.dataset.stock; if (Number(qty.value) > Number(btn.dataset.stock)) qty.value = btn.dataset.stock; }
    if (note) { note.textContent = `${btn.querySelector("strong")?.textContent || "گزینه"} انتخاب شد — موجودی: ${Number(btn.dataset.stock).toLocaleString("fa-IR")}`; note.classList.add("is-ready"); }
  }));
  form?.addEventListener("submit", e => {
    if (selected && !selected.value) { e.preventDefault(); note?.classList.add("is-error"); note.textContent = "اول یکی از مدل‌های موجود را انتخاب کن."; document.querySelector(".variant-option:not(:disabled)")?.focus(); }
  });
});
