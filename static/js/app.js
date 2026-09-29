document.addEventListener("DOMContentLoaded", () => {
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const body = document.body;

  if (!reduce) body.classList.add("motion-enabled");

  // Progressive reveal: content remains visible when JS is unavailable.
  const targets = [
    ...document.querySelectorAll(".reveal"),
    ...document.querySelectorAll(".section-head"),
    ...document.querySelectorAll(".category-card"),
    ...document.querySelectorAll(".product-card"),
    ...document.querySelectorAll(".step"),
    ...document.querySelectorAll(".trust-grid > div"),
    ...document.querySelectorAll(".advanced-link"),
    ...document.querySelectorAll(
      ".gallery-card, .product-info-panel, .auth-card, .summary-card, .checkout-card"
    ),
  ];

  [...new Set(targets)].forEach((element, index) => {
    element.classList.add("motion-target");
    element.style.setProperty("--motion-index", String(index % 7));
  });

  const revealAll = () => {
    document.querySelectorAll(".motion-target").forEach((element) => {
      element.classList.add("is-visible");
    });
  };

  if (!reduce && "IntersectionObserver" in window) {
    const observer = new IntersectionObserver((entries, instance) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        entry.target.classList.add("is-visible");
        instance.unobserve(entry.target);
      });
    }, {
      threshold: 0.08,
      rootMargin: "0px 0px -7% 0px"
    });

    document.querySelectorAll(".motion-target").forEach((element) => {
      observer.observe(element);
    });
  } else {
    revealAll();
  }

  // Scroll UI: one passive listener, one rAF paint.
  const progress = document.querySelector("[data-scroll-progress] span");
  const header = document.querySelector(".site-header");
  let scrollFrame = 0;

  const paintScrollState = () => {
    const root = document.documentElement;
    const max = Math.max(1, root.scrollHeight - window.innerHeight);
    const ratio = Math.min(1, Math.max(0, window.scrollY / max));

    if (progress) {
      progress.style.transform = `scaleX(${ratio})`;
    }

    header?.classList.toggle("is-scrolled", window.scrollY > 24);
    scrollFrame = 0;
  };

  window.addEventListener("scroll", () => {
    if (scrollFrame) return;
    scrollFrame = requestAnimationFrame(paintScrollState);
  }, { passive: true });

  paintScrollState();

  // Correct active top navigation.
  const currentPath = window.location.pathname.replace(/\/+$/, "") || "/";

  document.querySelectorAll(".nav-link[data-nav]").forEach((link) => {
    const type = link.dataset.nav;
    const active =
      (type === "home" && (currentPath === "/" || currentPath === "")) ||
      (type === "shop" && currentPath.startsWith("/shop")) ||
      (type === "orders" && currentPath.startsWith("/orders"));

    link.classList.toggle("is-active", active);
  });

  // Mobile nav active item.
  document.querySelectorAll(".mobile-bottom-nav a").forEach((link) => {
    link.classList.remove("is-current");
    try {
      const path = new URL(link.href, window.location.origin)
        .pathname.replace(/\/+$/, "") || "/";
      if (path === currentPath) link.classList.add("is-current");
    } catch (_) {}
  });

  // Toasts.
  document.querySelectorAll("[data-dismiss-toast]").forEach((button) => {
    button.addEventListener("click", () => button.closest(".toast")?.remove());
  });

  if (!reduce) {
    document.querySelectorAll(".toast").forEach((toast) => {
      window.setTimeout(() => {
        toast.classList.add("is-fading");
        window.setTimeout(() => toast.remove(), 220);
      }, 5200);
    });
  }

  // Product gallery.
  document.addEventListener("click", (event) => {
    const thumb = event.target.closest("[data-gallery-thumb]");
    if (!thumb) return;

    const gallery = thumb.closest("[data-product-gallery]");
    const main = gallery?.querySelector("[data-gallery-main]");
    if (!main) return;

    main.classList.remove("image-switching");
    void main.offsetWidth;
    main.src = thumb.dataset.imageUrl;
    main.alt = thumb.dataset.imageAlt || main.alt;
    main.classList.add("image-switching");

    gallery.querySelectorAll("[data-gallery-thumb]").forEach((item) => {
      item.classList.toggle("is-active", item === thumb);
    });
  });

  // Lightweight desktop hero tilt + mouse glow.
  document.querySelectorAll("[data-parallax]").forEach((element) => {
    if (reduce || window.matchMedia("(max-width: 800px)").matches) return;

    let frame = 0;
    let targetX = 0;
    let targetY = 0;
    let currentX = 0;
    let currentY = 0;

    const render = () => {
      currentX += (targetX - currentX) * 0.12;
      currentY += (targetY - currentY) * 0.12;

      element.style.transform =
        `perspective(900px) rotateY(${currentX}deg) rotateX(${-currentY}deg)`;

      if (
        Math.abs(targetX - currentX) > 0.01 ||
        Math.abs(targetY - currentY) > 0.01
      ) {
        frame = requestAnimationFrame(render);
      } else {
        frame = 0;
      }
    };

    element.addEventListener("pointermove", (event) => {
      const rect = element.getBoundingClientRect();
      const x = (event.clientX - rect.left) / rect.width - 0.5;
      const y = (event.clientY - rect.top) / rect.height - 0.5;

      targetX = x * 3.5;
      targetY = y * 3.5;

      element.style.setProperty("--gb-mx", `${(x + 0.5) * 100}%`);
      element.style.setProperty("--gb-my", `${(y + 0.5) * 100}%`);

      if (!frame) frame = requestAnimationFrame(render);
    }, { passive: true });

    element.addEventListener("pointerleave", () => {
      targetX = 0;
      targetY = 0;
      element.style.setProperty("--gb-mx", "50%");
      element.style.setProperty("--gb-my", "50%");
      if (!frame) frame = requestAnimationFrame(render);
    });
  });

  // Soft same-origin page transition. Never blocks navigation.
  if (!reduce) {
    document.addEventListener("click", (event) => {
      const link = event.target.closest("a");
      if (!link || event.defaultPrevented) return;
      if (event.button !== 0) return;
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      if (link.target && link.target !== "_self") return;

      try {
        const url = new URL(link.href, window.location.href);
        if (url.origin !== window.location.origin) return;
        if (url.hash && url.pathname === window.location.pathname && url.search === window.location.search) return;
        body.classList.add("page-leaving");
      } catch (_) {}
    }, { capture: true });
  }

  // Image reveal after load.
  document.querySelectorAll("img").forEach((image) => {
    const ready = () => image.classList.add("image-ready");
    if (image.complete) ready();
    else image.addEventListener("load", ready, { once: true });
    image.addEventListener("error", ready, { once: true });
  });
});

