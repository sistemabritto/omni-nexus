"""Share links — create, list, revoke, and public view endpoints for workspace files."""

import mimetypes
import os
import secrets
from datetime import datetime, timezone, timedelta
from pathlib import Path

from urllib.parse import urlparse

from flask import Blueprint, jsonify, redirect, request, Response, after_this_request, send_file
from flask_login import login_required, current_user

from models import db, FileShare, ShareEvent, audit, has_workspace_folder_access
from rate_limit import limiter
from routes.auth_routes import require_permission

bp = Blueprint("shares", __name__)


def _public_base_url() -> str:
    """URL pública pra montar o link de share. `request.host_url` reflete o
    Host da requisição — quando quem chama é o media_worker (via sdk_client,
    hostname interno do service mesh), o link vira
    "http://evonexus-dashboard:8080/share/...", que não abre em lugar nenhum
    fora da rede Swarm. Achado ao vivo em 29/07/2026: o ticket de aprovação
    dos cortes virais saiu com esse link. NEXUS_PUBLIC_URL já estava
    documentado em .env.example pra esse exato cenário, só nunca tinha sido
    lido pelo código.
    """
    return (os.environ.get("NEXUS_PUBLIC_URL") or os.environ.get("NGROK_URL")
            or request.host_url).rstrip("/")


# Resolve REPO_ROOT relative to this file: backend/routes/ → workspace root (3 levels up)
REPO_ROOT = Path(__file__).resolve().parents[3]
WORKSPACE_DIR = REPO_ROOT / "workspace"
# Esteira de vídeo (Fase 1B): a página de revisão do corte editorial nasce no
# workspace do MediaJob (media_workspace_root(), volume separado do
# workspace/ geral), não em workspace/reports/. Sem esta segunda raiz
# permitida, todo artefato de vídeo pra aprovação humana ficaria sem como
# virar link — teria que copiar arquivo de 1+GB entre volumes só pra servir
# uma página de texto.
MEDIA_WORKSPACE_DIR = Path(os.environ.get("MEDIA_WORKSPACE") or (REPO_ROOT / "media")).resolve()

_EXPIRY_MAP = {
    "1h": timedelta(hours=1),
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
}

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico", ".bmp"}
_VIDEO_EXTS = {".mp4", ".webm", ".mov", ".avi", ".mkv", ".ogv"}
_AUDIO_EXTS = {".mp3", ".wav", ".ogg", ".aac", ".flac", ".m4a", ".wma"}
_PDF_EXTS = {".pdf"}
_CODE_EXTS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".json", ".yaml", ".yml",
    ".toml", ".sh", ".bash", ".zsh", ".env", ".tf", ".go", ".rs",
    ".java", ".c", ".cpp", ".h", ".css", ".scss", ".xml", ".sql",
}


def _resolve_path_safe(path_str: str) -> Path | None:
    """Resolve a repo-relative path for share serving (no user context needed).

    Returns the resolved Path if valid, or None on any security violation.
    Only allows paths within WORKSPACE_DIR (no admin paths via shares).
    """
    if not path_str or "\x00" in path_str:
        return None
    p = Path(path_str)
    if p.is_absolute():
        return None

    full = (REPO_ROOT / path_str).resolve()

    # Must stay inside WORKSPACE_DIR or MEDIA_WORKSPACE_DIR — nunca fora dos
    # dois, e nunca aceitar caminho absoluto vindo do cliente (checado acima).
    for raiz in (WORKSPACE_DIR.resolve(), MEDIA_WORKSPACE_DIR):
        try:
            full.relative_to(raiz)
            return full
        except ValueError:
            continue
    return None


def _content_type_for(path: Path) -> str:
    """Return the MIME type for the given path."""
    suffix = path.suffix.lower()
    if suffix in (".html", ".htm"):
        return "text/html; charset=utf-8"
    if suffix in _IMAGE_EXTS:
        mime, _ = mimetypes.guess_type(path.name)
        return mime or "application/octet-stream"
    return "application/json"


# ── Authenticated endpoints ─────────────────────────────────────────────────

@bp.route("/api/shares", methods=["POST"])
@login_required
@require_permission("workspace", "manage")
def create_share():
    """Create a new public share link for a workspace file."""
    data = request.get_json(silent=True) or {}
    path = data.get("path", "").strip()
    expires_in = data.get("expires_in", "7d")  # e.g. "1h", "24h", "7d", "30d", null

    if not path:
        return jsonify({"error": "path is required", "code": "bad_path"}), 400

    # Validate path resolves to a real file inside WORKSPACE_DIR
    full = _resolve_path_safe(path)
    if full is None:
        return jsonify({"error": "Invalid or disallowed path", "code": "bad_path"}), 400
    if not full.exists() or not full.is_file():
        return jsonify({"error": "File not found", "code": "not_found"}), 404

    # Enforce folder access before creating a share
    if not has_workspace_folder_access(current_user.role, path):
        return jsonify({"error": "Access to this workspace folder is restricted", "code": "forbidden"}), 403

    # Calculate expiry
    expires_at = None
    if expires_in and expires_in in _EXPIRY_MAP:
        expires_at = datetime.now(timezone.utc) + _EXPIRY_MAP[expires_in]

    token = secrets.token_urlsafe(32)
    share = FileShare(
        token=token,
        path=path,
        created_by_id=current_user.id,
        expires_at=expires_at,
    )
    db.session.add(share)
    db.session.commit()

    audit(current_user, "share_create", "shares", detail=f"path={path} expiry={expires_in}")

    base_url = _public_base_url()
    return jsonify({
        "token": token,
        "path": path,
        "url": f"{base_url}/share/{token}",
        "expires_at": share.expires_at.strftime("%Y-%m-%dT%H:%M:%S.%fZ") if share.expires_at else None,
        "created_at": share.created_at.strftime("%Y-%m-%dT%H:%M:%S.%fZ") if share.created_at else None,
    }), 201


