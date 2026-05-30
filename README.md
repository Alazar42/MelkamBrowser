# Melkam Browser

Melkam Browser is a Python-native desktop browser prototype built with PySide6.

## How To Use

1. Install the package in editable mode.

```bash
python -m pip install -e .
```

2. Start the browser.

```bash
python -m melkam_browser
```

3. Use the top shell like a browser toolbar.

- Type a full URL to navigate directly.
- Type normal search text to search the web.
- Use the tabs to open, switch, and close pages.
- Click the built-in plus tab to open a new tab.

4. Open the example showcase from `example/index.html` to see Python-driven DOM updates, notes, and log entries.

## Current scope

- Chromium-backed browser shell with tabs, address bar, navigation buttons, and a built-in new-tab button
- Python scripting through `script type="text/python"` with DOM access and JS interop
- Persistent browser storage and HTTP loading
- Example showcase page with live logs, notes, counters, and DOM updates

## Demo

The app starts in a Chromium-rendered shell, and the example page demonstrates `script type="text/python"` updating the DOM, wiring click handlers, and calling into JavaScript.

## Notes

- The browser shell uses Qt WebEngine as the rendering backend.
- The Python DOM bridge covers common DOM operations for the bundled showcase and browser pages, but it is not a full browser DOM implementation.