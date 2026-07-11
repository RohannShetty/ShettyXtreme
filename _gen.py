import os
base = '/d/ShettyXtreme'

def w(relpath, content):
    full = os.path.join(base, relpath)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, 'w', newline='\n') as f:
        f.write(content.lstrip('\n'))
    print('OK:', relpath)

# __init__.py
w('src/shettyxtreme/data/pipeline/__init__.py', '''
# Data pipeline: streaming, bar building, and ingestion
from shettyxtreme.data.pipeline.stream_manager import StreamManager, StreamConfig
from shettyxtreme.data.pipeline.bar_builder import BarBuilder, compute_bar_timestamp

__all__ = [
    "StreamManager",
    "StreamConfig",
    "BarBuilder",
    "compute_bar_timestamp",
]
''')

print('Done')
