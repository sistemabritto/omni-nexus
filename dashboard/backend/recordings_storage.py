"""Private, resumable local media storage. No remote fetching or transcription."""
import hashlib
import os
import uuid
from pathlib import Path
from media_workspace import media_workspace_root

CHUNK_BYTES = 4 * 1024 * 1024
EXTENSIONS = {'.mp4':'video/mp4','.mov':'video/quicktime','.webm':'video/webm',
              '.m4v':'video/mp4','.jpg':'image/jpeg','.jpeg':'image/jpeg','.png':'image/png',
              '.webp':'image/webp','.mp3':'audio/mpeg','.wav':'audio/wav','.m4a':'audio/mp4','.ogg':'audio/ogg'}


def private_path(relative):
    root = media_workspace_root() / 'recordings'
    path = (media_workspace_root() / relative).resolve()
    if root not in path.parents:
        raise ValueError('invalid_storage_path')
    return path


def atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.part')
    try:
        with temporary.open('wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def media_kind(name, supplied_mime=None):
    ext = Path(name).suffix.lower()
    if ext not in EXTENSIONS:
        raise ValueError('unsupported_media_extension')
    mime = EXTENSIONS[ext]
    if ext == '.webm' and (supplied_mime or '').startswith('audio/webm'):
        mime = 'audio/webm'
    return mime.split('/')[0], mime, ext


def valid_signature(path):
    with path.open('rb') as stream:
        head = stream.read(32)
    return (head.startswith((b'\xff\xd8\xff',b'\x89PNG\r\n\x1a\n',b'\x1aE\xdf\xa3',b'OggS',b'ID3'))
            or head[4:8] == b'ftyp' or (head.startswith(b'RIFF') and head[8:12] in (b'WEBP',b'WAVE'))
            or (len(head)>1 and head[0]==255 and head[1]&224==224))


def hash_file(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(CHUNK_BYTES), b''):
            result.update(chunk)
    return result.hexdigest()
