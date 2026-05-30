# Melkam Browser

Melkam Browser is a Python-native desktop browser prototype built with PySide6.

## Current scope

- Custom GUI shell with tabs, address bar, navigation buttons, and status bar
- Custom HTML tokenizer/parser and DOM tree
- Basic CSS selector and style resolution
- Block and inline layout
- QPainter-based rendering
- Sandboxed Python scripting with DOM access
- Simple storage and HTTP loading

## Run

```bash
python -m pip install -e .
python -m melkam_browser
```

## Demo

The app starts on a built-in page that demonstrates `script type="text/python"` updating the DOM and wiring a click handler without JavaScript.

## Notes

- The browser is intentionally scoped as a custom engine prototype, not a full web compatibility layer.
- The code targets the workspace's available Python runtime and avoids QtWebEngine or Chromium.