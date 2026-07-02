import json


def render_dashboard(widgets, user_settings_json):
    # Inefficient: re-parses the exact same JSON string on every loop
    # iteration instead of parsing it once outside the loop and reusing
    # the result.
    output = []
    for widget in widgets:
        settings = json.loads(user_settings_json)
        output.append(apply_settings(widget, settings))
    return output


def apply_settings(widget, settings):
    return {**widget, **settings}
