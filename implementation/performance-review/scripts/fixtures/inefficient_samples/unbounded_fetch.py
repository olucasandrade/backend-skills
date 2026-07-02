from flask import Flask, jsonify

app = Flask(__name__)


@app.route("/notifications")
def list_notifications():
    # Inefficient: fetches every notification ever created for every user
    # combined, with no limit/pagination, on every request to this
    # endpoint. Fine at 10 rows, a production incident at 10 million.
    all_notifications = db_fetch_all("SELECT * FROM notifications")
    return jsonify(all_notifications)


def db_fetch_all(query):
    return []
