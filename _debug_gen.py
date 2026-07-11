import os

base = '/d/ShettyXtreme'

def w(relpath, content):
    full = os.path.join(base, relpath)
    print(f"  Writing to: {full}")
    os.makedirs(os.path.dirname(full), exist_ok=True)
    print(f"  Content length: {len(content)}")
    with open(full, 'w', newline='\n') as f:
        f.write(content)
    print(f"  File exists after write: {os.path.exists(full)}")
    print('OK:', relpath)

content = """
test content
"""
print(f"Debug content: [{content}]")
print(f"Length: {len(content)}")

w('src/shettyxtreme/data/pipeline/test_write.txt', content)
print("Done")
