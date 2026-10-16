"""Offline project contract. Composition inputs, never generation/spend/approval."""
import math
import re

ENTRY_MODES={'long_cuts','enriched_edit','faceless','stickman','motion_vsl'}
KINDS={'footage','image','motion','stickman'}


def number(value, minimum, maximum):
    if isinstance(value,bool) or not isinstance(value,(int,float)):
        raise ValueError('finite_number_required')
    try: valid=math.isfinite(value) and minimum<=value<=maximum
    except OverflowError: valid=False
    if not valid:raise ValueError('number_out_of_bounds')
    return float(value)


def text(value,maximum=2000):
    if not isinstance(value,str) or not value.strip() or len(value)>maximum:raise ValueError('text_required')
    return value.strip()


def normalize_project(value, assets):
    if not isinstance(value,dict) or set(value)-{'entry_modes','script','brand_reference','palette','scenes','captions','audio_upload_id','audio_policy'}:
        raise ValueError('invalid_production_spec')
    modes=value.get('entry_modes')
    if not isinstance(modes,list) or not modes or not all(isinstance(mode,str) and mode in ENTRY_MODES for mode in modes) or len(set(modes))!=len(modes):raise ValueError('invalid_entry_modes')
    palette=value.get('palette',{'background':'#0d1117','foreground':'#e6edf3','accent':'#58a6ff'})
    if not isinstance(palette,dict) or set(palette)!={'background','foreground','accent'} or any(not isinstance(c,str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',c) for c in palette.values()):raise ValueError('invalid_palette')
    scenes=value.get('scenes')
    if not isinstance(scenes,list) or not 1<=len(scenes)<=200:raise ValueError('invalid_scenes')
    normalized=[];cursor=0.0
    for scene in scenes:
        if not isinstance(scene,dict) or set(scene)-{'kind','duration','title','text','show_title','asset_id','source_start','frame','grade','pose','metric','metric_source','overlay_asset_id','overlay_rights_reference','rights_reference','selection'}:raise ValueError('invalid_scene')
        kind=scene.get('kind')
        if not isinstance(kind,str) or kind not in KINDS:raise ValueError('invalid_scene_kind')
        body=scene.get('text','')
        if not isinstance(body,str) or len(body)>1600:raise ValueError('invalid_scene_text')
        duration=number(scene.get('duration'),.1,300)
        item={'kind':kind,'duration':duration,'start':cursor,'title':text(scene.get('title'),180),'text':body.strip()}
        item['show_title']=scene.get('show_title',kind not in ('footage','image'))
        if not isinstance(item['show_title'],bool):raise ValueError('invalid_show_title')
        for key,allowed,default in [('frame',{'contain','cover'},'contain'),('grade',{'none','warm','cool'},'none'),('pose',{'wave','walk','explain'},'explain')]:
            item[key]=scene.get(key,default)
            if not isinstance(item[key],str) or item[key] not in allowed:raise ValueError('invalid_'+key)
        if kind in ('footage','image'):
            if not isinstance(scene.get('asset_id'),str):raise ValueError('scene_asset_type_or_access')
            asset=assets.get(scene.get('asset_id'))
            if not asset or asset['kind']!=('video' if kind=='footage' else 'image'):raise ValueError('scene_asset_type_or_access')
            item['asset_id']=asset['id'];item['rights_reference']=text(scene.get('rights_reference'),1000)
            if kind=='footage':item['source_start']=number(scene.get('source_start',0),0,86400)
        if 'overlay_asset_id' in scene:
            if not isinstance(scene['overlay_asset_id'],str):raise ValueError('overlay_requires_authorized_image')
            overlay=assets.get(scene['overlay_asset_id'])
            if not overlay or overlay['kind']!='image':raise ValueError('overlay_requires_authorized_image')
            item['overlay_asset_id']=overlay['id'];item['overlay_rights_reference']=text(scene.get('overlay_rights_reference'),1000)
        if 'metric' in scene:
            item['metric']=number(scene['metric'],0,100);item['metric_source']=text(scene.get('metric_source'),1000)
        if 'long_cuts' in modes and kind=='footage':
            selection=scene.get('selection')
            if not isinstance(selection,dict) or set(selection)!={'rationale','transcript_excerpt','source_reference'}:raise ValueError('semantic_selection_evidence_required')
            item['selection']={k:text(selection[k]) for k in selection}
        normalized.append(item);cursor+=duration
    if cursor>3600:raise ValueError('project_exceeds_one_hour')
    kinds={scene['kind'] for scene in normalized}
    if 'stickman' in modes and 'stickman' not in kinds:raise ValueError('stickman_scene_required')
    if 'long_cuts' in modes and 'footage' not in kinds:raise ValueError('long_cuts_footage_required')
    if 'enriched_edit' in modes and not kinds.intersection({'footage','image'}):raise ValueError('enriched_edit_material_required')
    if set(modes).intersection({'faceless','motion_vsl'}) and not kinds.intersection({'motion','stickman','image'}):raise ValueError('generated_scene_required')
    captions=value.get('captions',[])
    if not isinstance(captions,list) or len(captions)>1000:raise ValueError('invalid_captions')
    normalized_captions=[]
    for caption in captions:
        if not isinstance(caption,dict) or set(caption)!={'start','end','text'}:raise ValueError('invalid_caption')
        start=number(caption['start'],0,cursor);end=number(caption['end'],0,cursor)
        if end<=start:raise ValueError('invalid_caption_interval')
        normalized_captions.append({'start':start,'end':end,'text':text(caption['text'],160)})
    policy=value.get('audio_policy')
    if not isinstance(policy,str) or policy not in ('silent','source','provided'):raise ValueError('explicit_audio_policy_required')
    audio=value.get('audio_upload_id')
    if policy=='provided' and (not isinstance(audio,str) or audio not in assets or assets[audio]['kind']!='audio'):raise ValueError('provided_audio_required')
    if policy!='provided' and audio is not None:raise ValueError('unexpected_audio_asset')
    if policy=='source' and not any(s['kind']=='footage' for s in normalized):raise ValueError('source_audio_requires_footage')
    brand=text(value.get('brand_reference'),1000)
    if '@' not in brand or any(not part for part in brand.rsplit('@',1)):raise ValueError('brand_source_and_version_required')
    return {'schema_version':1,'entry_modes':modes,'script':text(value.get('script'),100000),'brand_reference':brand,
            'palette':palette,'scenes':normalized,'captions':normalized_captions,'duration':cursor,'audio_policy':policy,'audio_upload_id':audio}
