"""Keyboard shortcuts (injected into the page head) and their help text."""

from __future__ import annotations

# Alt (⌥ on the Mac) combinations work everywhere, even while typing. They use
# KeyboardEvent.code, so they also work on a German Mac keyboard where ⌥+R types "®".
# Single keys only work when no text field has the focus (press Esc to leave one).
SHORTCUTS_JS = """
<script>
(() => {
  const visible = (el) => el && el.offsetParent !== null;
  const button = (id) => {
    const el = document.getElementById(id);
    if (!el) return null;
    return el.tagName === "BUTTON" ? el : el.querySelector("button");
  };
  const click = (id) => {
    const b = button(id);
    if (visible(b) && !b.disabled) { b.click(); return true; }
    return false;
  };
  const typing = (el) =>
    el && (el.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName));

  const toggleRecording = () =>
    visible(document.getElementById("parla-talk")) && window.parlaVoice?.key();

  function toggleTranslation() {
    const all = document.querySelectorAll("#parla-chat details.parla-translation");
    const last = all[all.length - 1];
    if (!last) return false;
    last.open = !last.open;
    return true;
  }

  const PAGES = ["chat", "trainer", "lookup", "editor", "settings"];
  function selectPage(n) {
    const b = PAGES[n] && button("parla-nav-" + PAGES[n]);
    if (!b) return false;
    b.click();
    return true;
  }

  // Burger menu: open/close without a server round trip. Picking a page, tapping
  // beside the menu or pressing Esc closes it.
  const nav = () => document.getElementById("parla-nav");
  const navOpen = () => !!nav()?.classList.contains("open");
  const setNav = (open) => nav()?.classList.toggle("open", open);
  document.addEventListener("click", (e) => {
    if (e.target.closest("#parla-burger")) setNav(!navOpen());
    else if (navOpen() && (e.target.closest(".parla-nav-item") || !e.target.closest("#parla-nav")))
      setNav(false);
  });

  document.addEventListener("keydown", (e) => {
    if (e.defaultPrevented || e.isComposing) return;
    if (e.key === "Escape" && navOpen()) { setNav(false); e.preventDefault(); return; }
    let done = false;
    if (e.altKey && !e.ctrlKey && !e.metaKey) {
      const digit = /^Digit([1-9])$/.exec(e.code);
      if (digit) done = selectPage(Number(digit[1]) - 1);
      else if (e.code === "KeyR") done = toggleRecording();
      else if (e.code === "KeyP") done = click("parla-replay");
      else if (e.code === "KeyT") done = toggleTranslation();
    } else if (!e.ctrlKey && !e.metaKey && !e.altKey) {
      if (e.key === "Escape" && typing(document.activeElement)) {
        document.activeElement.blur();
        return;
      }
      if (typing(document.activeElement)) return;
      if (e.key === "/") {
        const msg = document.querySelector("#parla-msg textarea");
        if (visible(msg)) { msg.focus(); done = true; }
      } else if (e.key === " " || e.key === "Enter") {
        done = click("parla-reveal") || (e.key === " " && click("parla-start"));
      } else if (e.key === "ArrowRight" || e.key === "1") {
        done = click("parla-known");
      } else if (e.key === "ArrowLeft" || e.key === "2") {
        done = click("parla-unknown");
      } else if (e.key === "n") {
        done = click("parla-start");
      }
    }
    if (done) e.preventDefault();
  });
})();
</script>
"""

SHORTCUTS_HELP = """
| Taste | Wirkung |
|---|---|
| **⌥ 1** … **⌥ 5** | Seite wechseln (Gespräch, Vokabeltrainer, Nachschlagen, Listen bearbeiten, Einstellungen) |
| **⌥ R** | 🎙️ Aufnahme starten / stoppen (stoppen = senden) · freihändig: an / aus |
| **⌥ P** | 🔊 Letzte Antwort nochmal anhören |
| **⌥ T** | Übersetzung der letzten Antwort auf-/zuklappen |
| **Enter** | Nachricht senden · Suche starten |
| **Esc** | Textfeld verlassen, danach gehen die Einzeltasten |
| **/** | Ins Nachrichtenfeld springen |
| **Leertaste** | Vokabeltrainer: Aufdecken (oder neue Runde starten) |
| **→** oder **1** | Vokabeltrainer: ✅ Gewusst |
| **←** oder **2** | Vokabeltrainer: ❌ Nicht gewusst |
| **N** | Vokabeltrainer: neue Runde |

⌥ = Alt-/Option-Taste. Die Einzeltasten wirken nur, wenn kein Textfeld aktiv ist.
"""