@bp.route("/api/shares", methods=["GET"])
@login_required
@require_permission("workspace", "manage")
def list_shares():
    """List all share links."""
    shares = FileShare.query.order_by(FileShare.created_at.desc()).all()
    return jsonify({"shares": [s.to_dict() for s in shares]})


@bp.route("/api/shares/by-path", methods=["GET"])
@login_required
@require_permission("workspace", "manage")
def get_active_share_by_path():
    """Return the most recent ACTIVE (enabled + not expired) share for a path,
    so the UI can reuse it instead of generating a new token every time."""
    path = (request.args.get("path") or "").strip()
    if not path:
        return jsonify({"error": "path is required", "code": "bad_path"}), 400

    if not has_workspace_folder_access(current_user.role, path):
        return jsonify({"error": "Access to this workspace folder is restricted", "code": "forbidden"}), 403

    now = datetime.now(timezone.utc)
    candidates = (
        FileShare.query
        .filter_by(path=path, enabled=True)
        .order_by(FileShare.created_at.desc())
        .all()
    )
    for share in candidates:
        if share.expires_at is not None:
            expires = share.expires_at
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            if now > expires:
                continue
        base_url = _public_base_url()
        return jsonify({
            **share.to_dict(),
            "url": f"{base_url}/share/{share.token}",
        })
    return jsonify({"error": "No active share for this path", "code": "not_found"}), 404


@bp.route("/api/shares/<token>", methods=["DELETE"])
@login_required
@require_permission("workspace", "manage")
def revoke_share(token: str):
    """Revoke a share link (set enabled=False)."""
    share = FileShare.query.filter_by(token=token).first()
    if not share:
        return jsonify({"error": "Share not found", "code": "not_found"}), 404

    share.enabled = False
    db.session.commit()

    audit(current_user, "share_revoke", "shares", detail=f"token={token} path={share.path}")
    return jsonify({"ok": True, "token": token})


# ── Public endpoint (no auth required) ──────────────────────────────────────

