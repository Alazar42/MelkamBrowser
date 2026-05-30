def init(document):
    title = document.query("#title")
    subtitle = document.query("#subtitle")
    cards = document.query("#cards")
    primary = document.query("#btn-primary")
    secondary = document.query("#btn-secondary")

    state = {"accent": False, "count": 0}

    def run_action(event):
        state["count"] += 1
        title.text = f"Python Action Executed {state['count']} time(s)"
        subtitle.text = "The DOM update above came from a native Python callback."

        badge = document.create_element("p")
        badge.set_attribute("class", "runtime-badge")
        badge.text = "Updated by Python runtime"
        cards.append(badge)

    def toggle_accent(event):
        state["accent"] = not state["accent"]
        if state["accent"]:
            title.set_attribute("style", "color: #0f766e;")
            subtitle.set_attribute("style", "color: #115e59;")
        else:
            title.set_attribute("style", "color: #0f172a;")
            subtitle.set_attribute("style", "color: #334155;")

    primary.on("click", run_action)
    secondary.on("click", toggle_accent)


init(document)
