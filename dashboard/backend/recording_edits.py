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
    result={}
    for key,trim in value.items():
        segments=video_segments(trim)
        result[key]={'keep_segments':segments} if isinstance(trim,dict) and 'keep_segments' in trim else segments[0]
    if sum(len(video_segments(trim)) for trim in result.values())>200:raise ValueError('too_many_segments')
    return result


def video_segments(value):
    """Legacy single trim or ordered non-overlapping kept intervals (no source paths)."""
    if not isinstance(value, dict) or 'keep_segments' not in value:
        return [video_trim(value)]
    segments=value['keep_segments']
    if set(value)!={'keep_segments'} or not isinstance(segments,list) or not 1<=len(segments)<=20:
        raise ValueError('invalid_keep_segments')
    normalized=[video_trim(segment) for segment in segments]
    for previous,current in zip(normalized,normalized[1:]):
        if previous['end_seconds'] is None or current['start_seconds']<previous['end_seconds']:
            raise ValueError('keep_segments_must_be_ordered_without_overlap')
    return normalized
