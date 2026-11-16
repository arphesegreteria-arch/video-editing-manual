from __future__ import annotations

from typing import Any
from pathlib import Path
from fractions import Fraction

from .safety import ValidationError
from .safety import allowed_asset
from .feature_flags import require_capability
from .still_media import validate_still_appearance, prepare_presented_still, prepare_still_video
from .longform_tools import allowed_media, import_media_item
from .resolve_connection import safe_call


def is_still_asset(path: str) -> bool:
    return Path(path).suffix.lower() in {'.jpg','.jpeg','.png','.webp','.tif','.tiff'}


def _range(raw: object, label: str, maximum: int) -> tuple[int, int]:
    if not isinstance(raw, dict):
        raise ValidationError(f"range {label} mancante")
    start, end = raw.get("start_frame"), raw.get("end_frame")
    if not isinstance(start, int) or not isinstance(end, int) or not 0 <= start < end <= maximum:
        raise ValidationError(f"range {label} non valido")
    return start, end


def validate_provided_broll(action: dict[str, Any], total_frames: int) -> dict[str, Any]:
    if action.get("type") != "B_ROLL_PROVIDED" or action.get("state") != "APPROVED":
        raise ValidationError("B-roll fornito non approvato")
    if not isinstance(total_frames, int) or total_frames <= 0:
        raise ValidationError("durata timeline non valida")
    asset = str(action.get("asset_path", "")).strip()
    if not asset:
        raise ValidationError("asset B-roll fornito mancante")
    if not str(action.get("reason", "")).strip():
        raise ValidationError("reason B-roll mancante")
    timeline_range = _range(action.get("timeline_range"), "timeline B-roll", total_frames)
    source_range = _range(action.get("source_range"), "sorgente B-roll", 10**9)
    if timeline_range[1] - timeline_range[0] != source_range[1] - source_range[0]:
        raise ValidationError("durata B-roll sorgente/timeline diversa")
    appearance = action.get("appearance")
    image = is_still_asset(asset)
    if appearance is not None:
        if not image: raise ValidationError('Aspetto B-roll animato supportato solo per immagini')
        appearance = validate_still_appearance(appearance, timeline_range[1]-timeline_range[0])
    if image and source_range[0] != 0:
        raise ValidationError('Range sorgente immagini deve iniziare da zero')
    return {"asset_path": asset, "timeline_range": timeline_range, "source_range": source_range,
            "image": image, "appearance": appearance}


