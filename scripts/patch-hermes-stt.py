#!/usr/bin/env python3
"""Version-checked mechanical patch for Telegram .oga uploads (Hermes 0.21.1)."""
import ast
from pathlib import Path
p=Path('/opt/hermes/tools/transcription_cloud.py')
text=p.read_text()
old='                return client.audio.transcriptions.create(file=audio_file, **create_kwargs)'
new='''                # Telegram .oga is Ogg; some STT APIs validate the upload suffix.
                upload_name = Path(path).name
                if Path(upload_name).suffix.lower() == ".oga":
                    upload_name = str(Path(upload_name).with_suffix(".ogg"))
                return client.audio.transcriptions.create(file=(upload_name, audio_file), **create_kwargs)'''
if new in text:
    print('Hermes Ogg filename patch already installed')
else:
    if text.count(old)!=1:raise SystemExit('Unexpected upstream STT source; refusing patch')
    updated=text.replace(old,new);ast.parse(updated);p.write_text(updated)
    print('Hermes Ogg filename normalization installed')