@bp.route("/api/shares/<token>/view", methods=["GET"])
@limiter.limit("60 per minute")
def view_share(token: str):
    """Serve the file content for a valid share token. No authentication required."""
    share = FileShare.query.filter_by(token=token).first()

    if not share or not share.enabled:
        return jsonify({"error": "Link inválido ou expirado", "code": "not_found"}), 404

    # Check expiry
    if share.expires_at:
        now = datetime.now(timezone.utc)
        expires = share.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if now > expires:
            return jsonify({"error": "Link inválido ou expirado", "code": "expired"}), 404

    # Resolve path without current_user dependency
    full = _resolve_path_safe(share.path)
    if full is None or not full.exists() or not full.is_file():
        return jsonify({"error": "Arquivo não encontrado", "code": "not_found"}), 404

    # Increment view count
    share.view_count = (share.view_count or 0) + 1
    db.session.commit()

    # Log the view (user=None for anonymous)
    ip = request.remote_addr or "-"
    ua = (request.headers.get("User-Agent", "-") or "-")[:200]
    audit(None, "share_view", "shares", detail=f"token={token} ip={ip} ua={ua[:80]}")

    # Vault §2.S2: security headers on all public share responses.
    @after_this_request
    def _add_security_headers(response):
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store, private, no-cache, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        return response

    suffix = full.suffix.lower()

    # HTML/HTM: serve raw so browser renders it as a full page
    if suffix in (".html", ".htm"):
        content = full.read_bytes()
        response = Response(content, mimetype="text/html; charset=utf-8")
        # `_resolve_path_safe` já impede path traversal; o problema aqui é
        # outro: este HTML executa na MESMA origem do dashboard. E
        # `.claude/rules/artifacts.md` institucionaliza a rota — todo relatório
        # de agente é HTML publicado por aqui. Um agente com prompt injetado
        # grava um <script> no relatório, o superadmin abre o link logado, e o
        # script faz fetch('/api/...') com a sessão dele. HttpOnly não protege:
        # o script não precisa ler o cookie, só que o navegador o envie.
        #
        # `sandbox` dá origem opaca e mata script e form. Os dois tokens que
        # sobram devolvem só o que um relatório precisa e nenhum script pode
        # usar sozinho: abrir um link em nova aba, e navegar quando o clique
        # partiu do usuário. Sem eles, todo link do relatório vira texto morto.
        #
        # O resto é exatamente o que a rule de artefatos já exige de um share:
        # arquivo único, CSS inline, imagem em data:.
        response.headers["Content-Security-Policy"] = (
            "sandbox allow-popups allow-popups-to-escape-sandbox "
            "allow-top-navigation-by-user-activation; "
            "default-src 'none'; style-src 'unsafe-inline'; "
            "img-src data:; font-src data:"
        )
        return response

    # Images: serve binary with correct MIME type
    if suffix in _IMAGE_EXTS:
        mime, _ = mimetypes.guess_type(full.name)
        content = full.read_bytes()
        return Response(content, mimetype=mime or "application/octet-stream")

    # Video: serve binary with correct MIME type
    if suffix in _VIDEO_EXTS:
        return send_file(full, mimetype="video/mp4", conditional=True)

    # Audio: serve binary with correct MIME type
    if suffix in _AUDIO_EXTS:
        mime, _ = mimetypes.guess_type(full.name)
        content = full.read_bytes()
        return Response(content, mimetype=mime or "audio/mpeg")

    # PDF: serve binary
    if suffix in _PDF_EXTS:
        content = full.read_bytes()
        return Response(content, mimetype="application/pdf")

    # Markdown: return as JSON for frontend rendering
    if suffix in (".md", ".markdown"):
        try:
            content = full.read_text("utf-8")
        except (UnicodeDecodeError, OSError):
            return jsonify({"error": "Erro ao ler arquivo", "code": "read_error"}), 500
        return jsonify({"content": content, "type": "markdown", "path": share.path})

    # Code files: return as JSON with type=code
    if suffix in _CODE_EXTS:
        try:
            content = full.read_text("utf-8")
        except (UnicodeDecodeError, OSError):
            return jsonify({"error": "Erro ao ler arquivo", "code": "read_error"}), 500
        return jsonify({"content": content, "type": "code", "path": share.path, "extension": suffix.lstrip(".")})

    # Default: try to read as text
    try:
        content = full.read_text("utf-8")
        return jsonify({"content": content, "type": "text", "path": share.path})
    except UnicodeDecodeError:
        # Binary file — not shareable in v1
        return jsonify({"error": "Arquivo binário não suportado", "code": "unsupported"}), 415


# CTA de artefato compartilhado clica aqui, não direto no destino. Existe
# porque a rota /view tem CSP `default-src 'none'` (ver comentário acima,
# §prompt injection) — qualquer fetch() de JS embutido no artefato seria
# bloqueado, e o próprio motivo do bloqueio (script de agente com prompt
# injetado lendo a sessão do superadmin) não pode ser afrouxado só pra medir
# clique. Um <a href> puro, sem JS nenhum, contorna isso: o navegador segue
# link normal, o clique é registrado no servidor antes do redirect.
#
# `to` é validado contra um allowlist de host, não é passe livre — sem isso
# esta rota seria um open redirect a partir de um domínio confiável
# (nexus.workflowapi.com.br), útil demais pra phishing pra deixar aberto.
_CLICK_REDIRECT_ALLOWED_HOSTS = {
    "sistemabritto.com.br",
    "www.sistemabritto.com.br",
    "blog.sistemabritto.com.br",
}


@bp.route("/api/shares/<token>/click", methods=["GET"])
@limiter.limit("60 per minute")
def click_share(token: str):
    """Registra o clique de CTA de um artefato público e redireciona.

    Sem autenticação de propósito, pela mesma razão de /view: quem lê o
    artefato é anônimo. `token` só precisa existir (não precisa estar
    habilitado — um share revogado ainda pode ter cliques em cache de
    página que valem registrar, e recusar aqui não desfaz o clique).
    """
    share = FileShare.query.filter_by(token=token).first()
    if not share:
        return jsonify({"error": "Link inválido", "code": "not_found"}), 404

    destino = request.args.get("to", "")
    rotulo = (request.args.get("label") or "")[:200]
    partes = urlparse(destino)
    if partes.scheme != "https" or partes.netloc not in _CLICK_REDIRECT_ALLOWED_HOSTS:
        return jsonify({"error": "Destino não permitido", "code": "invalid_target"}), 400

    evento = ShareEvent(token=token, event_type="cta_click", meta=rotulo or destino[:200])
    db.session.add(evento)
    db.session.commit()

    return redirect(destino, code=302)


@bp.route("/api/shares/<token>/events", methods=["GET"])
@login_required
@require_permission("workspace", "manage")
def list_share_events(token: str):
    """Eventos de clique registrados para um artefato — para conferir conversão."""
    share = FileShare.query.filter_by(token=token).first()
    if not share:
        return jsonify({"error": "Link inválido", "code": "not_found"}), 404
    eventos = (ShareEvent.query.filter_by(token=token)
               .order_by(ShareEvent.created_at.desc()).limit(500).all())
    return jsonify({
        "token": token,
        "path": share.path,
        "view_count": share.view_count,
        "click_count": len(eventos),
        "events": [e.to_dict() for e in eventos],
    })