// Existing multi-variant purchase behavior — Django POST contract unchanged.
document.addEventListener("DOMContentLoaded", () => {
  const form = document.querySelector("[data-buy-form]");
  const selected = form?.querySelector("[data-selected-variant]");
  const note = form?.querySelector("[data-selection-note]");
  const priceValue = document.querySelector("[data-price-value]");
  const qty = form?.querySelector("[name=quantity]");

  document.querySelectorAll(".variant-option:not(:disabled)").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll(".variant-option").forEach((item) => {
        item.classList.remove("is-selected");
      });

      button.classList.add("is-selected");

      if (selected) selected.value = button.dataset.variantId;
      if (priceValue) priceValue.textContent = Number(button.dataset.price).toLocaleString("fa-IR");

      if (qty) {
        qty.max = button.dataset.stock;
        if (Number(qty.value) > Number(button.dataset.stock)) {
          qty.value = button.dataset.stock;
        }
      }

      if (note) {
        note.textContent =
          `${button.querySelector("strong")?.textContent || "گزینه"} انتخاب شد — موجودی: ${Number(button.dataset.stock).toLocaleString("fa-IR")}`;
        note.classList.add("is-ready");
      }
    });
  });

  form?.addEventListener("submit", (event) => {
    if (selected && !selected.value) {
      event.preventDefault();
      if (note) {
        note.classList.remove("is-error");
        void note.offsetWidth;
        note.classList.add("is-error");
        note.textContent = "اول یکی از مدل‌های موجود را انتخاب کن.";
      }
      document.querySelector(".variant-option:not(:disabled)")?.focus();
    }
  });
});
