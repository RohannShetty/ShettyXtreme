content = open("src/shettyxtreme/terminal/app.py", "r", newline="\n").read()

# 1. Fix imports - remove duplicates, add ScannerPanel
old_imports = """from shettyxtreme.terminal.panels import (
    WatchlistPanel,
    MarketInternalsPanel,
    StatusBar,
    LogPanel,
    OptionsChainPanel,
    OptionsStrategyPanel,
    WatchlistPanel,
    MarketInternalsPanel,
    StatusBar,
    LogPanel,
)"""

new_imports = """from shettyxtreme.terminal.panels import (
    LogPanel,
    MarketInternalsPanel,
    ScannerPanel,
    StatusBar,
    WatchlistPanel,
)"""

content = content.replace(old_imports, new_imports)

# 2. Replace PlaceholderPanel("Scanners") with ScannerPanel
old_scanner = 'self._scanners = PlaceholderPanel("Scanners", id="scanners-panel")'
new_scanner = 'self._scanners = ScannerPanel(id="scanners-panel")'
content = content.replace(old_scanner, new_scanner)

# 3. Change SIGNAL_GENERATED subscription
old_sub = "self._event_bus.subscribe(Topic.SIGNAL_GENERATED, self._on_log_event)"
new_sub = "self._event_bus.subscribe(Topic.SIGNAL_GENERATED, self._on_signal_generated)"
content = content.replace(old_sub, new_sub)

# 4. Add _on_signal_generated handler
old_handler = """        self._log.handle_event(event)

    def _poll_event_bus(self) -> None:"""

new_handler = """        self._log.handle_event(event)

    async def _on_signal_generated(self, event: Event) -> None:
        \"\"\"Dispatch SIGNAL_GENERATED events to ScannerPanel and LogPanel.

        Args:
            event: The SIGNAL_GENERATED event with a Signal dataclass.
        \"\"\"
        self._scanners.handle_signal(event)
        self._log.handle_event(event)

    def _poll_event_bus(self) -> None:"""

content = content.replace(old_handler, new_handler)

with open("src/shettyxtreme/terminal/app.py", "w", newline="\n") as f:
    f.write(content)

print("app.py updated successfully")
