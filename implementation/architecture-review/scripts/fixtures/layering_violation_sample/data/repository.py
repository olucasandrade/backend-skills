from handlers.http import format_error_response


def fetch_user(user_id):
    # Layering violation: the data-access layer importing from the
    # presentation/handler layer — a lower layer reaching upward into a
    # higher one, inverting the intended dependency direction.
    try:
        return {"id": user_id}
    except Exception as e:
        return format_error_response(e)
