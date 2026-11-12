"""Offline editorial planning for existing MediaJobs; never submits or publishes.

A plan is evidence for human review, not an approval or an edit engine. Times
are seconds. v1 keeps chronological, normal-speed source intervals only.
"""
from __future__ import annotations

import math
from pathlib import PurePosixPath


class EditorialPlanError(ValueError):
    pass


WORKFLOWS = {
    "faceless_montage": {
        "entry_job_type": "social_clip",
        "stages": ["social_clip", "ready_for_review", "approve", "create-draft", "schedule"],
        "reference": "references/faceless.md",
    },
    "personal_footage": {
        "entry_job_type": "corte_bruto",
        "stages": ["corte_bruto", "corte_editorial", "aplicar_corte_editorial", "cortes_virais",
                   "ready_for_review", "approve", "create-draft", "schedule"],
        "reference": "references/personal-footage.md",
    },
}


def _number(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise EditorialPlanError(f"{name}: número finito obrigatório")
    return float(value)


def _object(value, name):
    if not isinstance(value, dict):
        raise EditorialPlanError(f"{name}: objeto obrigatório")
    return value


def _list(value, name):
    if not isinstance(value, list):
        raise EditorialPlanError(f"{name}: lista obrigatória")
    return value


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise EditorialPlanError(f"{name}: texto obrigatório")
    return value


def _relative(value):
    path = _text(value, "asset.path")
    parsed = PurePosixPath(path)
    if parsed.is_absolute() or ".." in parsed.parts or "\\" in path or ":" in path:
        raise EditorialPlanError("asset.path deve ser relativo ao workspace autorizado")
    return path


def source_to_edited(time_map, timestamp):
    """None means removed. Cut intervals are half-open; no speed/reorder guessing."""
    timestamp = _number(timestamp, "timestamp")
    for segment in time_map:
        if segment["source_start"] <= timestamp < segment["source_end"]:
            return segment["edited_start"] + timestamp - segment["source_start"]
    return None


def build_editorial_plan(payload):
    data = _object(payload, "request")
    mode = data.get("mode")
    if not isinstance(mode, str) or mode not in WORKFLOWS:
        raise EditorialPlanError("mode: faceless_montage ou personal_footage obrigatório; não inferir")
    title = _text(data.get("title"), "title")
    duration = _number(data.get("source_duration_seconds"), "source_duration_seconds")
    if duration <= 0:
        raise EditorialPlanError("source_duration_seconds deve ser positivo")
    revision = data.get("revision", 1)
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
        raise EditorialPlanError("revision deve ser inteiro positivo")
    previous = data.get("previous_revision")
    if revision > 1 and (not isinstance(previous, int) or isinstance(previous, bool) or previous != revision - 1):
        raise EditorialPlanError("preservar previous_revision antes de revisar")

    assets = _list(data.get("assets"), "assets")
    by_id = {}
    for asset in assets:
        asset = _object(asset, "asset")
        asset_id = _text(asset.get("id"), "asset.id")
        if asset_id in by_id:
            raise EditorialPlanError("asset.id duplicado")
        _relative(asset.get("path"))
        if asset.get("kind") not in ("photo", "illustration", "footage", "meme", "audio", "font", "logo"):
            raise EditorialPlanError("asset.kind não suportado")
        if asset.get("rights") not in ("owned", "licensed", "permission"):
            raise EditorialPlanError("material sem autorização não pode entrar no plano")
        _text(asset.get("rights_evidence"), "asset.rights_evidence")
        by_id[asset_id] = asset
    if not assets:
        raise EditorialPlanError("forneça material autorizado; não buscar mídia automaticamente")
    if mode == "faceless_montage" and not any(asset["kind"] in ("photo", "illustration", "footage", "meme")
                                             for asset in assets):
        raise EditorialPlanError("faceless_montage exige material visual autorizado")
    source_id = data.get("source_asset")
    if source_id is not None and not isinstance(source_id, str):
        raise EditorialPlanError("source_asset deve ser um asset.id")
    source = by_id.get(source_id)
    if mode == "personal_footage" and (not source or source.get("kind") != "footage"):
        raise EditorialPlanError("personal_footage exige source_asset de footage autorizado")

    words = _list(data.get("words", []), "words")
    previous_end = 0.0
    for word in words:
        word = _object(word, "word")
        _text(word.get("word"), "word.word")
        start, end = _number(word.get("start"), "word.start"), _number(word.get("end"), "word.end")
        if not previous_end <= start < end <= duration:
            raise EditorialPlanError("palavras devem estar ordenadas dentro da duração da fonte")
        previous_end = end
    glossary = _object(data.get("glossary", {}), "glossary")
    if not all(isinstance(key, str) and isinstance(value, str) for key, value in glossary.items()):
        raise EditorialPlanError("glossary deve mapear grafias para marcas/termos corretos")

    transcription = _object(data.get("transcription", {"engine": "provided"}), "transcription")
    if transcription.get("engine") not in ("provided", "whisper_local"):
        raise EditorialPlanError("transcription exige supplied words ou whisper_local explícito; sem envio de áudio")
    if transcription.get("engine") == "whisper_local":
        model = _text(transcription.get("model"), "transcription.model multilíngue")
        if model.endswith(".en"):
            raise EditorialPlanError("selecione modelo Whisper multilíngue para este fluxo")
    face_box = data.get("face_box")
    if face_box is not None:
        face_box = _object(face_box, "face_box")
        x, y, width, height = [_number(face_box.get(key), "face_box." + key)
                               for key in ("x", "y", "width", "height")]
        if not (0 <= x < 1 and 0 <= y < 1 and width > 0 and height > 0
                and x + width <= 1 and y + height <= 1):
            raise EditorialPlanError("face_box deve estar normalizada dentro do frame; não há tracking")

    cuts = _list(data.get("keep", [{"start": 0, "end": duration}]), "keep")
    time_map, captions, cursor, previous_end = [], [], 0.0, 0.0
    for cut in cuts:
        cut = _object(cut, "keep item")
        start, end = _number(cut.get("start"), "keep.start"), _number(cut.get("end"), "keep.end")
        if not previous_end <= start < end <= duration:
            raise EditorialPlanError("keep exige intervalos cronológicos sem sobreposição e dentro da fonte")
        segment = {"source_start": start, "source_end": end, "edited_start": cursor,
                   "edited_end": cursor + end - start}
        time_map.append(segment)
        for word in words:
            if word["start"] < end and word["end"] > start:
                if word["start"] < start or word["end"] > end:
                    raise EditorialPlanError(f"corte divide palavra: {word['word']}")
                captions.append({"word": glossary.get(word["word"], word["word"]),
                                 "start": cursor + word["start"] - start,
                                 "end": cursor + word["end"] - start})
        cursor += end - start
        previous_end = end
    if not time_map:
        raise EditorialPlanError("keep não pode remover todo o vídeo")

    beats = _list(data.get("beats"), "beats")
    if not beats:
        raise EditorialPlanError("beat sheet obrigatório para revisão antes de editar")
    for beat in beats:
        beat = _object(beat, "beat")
        start, end = _number(beat.get("start"), "beat.start"), _number(beat.get("end"), "beat.end")
        if not 0 <= start < end <= cursor:
            raise EditorialPlanError("beat fora da timeline editada")
        _text(beat.get("speech"), "beat.speech (ou indicação sem fala)")
        _text(beat.get("sound"), "beat.sound (ou silêncio)")
        for element in _list(beat.get("elements"), "beat.elements"):
            element = _object(element, "element")
            _text(element.get("kind"), "element.kind")
            _text(element.get("position"), "element.position")
            if element.get("asset") is not None and (not isinstance(element["asset"], str)
                                                      or element["asset"] not in by_id):
                raise EditorialPlanError("elemento referencia material não autorizado")
            anchor = element.get("word_index")
            if anchor is not None and (isinstance(anchor, bool) or not isinstance(anchor, int)
                                       or not 0 <= anchor < len(captions)
                                       or not start <= captions[anchor]["start"] < end):
                raise EditorialPlanError("efeito deve se ligar a palavra mantida dentro do beat")
            if element["kind"] == "transition":
                effect_start = _number(element.get("start", start), "transition.start")
                effect_end = _number(element.get("end", end), "transition.end")
                if not start <= effect_start < effect_end <= end:
                    raise EditorialPlanError("transição fora do beat")
                if any(word["start"] < boundary < word["end"]
                       for boundary in (effect_start, effect_end) for word in captions):
                    raise EditorialPlanError("transição divide palavra mantida")

    return {
        "schema_version": 1, "mode": mode, "title": title, "revision": revision,
        "previous_revision": previous, "workflow": WORKFLOWS[mode],
        "skill": "video-editorial-pipeline", "agents": {
            "editorial": "pixel-social-media", "implementation": "bolt-executor",
            "qa": "probe-qa", "human_review": "Felipe",
        },
        "assets": assets, "time_map": time_map, "captions": captions, "beats": beats,
        "time_map_scope": {"source_asset": source_id, "revision": revision,
                           "refresh_after_any_additional_cut": True},
        "transcription": transcription, "face_box": face_box, "face_tracking": False,
        "frame_sampling": {"strategy": "uniform_across_source", "max_frames": 80},
        "edited_duration_seconds": cursor, "state": "awaiting_beat_sheet_review",
        "next_action": "Apresentar beat sheet ao Felipe; não criar job nem editar automaticamente.",
        "qa_required": ["audio", "captions", "face", "safe_zones", "rights", "overlap", "transparency"],
        "artifacts_required": ["word_transcript.json", "frames/", "rough_cut", "short_preview",
                               "snapshots/", "timestamped_review", "previous_revision"],
        "release_gates": ["felipe_beat_sheet_approval", "rough_cut_review", "qa_review",
                          "felipe_final_approval", "destination_and_schedule_authorization"],
        "execution_limits": {
            "auto_queue": False, "auto_schedule": False, "paid_generation": False,
            "retiming": "normal_speed_chronological_only",
            "personal_effects": "manual_handoff; existing corte_bruto does not apply color/memes",
        },
    }
