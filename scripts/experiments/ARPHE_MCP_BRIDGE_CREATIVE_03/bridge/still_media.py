"""Lossless, duration-controlled carriers for approved still images.

The caller validates the source against the existing asset allowlist.  Resolve
ignores AppendToTimeline source trims on stills; a real movie avoids its default
still duration without changing project preferences or weakening range checks.
"""
from fractions import Fraction
from pathlib import Path
import os
import math
from uuid import uuid4

import av
import numpy as np

from .safety import ValidationError


def validate_still_geometry(source_width: int, source_height: int, width: int, height: int,
                             maximum_zoom: float) -> float:
    limit = 16_777_216
    if source_width <= 0 or source_height <= 0 or source_width*source_height > limit:
        raise ValidationError('Dimensioni sorgente immagine fuori limite')
    cover = max(width/source_width,height/source_height)
    if math.ceil(source_width*cover*maximum_zoom)*math.ceil(source_height*cover*maximum_zoom) > limit:
        raise ValidationError('Immagine intermedia fuori limite di memoria')
    return cover


def validate_still_appearance(raw: dict, frames: int) -> dict:
    if not isinstance(raw, dict) or set(raw) - {'fade_in_frames', 'fade_out_frames', 'zoom_start', 'zoom_end'}:
        raise ValidationError('Aspetto immagine non supportato')
    if isinstance(frames, bool) or not isinstance(frames, int) or not 2 <= frames <= 9000:
        raise ValidationError('Durata immagine animata fuori limite')
    fades = [raw.get('fade_in_frames', 0), raw.get('fade_out_frames', 0)]
    if any(isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 60
           or value == 1 for value in fades) or sum(fades) > frames:
        raise ValidationError('Dissolvenze immagine fuori range o sovrapposte')
    scales = [raw.get('zoom_start', 1.), raw.get('zoom_end', 1.04)]
    if any(isinstance(value, bool) or not isinstance(value, (float, int))
           or not math.isfinite(value) or not 1. <= value <= 1.15 for value in scales):
        raise ValidationError('Zoom immagine non sicuro')
    return {'fade_in_frames': fades[0], 'fade_out_frames': fades[1],
            'zoom_start': float(scales[0]), 'zoom_end': float(scales[1])}


