from flask import Flask, request
import sqlite3

app = Flask(__name__)


@app.route("/users/search")
def search_users():
    name = request.args.get("name")
    conn = sqlite3.connect("app.db")
    cur = conn.cursor()
    # Vulnerable: string-concatenated SQL from unsanitized user input.
    query = "SELECT id, email FROM users WHERE name = '" + name + "'"
    cur.execute(query)
    return {"results": cur.fetchall()}
