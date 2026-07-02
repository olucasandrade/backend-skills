from flask import Flask, request, session

app = Flask(__name__)


@app.route("/admin/users/<user_id>", methods=["DELETE"])
def delete_user(user_id):
    # Vulnerable: checks that *someone* is logged in, but never checks
    # that the logged-in user actually has admin rights before allowing
    # a destructive, cross-account action.
    if "user_id" not in session:
        return {"error": "not authenticated"}, 401

    db_delete_user(user_id)
    return {"status": "deleted"}


def db_delete_user(user_id):
    pass
