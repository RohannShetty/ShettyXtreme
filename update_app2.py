content = open("src/shettyxtreme/terminal/app.py", "rb").read().decode("utf-8")

# Check current handler area
old_handler = '        self._log.handle_event(event)\r\n\r\n    def _poll_event_bus(self) -> None:'
new_handler = '        self._log.handle_event(event)\r\n\r\n    async def _on_signal_generated(self, event: Event) -> None:\r\n        """Dispatch SIGNAL_GENERATED events to ScannerPanel and LogPanel.\r\n\r\n        Args:\r\n            event: The SIGNAL_GENERATED event with a Signal dataclass.\r\n        """\r\n        self._scanners.handle_signal(event)\r\n        self._log.handle_event(event)\r\n\r\n    def _poll_event_bus(self) -> None:'

if old_handler in content:
    content = content.replace(old_handler, new_handler)
    with open("src/shettyxtreme/terminal/app.py", "wb") as f:
        f.write(content.encode("utf-8"))
    print("Handler added successfully")
else:
    print("ERROR: old_handler pattern not found")
    # Show the actual text around that area
    import re
    m = re.search(r'handle_event\(event\).*?poll_event_bus', content, re.DOTALL)
    if m:
        print(repr(m.group()))
