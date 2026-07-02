# fixture: intentional path traversal
import os

from flask import Flask, request, send_file

app = Flask(__name__)

BASE_DIR = "/var/app/uploads"


@app.route("/files/download")
def download_file():
    filename = request.args.get("filename")
    # Vulnerable: no normalization or containment check before joining
    # user-controlled input onto the base directory.
    path = os.path.join(BASE_DIR, filename)
    return send_file(path)
