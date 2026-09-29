document.addEventListener("DOMContentLoaded", () => {
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const coarse = window.matchMedia("(pointer: coarse)").matches;
  const body = document.body;

  if (!reduce) body.classList.add("motion-enabled", "page-entering");

  const wait = (ms) => new Promise((resolve) => window.setTimeout(resolve, ms));

  /* ------------------------------------------------------------
     Premium page entrance
     ------------------------------------------------------------ */
  if (!reduce) {
    requestAnimationFrame(() => body.classList.add("page-ready"));
    window.setTimeout(() => body.classList.remove("page-entering"), 780);
  }

  /* ------------------------------------------------------------
     Smart reveal system
     - each component gets a slightly different motion preset
     - IntersectionObserver means offscreen sections cost almost nothing
     ------------------------------------------------------------ */
  const targets = [
    ...document.querySelectorAll(".reveal"),
    ...document.querySelectorAll(".section-head"),
    ...document.querySelectorAll(".category-card"),
    ...document.querySelectorAll(".product-card"),
    ...document.querySelectorAll(".step"),
    ...document.querySelectorAll(".trust-grid > div"),
    ...document.querySelectorAll(".advanced-link"),
    ...document.querySelectorAll(".gallery-card, .product-info-panel, .auth-card, .summary-card, .checkout-card, .order-card"),
    ...document.querySelectorAll(".faq-list details"),
  ];

  const uniqueTargets = [...new Set(targets)];

  uniqueTargets.forEach((el, index) => {
    el.classList.add("motion-target");
    el.style.setProperty("--motion-index", String(index % 9));

    if (el.classList.contains("product-card")) el.dataset.motion = "card";
    else if (el.classList.contains("category-card")) el.dataset.motion = "category";
    else if (el.classList.contains("section-head")) el.dataset.motion = "heading";
    else if (el.classList.contains("step")) el.dataset.motion = "step";
    else if (el.matches(".trust-grid > div")) el.dataset.motion = "trust";
    else if (el.matches(".gallery-card, .product-info-panel, .auth-card, .summary-card, .checkout-card")) el.dataset.motion = "panel";
    else if (el.matches(".faq-list details")) el.dataset.motion = "faq";
    else el.dataset.motion = "fade";
  });

  const revealAll = () => {
    document.querySelectorAll(".motion-target").forEach((el) => el.classList.add("is-visible"));
  };

  if (!reduce && "IntersectionObserver" in window) {
    const observer = new IntersectionObserver((entries, instance) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        entry.target.classList.add("is-visible");
        instance.unobserve(entry.target);
      });
    }, { threshold: 0.07, rootMargin: "0px 0px -6% 0px" });

    uniqueTargets.forEach((el) => observer.observe(el));
  } else {
    revealAll();
  }

  /* ------------------------------------------------------------
     Scroll state + progress. One passive listener + one rAF.
     ------------------------------------------------------------ */
  const progress = document.querySelector("[data-scroll-progress] span");
  const header = document.querySelector(".site-header");
  let scrollFrame = 0;

  const paintScroll = () => {
    const root = document.documentElement;
    const max = Math.max(1, root.scrollHeight - window.innerHeight);
    const ratio = Math.min(1, Math.max(0, window.scrollY / max));

    if (progress) progress.style.transform = `scaleX(${ratio})`;
    header?.classList.toggle("is-scrolled", window.scrollY > 28);
    body.classList.toggle("is-deep-scrolled", window.scrollY > 260);
    scrollFrame = 0;
  };

  window.addEventListener("scroll", () => {
    if (!scrollFrame) scrollFrame = requestAnimationFrame(paintScroll);
  }, { passive: true });

  paintScroll();

  /* ------------------------------------------------------------
     Current nav state
     ------------------------------------------------------------ */
  const currentPath = window.location.pathname.replace(/\/+$/, "") || "/";

  document.querySelectorAll(".nav-link[data-nav]").forEach((link) => {
    const type = link.dataset.nav;
    const active =
      (type === "home" && currentPath === "/") ||
      (type === "shop" && currentPath.startsWith("/shop")) ||
      (type === "orders" && currentPath.startsWith("/orders"));
    link.classList.toggle("is-active", active);
  });

  document.querySelectorAll(".mobile-bottom-nav a").forEach((link) => {
    link.classList.remove("is-current");
    try {
      const path = new URL(link.href, window.location.origin).pathname.replace(/\/+$/, "") || "/";
      if (path === currentPath) link.classList.add("is-current");
    } catch (_) {}
  });

  /* ------------------------------------------------------------
     Cursor aura + magnetic buttons on fine pointers
     ------------------------------------------------------------ */
  if (!reduce && !coarse) {
    const aura = document.createElement("div");
    aura.className = "gb-cursor-aura";
    document.body.appendChild(aura);

    let auraFrame = 0;
    let auraX = window.innerWidth * 0.5;
    let auraY = window.innerHeight * 0.5;
    let targetX = auraX;
    let targetY = auraY;

    const paintAura = () => {
      auraX += (targetX - auraX) * 0.14;
      auraY += (targetY - auraY) * 0.14;
      aura.style.transform = `translate3d(${auraX}px, ${auraY}px, 0)`;
      if (Math.abs(targetX-auraX) > .4 || Math.abs(targetY-auraY) > .4) {
        auraFrame = requestAnimationFrame(paintAura);
      } else auraFrame = 0;
    };

    window.addEventListener("pointermove", (event) => {
      targetX = event.clientX;
      targetY = event.clientY;
      if (!auraFrame) auraFrame = requestAnimationFrame(paintAura);
    }, { passive: true });

    document.querySelectorAll(".btn, .icon-action, .cart-action, .nav-link, .text-link").forEach((el) => {
      let frame = 0;
      let tx = 0, ty = 0, cx = 0, cy = 0;

      const render = () => {
        cx += (tx-cx) * .18;
        cy += (ty-cy) * .18;
        el.style.setProperty("--mx", `${cx}px`);
        el.style.setProperty("--my", `${cy}px`);
        if (Math.abs(tx-cx)>.15 || Math.abs(ty-cy)>.15) frame = requestAnimationFrame(render);
        else frame = 0;
      };

      el.addEventListener("pointermove", (event) => {
        const rect = el.getBoundingClientRect();
        tx = ((event.clientX - rect.left) / rect.width - .5) * 7;
        ty = ((event.clientY - rect.top) / rect.height - .5) * 5;
        if (!frame) frame = requestAnimationFrame(render);
      }, { passive: true });

      el.addEventListener("pointerleave", () => {
        tx = 0;
        ty = 0;
        if (!frame) frame = requestAnimationFrame(render);
      });
    });

    /* Product-card tilt: only the card being hovered gets a frame loop. */
    document.querySelectorAll(".product-card").forEach((card) => {
      let frame = 0;
      let tx = 0, ty = 0, cx = 0, cy = 0;

      const render = () => {
        cx += (tx-cx) * .16;
        cy += (ty-cy) * .16;
        card.style.setProperty("--rx", `${cy}deg`);
        card.style.setProperty("--ry", `${cx}deg`);
        card.style.setProperty("--mxp", `${50 + cx * 3}%`);
        card.style.setProperty("--myp", `${50 + cy * 3}%`);
        if (Math.abs(tx-cx)>.02 || Math.abs(ty-cy)>.02) frame = requestAnimationFrame(render);
        else frame = 0;
      };

      card.addEventListener("pointermove", (event) => {
        const rect = card.getBoundingClientRect();
        const x = (event.clientX - rect.left) / rect.width - .5;
        const y = (event.clientY - rect.top) / rect.height - .5;
        tx = x * 5;
        ty = -y * 5;
        card.classList.add("is-hovered-motion");
        if (!frame) frame = requestAnimationFrame(render);
      }, { passive: true });

      card.addEventListener("pointerleave", () => {
        tx = 0;
        ty = 0;
        card.classList.remove("is-hovered-motion");
        if (!frame) frame = requestAnimationFrame(render);
      });
    });

    /* Category tilt is intentionally weaker. */
    document.querySelectorAll(".category-card").forEach((card) => {
      card.addEventListener("pointermove", (event) => {
        const rect = card.getBoundingClientRect();
        const x = (event.clientX - rect.left) / rect.width - .5;
        const y = (event.clientY - rect.top) / rect.height - .5;
        card.style.setProperty("--category-rx", `${-y * 3}deg`);
        card.style.setProperty("--category-ry", `${x * 3}deg`);
      }, { passive: true });
      card.addEventListener("pointerleave", () => {
        card.style.setProperty("--category-rx", "0deg");
        card.style.setProperty("--category-ry", "0deg");
      });
    });
  }

  /* ------------------------------------------------------------
     Toasts
     ------------------------------------------------------------ */
  document.querySelectorAll("[data-dismiss-toast]").forEach((button) => {
    button.addEventListener("click", () => button.closest(".toast")?.remove());
  });

  if (!reduce) {
    document.querySelectorAll(".toast").forEach((toast) => {
      window.setTimeout(() => {
        toast.classList.add("is-fading");
        window.setTimeout(() => toast.remove(), 250);
      }, 5200);
    });
  }

  /* ------------------------------------------------------------
     Gallery with cinematic image switch
     ------------------------------------------------------------ */
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

  /* ------------------------------------------------------------
     Hero cinematic movement
     ------------------------------------------------------------ */
  document.querySelectorAll("[data-parallax]").forEach((element) => {
    if (reduce || coarse) return;

    let frame = 0;
    let tx = 0, ty = 0, cx = 0, cy = 0;

    const render = () => {
      cx += (tx-cx) * .10;
      cy += (ty-cy) * .10;
      element.style.setProperty("--hero-rx", `${cy}deg`);
      element.style.setProperty("--hero-ry", `${cx}deg`);
      element.style.setProperty("--hero-x", `${cx * 1.6}px`);
      element.style.setProperty("--hero-y", `${cy * 1.6}px`);
      if (Math.abs(tx-cx)>.02 || Math.abs(ty-cy)>.02) frame = requestAnimationFrame(render);
      else frame = 0;
    };

    element.addEventListener("pointermove", (event) => {
      const rect = element.getBoundingClientRect();
      const x = (event.clientX - rect.left) / rect.width - .5;
      const y = (event.clientY - rect.top) / rect.height - .5;
      tx = x * 3.2;
      ty = -y * 3.2;
      element.classList.add("has-pointer-focus");
      if (!frame) frame = requestAnimationFrame(render);
    }, { passive: true });

    element.addEventListener("pointerleave", () => {
      tx = 0; ty = 0;
      element.classList.remove("has-pointer-focus");
      if (!frame) frame = requestAnimationFrame(render);
    });
  });

  /* ------------------------------------------------------------
     Soft page exit transition
     ------------------------------------------------------------ */
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
        if (url.pathname === window.location.pathname && url.search === window.location.search) return;
        body.classList.add("page-leaving");
      } catch (_) {}
    }, { capture: true });
  }

  /* ------------------------------------------------------------
     Image load reveal
     ------------------------------------------------------------ */
  document.querySelectorAll("img").forEach((image) => {
    const ready = () => image.classList.add("image-ready");
    if (image.complete) ready();
    else image.addEventListener("load", ready, { once: true });
    image.addEventListener("error", ready, { once: true });
  });
});

/* Existing variant selector — contract unchanged. */
document.addEventListener("DOMContentLoaded", () => {
  const form = document.querySelector("[data-buy-form]");
  const selected = form?.querySelector("[data-selected-variant]");
  const note = form?.querySelector("[data-selection-note]");
  const priceValue = document.querySelector("[data-price-value]");
  const qty = form?.querySelector("[name=quantity]");

  document.querySelectorAll(".variant-option:not(:disabled)").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll(".variant-option").forEach((item) => item.classList.remove("is-selected"));
      button.classList.add("is-selected");
      if (selected) selected.value = button.dataset.variantId;
      if (priceValue) priceValue.textContent = Number(button.dataset.price).toLocaleString("fa-IR");
      if (qty) {
        qty.max = button.dataset.stock;
        if (Number(qty.value) > Number(button.dataset.stock)) qty.value = button.dataset.stock;
      }
      if (note) {
        note.textContent = `${button.querySelector("strong")?.textContent || "گزینه"} انتخاب شد — موجودی: ${Number(button.dataset.stock).toLocaleString("fa-IR")}`;
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
