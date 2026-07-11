import os
D = "docs/architecture/sections"
def ws(n, c):
    with open(os.path.join(D, n), "w") as fh:
        fh.write(c)
        print(f"{n}: {len(c)} chars")
