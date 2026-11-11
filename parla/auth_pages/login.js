// Parla login — passkeys only. While no passkey exists, the server logs a setup link
// (/login#setup=<token>) that registers the first one.

const el = {
  passkeyButton: document.getElementById("passkeyButton"),
  setup: document.getElementById("setup"),
  setupName: document.getElementById("setupName"),
  setupButton: document.getElementById("setupButton"),
  error: document.getElementById("loginError"),
};

const setupToken = new URLSearchParams(location.hash.slice(1)).get("setup");

init();
// Pasting the setup link into a tab that already shows /login only changes the hash.
addEventListener("hashchange", () => location.reload());

async function init() {
  el.passkeyButton.addEventListener("click", signInWithPasskey);
  el.setupButton.addEventListener("click", createFirstPasskey);
  try {
    const status = await (await fetch("/auth/status", { cache: "no-store" })).json();
    if (status.loggedIn) return location.replace("/");
    if (!window.PublicKeyCredential) return showError("Dieser Browser unterstützt keine Passkeys.");
    if (status.passkeys) {
      el.passkeyButton.hidden = false;
      el.passkeyButton.focus();
    } else if (setupToken) {
      el.setup.hidden = false;
      el.setupName.focus();
    } else {
      showError("Noch kein Passkey registriert. Öffne den Einrichtungslink aus dem Server-Log (docker compose logs parla).");
    }
  } catch {
    showError("Server nicht erreichbar.");
  }
}

async function signInWithPasskey() {
  showError("");
  el.passkeyButton.disabled = true;
  try {
    const optionsJSON = await postJSON("/auth/passkey/options");
    const response = await SimpleWebAuthnBrowser.startAuthentication({ optionsJSON });
    await postJSON("/auth/passkey/verify", { response });
    location.replace("/");
  } catch (err) {
    // NotAllowedError: the user closed the passkey prompt.
    showError(err.name === "NotAllowedError" ? "" : err.message);
    el.passkeyButton.disabled = false;
  }
}

async function createFirstPasskey() {
  showError("");
  el.setupButton.disabled = true;
  try {
    const optionsJSON = await postJSON("/auth/setup/options", { token: setupToken });
    const response = await SimpleWebAuthnBrowser.startRegistration({ optionsJSON });
    await postJSON("/auth/setup/verify", { token: setupToken, response, name: el.setupName.value });
    location.replace("/");
  } catch (err) {
    showError(err.name === "NotAllowedError" ? "" : err.message);
    el.setupButton.disabled = false;
  }
}

async function postJSON(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `Server-Fehler ${res.status}.`);
  return data;
}

function showError(text) {
  el.error.textContent = text;
}
