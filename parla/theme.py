"""Look of the app: a school exercise book by day, a chalkboard by night.

THEME sets Gradio's own design variables (each with a *_dark twin for the night look).
THEME_HEAD goes into <head>: fonts, the paper/chalkboard page background (outside the
Gradio container, so it can't go into launch(css=...)) and the ☀️/🌙 switch.

Gradio marks night mode with the class "dark" on <body>. By default it follows the
system setting; the switch overrides that and remembers the choice in localStorage.
"""

from __future__ import annotations

import gradio as gr

INK = "#2b3a55"  # navy "fountain pen" text
BLUE = "#2f6fd6"
BLUE_DARK = "#1f4fa8"
RED = "#e5484d"
RED_DARK = "#b8323a"
PAPER = "#fffdf7"
LINE = "#e6dcc6"

BOARD = "#1e3a32"  # chalkboard green
BOARD_LIGHT = "#264a40"
BOARD_DEEP = "#17302a"
CHALK = "#f3f1e7"
CHALK_YELLOW = "#ffd866"
CHALK_YELLOW_DARK = "#d9a832"
CHALK_LINE = "rgba(243, 241, 231, 0.22)"

FONT = [gr.themes.GoogleFont("Nunito"), "ui-rounded", "system-ui", "sans-serif"]

THEME = gr.themes.Base(
    primary_hue=gr.themes.colors.blue,
    secondary_hue=gr.themes.colors.amber,
    neutral_hue=gr.themes.colors.stone,
    radius_size=gr.themes.sizes.radius_lg,
    font=FONT,
).set(
    # page and text
    body_background_fill="#fbf8ef",
    body_background_fill_dark=BOARD,
    body_text_color=INK,
    body_text_color_dark=CHALK,
    body_text_color_subdued="#6b7a94",
    body_text_color_subdued_dark="#b9c4bd",
    background_fill_primary=PAPER,
    background_fill_primary_dark=BOARD_LIGHT,
    background_fill_secondary="#f6f1e4",
    background_fill_secondary_dark=BOARD_DEEP,
    border_color_primary=LINE,
    border_color_primary_dark=CHALK_LINE,
    border_color_accent=BLUE,
    border_color_accent_dark=CHALK_YELLOW,
    border_color_accent_subdued="#f2d675",
    border_color_accent_subdued_dark="rgba(255, 216, 102, 0.55)",
    color_accent=BLUE,
    color_accent_soft="#fff3b0",  # highlighter yellow (your chat bubbles)
    color_accent_soft_dark="rgba(255, 216, 102, 0.16)",
    link_text_color=BLUE,
    link_text_color_dark=CHALK_YELLOW,
    # blocks: sheets of paper / chalk outlines
    block_background_fill=PAPER,
    block_background_fill_dark=BOARD_LIGHT,
    block_border_color=LINE,
    block_border_color_dark=CHALK_LINE,
    block_border_width="1px",
    block_shadow="0 1px 2px rgba(43, 58, 85, 0.06), 0 4px 14px rgba(43, 58, 85, 0.07)",
    block_shadow_dark="0 6px 20px rgba(0, 0, 0, 0.18)",
    block_label_background_fill="#f6f1e4",
    block_label_background_fill_dark=BOARD_DEEP,
    block_label_text_color=INK,
    block_label_text_color_dark=CHALK,
    block_title_text_color=INK,
    block_title_text_color_dark=CHALK,
    block_title_text_weight="700",
    block_label_text_weight="700",
    panel_background_fill="#f6f1e4",
    panel_background_fill_dark=BOARD_DEEP,
    # inputs
    input_background_fill="#ffffff",
    input_background_fill_dark=BOARD_DEEP,
    input_border_color=LINE,
    input_border_color_dark=CHALK_LINE,
    input_border_color_focus=BLUE,
    input_border_color_focus_dark=CHALK_YELLOW,
    input_border_width="1.5px",
    input_placeholder_color="#a3abb9",
    input_placeholder_color_dark="#8fa59c",
    checkbox_background_color_selected=BLUE,
    checkbox_background_color_selected_dark=CHALK_YELLOW,
    checkbox_border_color_selected=BLUE,
    checkbox_border_color_selected_dark=CHALK_YELLOW,
    checkbox_label_background_fill_selected="#e8f0fd",
    checkbox_label_background_fill_selected_dark="rgba(255, 216, 102, 0.16)",
    checkbox_label_border_color_selected=BLUE,
    checkbox_label_border_color_selected_dark=CHALK_YELLOW,
    slider_color=BLUE,
    slider_color_dark=CHALK_YELLOW,
    # buttons: pills with soft shadows; shapes and radii
    block_radius="20px",
    container_radius="20px",
    input_radius="14px",
    button_large_radius="999px",
    button_medium_radius="999px",
    button_small_radius="999px",
    button_large_padding="12px 22px",
    button_border_width="1px",
    button_large_text_weight="800",
    button_small_text_weight="700",
    button_transition="transform 0.12s ease, box-shadow 0.15s ease, background 0.15s",
    button_primary_background_fill=BLUE,
    button_primary_background_fill_hover="#3b7ce6",
    button_primary_background_fill_dark=CHALK_YELLOW,
    button_primary_background_fill_hover_dark="#ffe08a",
    button_primary_border_color=BLUE,
    button_primary_border_color_hover=BLUE,
    button_primary_border_color_dark=CHALK_YELLOW,
    button_primary_border_color_hover_dark=CHALK_YELLOW,
    button_primary_text_color="#ffffff",
    button_primary_text_color_hover="#ffffff",
    button_primary_text_color_dark=BOARD_DEEP,
    button_primary_text_color_hover_dark=BOARD_DEEP,
    button_primary_shadow="0 2px 8px rgba(47, 111, 214, 0.30)",
    button_primary_shadow_hover="0 4px 16px rgba(47, 111, 214, 0.38)",
    button_primary_shadow_active="0 1px 3px rgba(47, 111, 214, 0.30)",
    button_primary_shadow_dark="0 2px 10px rgba(255, 216, 102, 0.22)",
    button_primary_shadow_hover_dark="0 4px 16px rgba(255, 216, 102, 0.30)",
    button_primary_shadow_active_dark="0 1px 3px rgba(255, 216, 102, 0.22)",
    button_secondary_background_fill="#ffffff",
    button_secondary_background_fill_hover="#fff8dc",
    button_secondary_background_fill_dark=BOARD_LIGHT,
    button_secondary_background_fill_hover_dark="#2e574b",
    button_secondary_border_color="#ece4d2",
    button_secondary_border_color_hover="#d8caa8",
    button_secondary_border_color_dark=CHALK_LINE,
    button_secondary_border_color_hover_dark="rgba(243, 241, 231, 0.4)",
    button_secondary_text_color=INK,
    button_secondary_text_color_hover=INK,
    button_secondary_text_color_dark=CHALK,
    button_secondary_text_color_hover_dark=CHALK,
    button_secondary_shadow="0 1px 2px rgba(43, 58, 85, 0.06), 0 4px 14px rgba(43, 58, 85, 0.07)",
    button_secondary_shadow_hover="0 2px 4px rgba(43, 58, 85, 0.08), 0 6px 18px rgba(43, 58, 85, 0.10)",
    button_secondary_shadow_active="0 1px 2px rgba(43, 58, 85, 0.08)",
    button_secondary_shadow_dark="0 2px 8px rgba(0, 0, 0, 0.22)",
    button_secondary_shadow_hover_dark="0 4px 14px rgba(0, 0, 0, 0.28)",
    button_secondary_shadow_active_dark="0 1px 3px rgba(0, 0, 0, 0.22)",
    button_cancel_background_fill=RED,
    button_cancel_background_fill_hover="#ee5d62",
    button_cancel_background_fill_dark="#f07178",
    button_cancel_background_fill_hover_dark="#f48a90",
    button_cancel_border_color=RED,
    button_cancel_border_color_hover=RED,
    button_cancel_border_color_dark="#f07178",
    button_cancel_border_color_hover_dark="#f07178",
    button_cancel_text_color="#ffffff",
    button_cancel_text_color_hover="#ffffff",
    button_cancel_text_color_dark="#2a1012",
    button_cancel_text_color_hover_dark="#2a1012",
    button_cancel_shadow="0 2px 8px rgba(229, 72, 77, 0.30)",
    button_cancel_shadow_hover="0 4px 16px rgba(229, 72, 77, 0.38)",
    button_cancel_shadow_active="0 1px 3px rgba(229, 72, 77, 0.30)",
    button_cancel_shadow_dark="0 2px 10px rgba(240, 113, 120, 0.22)",
    button_cancel_shadow_hover_dark="0 4px 16px rgba(240, 113, 120, 0.30)",
    button_cancel_shadow_active_dark="0 1px 3px rgba(240, 113, 120, 0.22)",
    # tables (word lists)
    table_even_background_fill="#ffffff",
    table_even_background_fill_dark=BOARD_LIGHT,
    table_odd_background_fill="#f8f4ea",
    table_odd_background_fill_dark=BOARD_DEEP,
    table_border_color=LINE,
    table_border_color_dark=CHALK_LINE,
)

