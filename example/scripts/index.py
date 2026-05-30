def init(document):
    title = document.query("#title")
    subtitle = document.query("#subtitle")
    cards = document.query("#cards")
    primary = document.query("#btn-primary")
    secondary = document.query("#btn-secondary")
    note_button = document.query("#btn-note")
    js_button = document.query("#btn-js")
    mirror_button = document.query("#btn-mirror")
    clear_button = document.query("#btn-clear")
    note_input = document.query("#note-input")
    preview = document.query("#preview")
    log = document.query("#log")
    action_count = document.query("#action-count")
    card_count = document.query("#card-count")
    theme_mode = document.query("#theme-mode")

    state = {"accent": False, "count": 0, "cards": 0}

    def log_entry(title_text, body_text):
        entry = document.create_element("div")
        entry.set_attribute("class", "log-entry")
        entry.html = f"<strong>{title_text}</strong><div>{body_text}</div>"
        log.append(entry)

    def seed_log(text):
        log_entry("Showcase", text)

    def refresh_counters():
        action_count.text = str(state["count"])
        card_count.text = str(state["cards"])

    def add_insight_card(label, body):
        card = document.create_element("article")
        card.set_attribute("class", "card")
        card.html = f"<h2>{label}</h2><p>{body}</p>"
        cards.append(card)
        state["cards"] += 1
        refresh_counters()

    def set_mode(mode_label, accent_color):
        title.set_attribute("style", f"color: {accent_color};")
        subtitle.set_attribute("style", f"color: {accent_color}; opacity: 0.85;")
        theme_mode.text = mode_label
        log_entry("Theme", f"Changed theme mode to {mode_label}")

    def run_action(event):
        state["count"] += 1
        title.text = f"Python Action Executed {state['count']} time(s)"
        subtitle.text = "This heading and subtitle were updated from Python through the DOM bridge."
        preview.text = f"Ran Python action #{state['count']} and updated text nodes in place."
        log_entry("Python", f"Primary action ran {state['count']} time(s)")

        badge = document.create_element("p")
        badge.set_attribute("class", "runtime-badge")
        badge.text = f"Updated by Python runtime at step {state['count']}"
        cards.append(badge)
        state["cards"] += 1
        refresh_counters()

    def toggle_accent(event):
        state["accent"] = not state["accent"]
        if state["accent"]:
            set_mode("Accent", "#0f766e")
        else:
            set_mode("Calm", "#0f172a")

    def add_note_card(event):
        note = note_input.text.strip()
        if not note:
            preview.text = "Type a note first, then mirror it into the live preview."
            log_entry("Note", "Ignored empty note input")
            return
        add_insight_card("User Note", note)
        preview.text = note
        note_input.text = ""
        log_entry("Note", f"Mirrored note into the card grid: {note}")

    def run_js_interop(event):
        js.eval("document.body.dataset.melkamInterop = 'done';")
        current = js.eval("document.body.dataset.melkamInterop")
        preview.text = f"JS interop wrote a dataset flag: {current}."
        log_entry("JS", f"Interoperability layer executed and returned {current}")

    def mirror_note(event):
        text = note_input.text.strip()
        if not text:
            preview.text = "Nothing to mirror yet."
            log_entry("Mirror", "No note text available")
            return
        preview.text = text
        log_entry("Mirror", f"Mirrored note: {text}")

    def clear_panel(event):
        cards.html = ""
        log.html = ""
        preview.text = "Preview cleared. Add content again to see live DOM mutations."
        state["cards"] = 0
        refresh_counters()
        seed_log("Reset cards and log panels")

    primary.on("click", run_action)
    secondary.on("click", toggle_accent)
    note_button.on("click", add_note_card)
    js_button.on("click", run_js_interop)
    mirror_button.on("click", mirror_note)
    clear_button.on("click", clear_panel)

    refresh_counters()
    seed_log("Python showcase initialized")
    add_insight_card("DOM Queries", "Elements are found and updated with document.query(...).")
    add_insight_card("Event Binding", "Click handlers are attached from Python using on(...).")
    add_insight_card("JS Interop", "Python can call js.eval(...) and receive a response.")
    seed_log("Try the buttons: add cards, mirror notes, toggle theme, and run JS interop.")


init(document)
