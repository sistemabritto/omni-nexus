"""Strict, path-free manual video trim decisions shared by API and worker."""
import math


def video_trim(value):
    if not isinstance(value, dict) or set(value) - {'start_seconds', 'end_seconds'}:
        raise ValueError('invalid_video_trim')
    start = value.get('start_seconds', 0)
    end = value.get('end_seconds')
    for number in (start, end):
        if number is None:continue
        if isinstance(number, bool) or not isinstance(number, (int, float)):
            raise ValueError('invalid_video_trim')
        try: finite = math.isfinite(number)
        except OverflowError: finite = False
        if not finite:raise ValueError('invalid_video_trim')
    if start is None or start < 0 or (end is not None and end <= start):
        raise ValueError('invalid_video_trim')
    return {'start_seconds': float(start), 'end_seconds': float(end) if end is not None else None}


def edit_decisions(value, selected):
    if not isinstance(value, dict) or not set(value).issubset(selected):
        raise ValueError('invalid_edit_assets')
    return {key: video_trim(trim) for key, trim in value.items()}
