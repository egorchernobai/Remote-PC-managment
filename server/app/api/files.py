import os, hashlib, secrets
from flask import Blueprint, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
from app import db
from app.models import FileTransfer, Agent
from app.auth import role_required, verify_agent_token
from app.audit import log_action
from flask_jwt_extended import get_jwt_identity
from app.config import Config
from app.auth import role_required, verify_agent_token  # ✅

files_bp = Blueprint("files", __name__)

ALLOWED_EXTENSIONS = {
    "txt","log","json","yaml","yml","sh","ps1","py","conf","cfg","csv"
}

def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

@files_bp.route("/upload/<agent_id>", methods=["POST"])
@role_required("operator")
def upload_to_agent(agent_id):
    """Загружаем файл на сервер — агент заберёт его."""
    if "file" not in request.files:
        return jsonify({"error": "No file"}), 400
    f = request.files["file"]
    if not allowed_file(f.filename):
        return jsonify({"error": "File type not allowed"}), 403

    safe_name = secure_filename(f.filename)
    transfer_id = secrets.token_hex(16)
    dest_dir = os.path.join(Config.UPLOAD_FOLDER, transfer_id)
    os.makedirs(dest_dir, exist_ok=True)
    dest_path = os.path.join(dest_dir, safe_name)
    f.save(dest_path)

    checksum = sha256_file(dest_path)
    size = os.path.getsize(dest_path)

    transfer = FileTransfer(
        agent_id=agent_id,
        initiated_by=get_jwt_identity(),
        direction="upload",
        filename=safe_name,
        sha256=checksum,
        size_bytes=size,
        status="ready"
    )
    db.session.add(transfer)
    db.session.commit()

    log_action(get_jwt_identity(), "user", "file_upload",
               target=agent_id, details={"file": safe_name, "sha256": checksum})
    return jsonify({"transfer_id": transfer.id, "sha256": checksum})

@files_bp.route("/fetch/<transfer_id>", methods=["GET"])
def agent_fetch_file(transfer_id):
    """Агент скачивает файл. Проверка токена агента."""
    agent = verify_agent_token(
        request.headers.get("X-Agent-ID"),
        request.headers.get("X-Agent-Token")
    )
    if not agent:
        return jsonify({"error": "Unauthorized"}), 401

    transfer = db.session.get(FileTransfer, transfer_id)
    if not transfer or transfer.agent_id != agent.id:
        return jsonify({"error": "Not found"}), 404

    file_dir = os.path.join(Config.UPLOAD_FOLDER, transfer_id)
    # Защита от path traversal: secure_filename уже применялся при сохранении
    return send_from_directory(file_dir, transfer.filename,
                               as_attachment=True,
                               etag=transfer.sha256)