def _apply_still_broll(project: object, timeline: object, config: Any, plan: dict) -> dict:
    require_capability('CAP_ASSETS', config, None, project, timeline)
    if plan['appearance'] is not None:
        require_capability('CAP_MOTION', config, None, project, timeline)
    asset = allowed_asset(plan['asset_path'], (config.asset_root, *getattr(config,'media_roots',())), 'image')
    start, end = plan['timeline_range']; duration = end-start
    fps = Fraction(str(safe_call(timeline,'GetSetting','timelineFrameRate')))
    if plan['appearance'] is None:
        path = prepare_still_video(asset, config.asset_root, fps, duration)
    else:
        width = int(safe_call(timeline,'GetSetting','timelineResolutionWidth'))
        height = int(safe_call(timeline,'GetSetting','timelineResolutionHeight'))
        path = prepare_presented_still(asset,config.asset_root,fps,duration,width,height,plan['appearance'])
    pool = safe_call(project,'GetMediaPool')
    imported = safe_call(pool,'ImportMedia',[str(path)])
    if not isinstance(imported,(list,tuple)) or len(imported)!=1:
        raise ValidationError('Import overlay immagine fallito')
    origin = safe_call(timeline,'GetStartFrame')
    previous = safe_call(timeline,'GetTrackCount','video')
    if isinstance(origin,bool) or not isinstance(origin,int) or isinstance(previous,bool) or not isinstance(previous,int):
        raise ValidationError('Contesto timeline immagine non verificabile')
    if safe_call(timeline,'AddTrack','video') is not True:
        raise ValidationError('Creazione traccia immagine fallita')
    track = previous+1
    inserted = []
    def rollback():
        deleted = not inserted or safe_call(timeline,'DeleteClips',inserted,False) is True
        removed = safe_call(timeline,'DeleteTrack','video',track) is True
        if not deleted or not removed: raise ValidationError('Rollback immagine B-roll incompleto')
    try:
        if safe_call(timeline,'GetTrackCount','video') != track:
            raise ValidationError('Traccia immagine non verificata')
        absolute_start, absolute_end = origin+start, origin+end
        def append(source_end):
            result = safe_call(pool,'AppendToTimeline',[{'mediaPoolItem':imported[0],
                'startFrame':0,'endFrame':source_end,'recordFrame':absolute_start,
                'mediaType':1,'trackIndex':track}])
            if isinstance(result,(list,tuple)): inserted.extend(result)
            if not isinstance(result,(list,tuple)) or len(result)!=1:
                raise ValidationError('Inserimento immagine B-roll non univoco')
            return result[0]
        item = append(duration)
        actual_start, actual_end = safe_call(item,'GetStart'), safe_call(item,'GetEnd')
        if actual_start==absolute_start and isinstance(actual_end,(int,float)) and abs(actual_end-absolute_end)==1:
            if safe_call(timeline,'DeleteClips',[item],False) is not True:
                raise ValidationError('Rollback adattamento frame immagine fallito')
            inserted.clear()
            item = append(duration+absolute_end-actual_end)
        if safe_call(item,'GetStart')!=absolute_start or safe_call(item,'GetEnd')!=absolute_end:
            raise ValidationError('Range immagine B-roll non corrispondente')
        return {'ok':True,'timeline':safe_call(timeline,'GetName'),'track_index':track,
                'timeline_range':[start,end],'source_range':list(plan['source_range']),
                'absolute_frame_range':[absolute_start,absolute_end],
                'asset_name':asset.name,'appearance':plan['appearance']}
    except Exception:
        rollback()
        raise


def validate_generated_broll(action: dict[str, Any]) -> None:
    del action
    raise ValidationError("B-roll generato bloccato: provider e approvazione locale richiesti")


def apply_provided_broll(resolve: object, project: object, timeline: object, config: Any,
                         action: dict[str, Any], total_frames: int) -> dict[str, Any]:
    """Insert an approved, allowlisted B-roll clip only on the selected provisional timeline."""
    plan = validate_provided_broll(action, total_frames)
    name = str(safe_call(timeline, "GetName") or "")
    if not name.startswith("__ARPHE_VERTICAL_"):
        raise ValidationError("B-roll consentito solo sulla timeline provvisoria Vertical Social")
    if plan['image']:
        return _apply_still_broll(project,timeline,config,plan)
    asset = allowed_media(plan["asset_path"], config)
    pool = safe_call(project, "GetMediaPool")
    media = import_media_item(resolve, pool, asset) if pool else None
    if media is None:
        raise ValidationError("Import B-roll fornito fallito")
    start, end = plan["timeline_range"]
    source_start, source_end = plan["source_range"]
    if not safe_call(timeline, "AddTrack", "video"):
        raise ValidationError("Creazione traccia B-roll fallita")
    track = int(safe_call(timeline, "GetTrackCount", "video") or 0)
    origin = safe_call(timeline, "GetStartFrame")
    if isinstance(origin, bool) or not isinstance(origin, int):
        raise ValidationError("Origine timeline B-roll non verificabile")
    appended = safe_call(pool, "AppendToTimeline", [{"mediaPoolItem": media, "startFrame": source_start,
                                                        "endFrame": source_end, "recordFrame": origin + start,
                                                        "mediaType": 1, "trackIndex": track}]) or []
    if len(appended) != 1 or int(safe_call(appended[0], "GetDuration") or 0) != end - start:
        raise ValidationError("Read-back B-roll non corrisponde al piano")
    return {"ok": True, "timeline": name, "track_index": track,
            "timeline_range": [start, end], "source_range": [source_start, source_end]}
