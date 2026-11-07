(function () {
  const sessionKey = "esg_demo_authenticated";
  const destinationKey = "esg_demo_destination";
  const loginUrl = new URL("login.html", window.location.href);
  const isLoginPage = window.location.pathname === loginUrl.pathname;

  if (!isLoginPage && sessionStorage.getItem(sessionKey) !== "1") {
    sessionStorage.setItem(destinationKey, `${window.location.pathname}${window.location.search}${window.location.hash}`);
    window.location.replace(loginUrl.href);
    return;
  }

  if (!isLoginPage) return;

  document.addEventListener("DOMContentLoaded", function () {
    if (sessionStorage.getItem(sessionKey) === "1") {
      window.location.replace("index.html");
      return;
    }

    const form = document.getElementById("login-form");
    const error = document.getElementById("login-error");
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      const username = form.elements.username.value.trim();
      const password = form.elements.password.value;

      if (username !== "admin" || password !== "esg2026") {
        error.textContent = "Username or password is incorrect.";
        return;
      }

      sessionStorage.setItem(sessionKey, "1");
      const destination = sessionStorage.getItem(destinationKey) || "index.html";
      sessionStorage.removeItem(destinationKey);
      const target = new URL(destination, window.location.origin);
      window.location.replace(target.origin === window.location.origin ? target.href : "index.html");
    });
  });
})();