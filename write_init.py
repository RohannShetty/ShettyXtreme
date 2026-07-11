with open('src/shettyxtreme/data/pipeline/__init__.py', 'w') as f:
    f.write("""from shettyxtreme.data.pipeline.stream_manager import StreamManager
from shettyxtreme.data.pipeline.bar_builder import BarBuilder

__all__ = ["StreamManager", "BarBuilder"]
""")
print('done')
