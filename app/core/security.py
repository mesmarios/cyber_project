from functools import wraps

from flask import redirect, session


def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if session.get("user_id") is None:
            return redirect("/login")
        return view(*args, **kwargs)

    return wrapped_view
