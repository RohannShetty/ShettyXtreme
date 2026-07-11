import base64
import os

# stream_manager.py in base64
b64 = """aW1wb3J0IGFzeW5jaW8KaW1wb3J0IGpzb24KaW1wb3J0IGxvZ2dpbmcKZnJvbSBkYXRl
dGltZSBpbXBvcnQgZGF0ZXRpbWUsIHRpbWV6b25lCmZyb20gdHlwaW5nIGltcG9y
dCBBbnkKCmltcG9ydCBodHRweAppbXBvcnQgd2Vic29ja2V0cwoKZnJvbSBzaGV0
dHl4dHJlbWUuY29yZS5kYXRhX21vZGVscy5tYXJrZXRfZGF0YSBpbXBvcnQgVGlj
awpmcm9tIHNoZXR0eXh0cmVtZS5jb3JlLmV2ZW50X2J1cy5ldmVudF9idXMgaW1w
b3J0IEV2ZW50LCBFdmVudEJ1cywgVG9waWMKCg=="""

path = '/d/ShettyXtreme/src/shettyxtreme/data/pipeline/stream_manager.py'
os.makedirs(os.path.dirname(path), exist_ok=True)
with open(path, 'w', newline='\n') as f:
    f.write(base64.b64decode(b64).decode())

print("test decode ok")
