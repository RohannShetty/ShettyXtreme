import os, sys
base = '/d/ShettyXtreme'
test_path = os.path.join(base, 'src/shettyxtreme/data/pipeline/test_ws.txt')
print(f"Target: {test_path}")
print(f"Target exists: {os.path.exists(test_path)}")
print(f"Target dir exists: {os.path.exists(os.path.dirname(test_path))}")
os.makedirs(os.path.dirname(test_path), exist_ok=True)
try:
    with open(test_path, 'w', newline='\n') as f:
        f.write("hello world\n")
    print(f"Write succeeded, file exists: {os.path.exists(test_path)}")
    with open(test_path, 'r') as f:
        print(f"Read back: [{f.read()}]")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
