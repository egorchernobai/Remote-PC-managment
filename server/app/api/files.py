import hashlib
import json
import os

from flask import Blueprint, jsonify, request, send_from_directory
from flask_jwt_extended import get_jwt_identity
from werkzeug.utils import secure_filename

from app import db
from app.audit import log_action
from app.auth import role_required, verify_agent_token
from app.command_queue import push_command
from app.config import Config
from app.models import Agent, Command, FileTransfer


files_bp = Blueprint("files", __name__)

ALLOWED_EXTENSIONS = {
    "cfg",
    "conf",
    "csv",
    "json",
    "log",
    "ps1",
    "py",
    "sh",
    "txt",
    "yaml",
    "yml",
}


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        for chunk in iter(lambda: file.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


@files_bp.route("/upload/<agent_id>", methods=["POST"])
@role_required("operator")
def upload_to_agent(agent_id):
    if "file" not in request.files:
        return jsonify({"error": "No file"}), 400

    uploaded_file = request.files["file"]
    if not allowed_file(uploaded_file.filename):
        return jsonify({"error": "File type not allowed"}), 403

    safe_name = secure_filename(uploaded_file.filename)
    agent = db.session.get(Agent, agent_id)
    if not agent:
        return jsonify({"error": "Agent not found"}), 404

    transfer = FileTransfer(
        agent_id=agent.id,
        initiated_by=get_jwt_identity(),
        direction="upload",
        filename=safe_name,
        status="saving",
    )
    db.session.add(transfer)
    db.session.flush()

    dest_dir = os.path.join(Config.UPLOAD_FOLDER, transfer.id)
    os.makedirs(dest_dir, exist_ok=True)
    dest_path = os.path.join(dest_dir, safe_name)
    uploaded_file.save(dest_path)

    checksum = sha256_file(dest_path)
    transfer.sha256 = checksum
    transfer.size_bytes = os.path.getsize(dest_path)
    transfer.status = "ready"

    command = Command(
        agent_id=agent.id,
        issued_by=get_jwt_identity(),
        command=json.dumps({
            "transfer_id": transfer.id,
            "filename": safe_name,
            "sha256": checksum,
        }),
        cmd_type="file_upload",
        status="pending",
    )
    db.session.add(command)
    db.session.commit()

    push_command(agent.id, command.id)
    log_action(
        get_jwt_identity(),
        "user",
        "file_upload",
        target=agent_id,
        details={"file": safe_name, "sha256": checksum},
    )
    return jsonify({"transfer_id": transfer.id, "command_id": command.id, "sha256": checksum})


@files_bp.route("/fetch/<transfer_id>", methods=["GET"])
def agent_fetch_file(transfer_id):
    agent = verify_agent_token(
        request.headers.get("X-Agent-ID"),
        request.headers.get("X-Agent-Token"),
    )
    if not agent:
        return jsonify({"error": "Unauthorized"}), 401

    transfer = db.session.get(FileTransfer, transfer_id)
    if not transfer or transfer.agent_id != agent.id:
        return jsonify({"error": "Not found"}), 404

    file_dir = os.path.join(Config.UPLOAD_FOLDER, transfer_id)
    return send_from_directory(
        file_dir,
        transfer.filename,
        as_attachment=True,
        etag=transfer.sha256,
    )
