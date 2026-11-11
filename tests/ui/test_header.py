"""Chat header: the scene picker."""

import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.ui


def open_chat(page):
    page.click("#parla-nav-chat")
    expect(page.locator("#parla-scenario")).to_be_visible()


def test_scene_picker_only_on_chat_page(page):
    open_chat(page)
    page.click("#parla-nav-trainer")
    expect(page.locator("#parla-scenario")).to_be_hidden()


@pytest.mark.parametrize("target", ["input", ".dropdown-arrow"])
def test_scene_picker_opens_on_text_and_arrow(page, target):
    open_chat(page)
    # Click at the spot on screen, like a finger or mouse: the arrow itself ignores
    # pointer events, so whatever lies under it there must open the list.
    box = page.locator(f"#parla-scenario {target}").bounding_box()
    page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    options = page.get_by_role("option")
    expect(options.first).to_be_visible()
    expect(options).to_contain_text(  # the selected one also has a "✓"
        ["Libero", "Al bar", "In albergo", "Al ristorante", "Indicazioni", "Dal medico", "Tra colleghi"]
    )
