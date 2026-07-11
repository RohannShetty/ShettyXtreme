# Generate test files
code = """
\"\"\"Tests for bar_builder.py\"\"\"

def test_placeholder():
    assert True
"""

with open('tests/data/test_bar_builder.py', 'w') as f:
    f.write(code)

with open('tests/data/test_stream_manager.py', 'w') as f:
    f.write(code.replace('bar_builder', 'stream_manager'))

print('test placeholders created')
