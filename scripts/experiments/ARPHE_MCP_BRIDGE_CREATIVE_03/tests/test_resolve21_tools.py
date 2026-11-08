from __future__ import annotations

import unittest

from bridge.server import mcp
from bridge.tool_catalog import EXPOSED_TOOL_NAMES


TOOLS = {
    "inspect_resolve21_compatibility",
    "start_native_transcription21",
    "read_native_transcription21",
    "export_review_frames21",
}


class Resolve21ToolRegistrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_resolve21_tools_are_registered_and_catalogued(self):
        tools = {tool.name: tool for tool in await mcp.list_tools()}
        self.assertTrue(TOOLS.issubset(EXPOSED_TOOL_NAMES))
        self.assertTrue(TOOLS.issubset(tools))
        self.assertTrue(tools["inspect_resolve21_compatibility"].annotations.read_only_hint)
        self.assertTrue(tools["read_native_transcription21"].annotations.read_only_hint)
        self.assertTrue(tools["export_review_frames21"].annotations.read_only_hint)
        self.assertFalse(tools["start_native_transcription21"].annotations.read_only_hint)
        self.assertTrue(tools["start_native_transcription21"].annotations.idempotent_hint)


if __name__ == "__main__":
    unittest.main()