def prepare_presented_still(source: Path, asset_root: Path, fps: Fraction, frames: int,
                            width: int, height: int, appearance: dict) -> Path:
    style = validate_still_appearance(appearance, frames)
    fps = Fraction(fps)
    if fps not in (Fraction(24), Fraction(25), Fraction(30)):
        raise ValidationError('FPS immagine animata non consentiti')
    if any(isinstance(value, bool) or not isinstance(value, int) or not 16 <= value <= 4096
           for value in (width, height)) or width * height > 3840 * 2160:
        raise ValidationError('Canvas immagine animata non sicuro')
    root = asset_root.resolve(strict=True)
    generated = root / 'generated-stills'
    generated.mkdir(exist_ok=True)
    if not generated.resolve(strict=True).is_relative_to(root):
        raise ValidationError('Cartella carrier fuori asset root')
    target = generated / ('ARPHE_SOFT_STILL_' + uuid4().hex + '.mov')
    temporary = target.with_suffix('.part.mov')
    try:
        with av.open(str(source)) as decoded:
            metadata = decoded.streams.video[0]
            cover = validate_still_geometry(metadata.width,metadata.height,width,height,
                                             max(style['zoom_start'],style['zoom_end']))
            still = next(decoded.decode(video=0)).reformat(format='rgba')
        with av.open(str(temporary), 'w', format='mov') as encoded:
            stream = encoded.add_stream('png', rate=fps)
            stream.width, stream.height, stream.pix_fmt = width, height, 'rgba'
            stream.time_base = 1 / fps
            for index in range(frames + 1):
                local = min(index, frames - 1)
                progress = local / (frames - 1)
                zoom = style['zoom_start'] + (style['zoom_end'] - style['zoom_start']) * progress
                scaled_w, scaled_h = max(width, math.ceil(still.width*cover*zoom)), max(height, math.ceil(still.height*cover*zoom))
                pixels = still.reformat(width=scaled_w, height=scaled_h, format='rgba',
                                        interpolation='BICUBIC').to_ndarray(format='rgba')
                x, y = (scaled_w-width)//2, (scaled_h-height)//2
                pixels = np.ascontiguousarray(pixels[y:y+height, x:x+width]).copy()
                gain = 1.
                if style['fade_in_frames']:
                    gain = min(gain, local/(style['fade_in_frames']-1))
                if style['fade_out_frames']:
                    gain = min(gain, (frames-1-local)/(style['fade_out_frames']-1))
                gain = max(0., min(1., gain))
                gain = gain*gain*(3-2*gain)
                pixels[:,:,3] = np.rint(pixels[:,:,3].astype(float)*gain).astype(np.uint8)
                frame = av.VideoFrame.from_ndarray(pixels, format='rgba')
                frame.pts, frame.time_base = index, 1/fps
                for packet in stream.encode(frame): encoded.mux(packet)
            for packet in stream.encode(): encoded.mux(packet)
        with av.open(str(temporary)) as check:
            video = check.streams.video[0]
            if (video.frames != frames+1 or video.average_rate != fps
                    or (video.width, video.height) != (width,height) or len(check.streams.audio)):
                raise ValidationError('Overlay immagine animata non verificato')
        os.replace(temporary, target)
        return target
    except Exception as exc:
        temporary.unlink(missing_ok=True)
        if isinstance(exc, ValidationError): raise
        raise ValidationError('Generazione immagine animata fallita: '+type(exc).__name__) from exc


def prepare_still_video(source: Path, asset_root: Path, fps: Fraction, frames: int) -> Path:
    fps = Fraction(fps)
    if fps not in (Fraction(24), Fraction(25), Fraction(30)):
        raise ValidationError('FPS carrier immagine non consentiti')
    if isinstance(frames, bool) or not isinstance(frames, int) or not 1 <= frames <= 9000:
        raise ValidationError('Durata carrier immagine fuori limite [1,9000]')
    root = asset_root.resolve(strict=True)
    generated = root / 'generated-stills'
    generated.mkdir(exist_ok=True)
    if not generated.resolve(strict=True).is_relative_to(root):
        raise ValidationError('Cartella carrier fuori asset root')
    target = generated / ('ARPHE_STILL_' + uuid4().hex + '.mov')
    temporary = target.with_suffix('.part.mov')
    try:
        with av.open(str(source)) as decoded:
            still = next(decoded.decode(video=0)).reformat(format='rgba')
        # PNG in QuickTime preserves RGB, alpha and odd source dimensions.
        with av.open(str(temporary), 'w', format='mov') as encoded:
            stream = encoded.add_stream('png', rate=fps)
            stream.width, stream.height = still.width, still.height
            stream.pix_fmt = 'rgba'
            stream.time_base = 1 / fps
            for index in range(frames + 1):
                still.pts, still.time_base = index, 1 / fps
                for packet in stream.encode(still): encoded.mux(packet)
            for packet in stream.encode(): encoded.mux(packet)
        with av.open(str(temporary)) as check:
            video = check.streams.video[0]
            if (video.frames != frames + 1 or video.average_rate != fps
                    or (video.width, video.height) != (still.width, still.height)
                    or len(check.streams.audio)):
                raise ValidationError('Carrier immagine non verificato')
        os.replace(temporary, target)
        return target
    except Exception as exc:
        temporary.unlink(missing_ok=True)
        if isinstance(exc, ValidationError): raise
        raise ValidationError('Generazione carrier immagine fallita: ' + type(exc).__name__) from exc
