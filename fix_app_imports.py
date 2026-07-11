"""Fix the app.py imports section."""
with open("src/shettyxtreme/terminal/app.py") as f:
    lines = f.readlines()

# Find the import block and fix it
new_imports = """from shettyxtreme.terminal.panels import (
    WatchlistPanel,
    MarketInternalsPanel,
    StatusBar,
    LogPanel,
    OrderPanel,
    PositionPanel,
)
from shettyxtreme.execution.paper_trading import PaperTradingEngine

"""

# Find the line where the old imports block starts
start_idx = None
for i, line in enumerate(lines):
    if "from shettyxtreme.terminal.panels import" in line and "(" in line:
        start_idx = i
        break

if start_idx is not None:
    # Find the closing paren
    end_idx = None
    for i in range(start_idx, len(lines)):
        if ")" in lines[i]:
            end_idx = i
            break
    
    if end_idx is not None:
        # Also check if there's a second import block nearby
        # Remove lines from start_idx to after the imports
        # But first, let's find where the PlaceholderPanel class starts
        class_idx = None
        for i in range(end_idx, len(lines)):
            if "class PlaceholderPanel" in lines[i]:
                class_idx = i
                break
        
        # Remove everything from start_idx to just before class_idx
        # Actually, let's just rewrite the section
        before = "".join(lines[:start_idx])
        after = "".join(lines[class_idx:])
        
        new_content = before + new_imports + after
        
        with open("src/shettyxtreme/terminal/app.py", "w") as f:
            f.write(new_content)
        print("Imports fixed.")
    else:
        print("Could not find closing paren of imports.")
else:
    print("Could not find imports block.")
