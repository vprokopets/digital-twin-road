(function () {
  function attachHeaderHomeLink() {
    var logo = document.querySelector(".md-header__button.md-logo");
    var siteTitle = document.querySelector(
      ".md-header__title .md-header__topic:first-child .md-ellipsis"
    );
    if (!logo || !siteTitle || siteTitle.closest("a") || siteTitle.querySelector("a")) {
      return;
    }
    var href = logo.getAttribute("href") || "./";
    var link = document.createElement("a");
    link.href = href;
    link.className = "dtr-header-home-link";
    link.textContent = siteTitle.textContent.trim();
    link.setAttribute("aria-label", "Digital Twin Road Platform — Documentation Home");
    siteTitle.textContent = "";
    siteTitle.appendChild(link);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", attachHeaderHomeLink);
  } else {
    attachHeaderHomeLink();
  }
})();
