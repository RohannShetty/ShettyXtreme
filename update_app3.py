content = open("src/shettyxtreme/terminal/app.py", "rb").read().decode("utf-8")

# Add ScannerPanel to imports
old_imports = """from shettyxtreme.terminal.panels import (
    WatchlistPanel,
    MarketInternalsPanel,
    StatusBar,
    LogPanel,
    OrderPanel,
    PositionPanel,
)"""

new_imports = """from shettyxtreme.terminal.panels import (
    LogPanel,
    MarketInternalsPanel,
    OrderPanel,
    PositionPanel,
    ScannerPanel,
    StatusBar,
    WatchlistPanel,
)"""

if old_imports in content:
    content = content.replace(old_imports, new_imports)
    with open("src/shettyxtreme/terminal/app.py", "wb") as f:
        f.write(content.encode("utf-8"))
    print("ScannerPanel import added")
else:
    print("ERROR: old imports not found")
    print(repr(content[content.find("from shettyxtreme.terminal.panels"):content.find("from shettyxtreme.terminal.panels")+280]))