# Day: squared exercise-book paper (a red margin line would collide with the sidebar).
# Night: chalkboard with faint chalk dust. The switch's icon comes from CSS, so it
# is always right without any server round trip.
THEME_HEAD = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Patrick+Hand&display=swap">
<style>
body, body > gradio-app, body > gradio-app > div {
  background-color: #fbf8ef !important;
  background-image:
    linear-gradient(rgba(120, 160, 205, 0.18) 1px, transparent 1px),
    linear-gradient(90deg, rgba(120, 160, 205, 0.18) 1px, transparent 1px) !important;
  background-size: 22px 22px !important;
  background-attachment: fixed !important;
}
body.dark, body.dark > gradio-app, body.dark > gradio-app > div {
  background-color: #1e3a32 !important;
  background-image:
    radial-gradient(ellipse at 20% 10%, rgba(255, 255, 255, 0.06), transparent 55%),
    radial-gradient(ellipse at 85% 80%, rgba(255, 255, 255, 0.04), transparent 50%),
    linear-gradient(rgba(255, 255, 255, 0.025) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.025) 1px, transparent 1px) !important;
  background-size: 100% 100%, 100% 100%, 44px 44px, 44px 44px !important;
}
/* Wooden chalkboard frame at the top of the page. */
body.dark > gradio-app { border-top: 8px solid #8a5a35; }
</style>
<script>
(() => {
  const KEY = "parla_theme";
  const wanted = () => localStorage.getItem(KEY);  // "dark", "light" or null (= system)
  const apply = () => {
    const w = wanted();
    if (w && document.body.classList.contains("dark") !== (w === "dark"))
      document.body.classList.toggle("dark", w === "dark");
  };
  // Gradio sets the class itself after loading and when the system setting changes;
  // re-apply the remembered choice whenever that happens.
  const start = () => {
    apply();
    new MutationObserver(apply).observe(document.body, { attributes: true, attributeFilter: ["class"] });
  };
  if (document.body) start(); else document.addEventListener("DOMContentLoaded", start);
  document.addEventListener("click", (e) => {
    if (!e.target.closest("#parla-theme-btn")) return;
    localStorage.setItem(KEY, document.body.classList.contains("dark") ? "light" : "dark");
    apply();
  });
})();
</script>
"""
