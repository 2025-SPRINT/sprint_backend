import asyncio
import os
import sys
from contextlib import AsyncExitStack
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from google.genai import types
from dotenv import load_dotenv

class MCPKVConnector:
    def __init__(self, server_params: StdioServerParameters):
        self.server_params = server_params
        self.session = None
        self._exit_stack = None

    async def connect(self):
        self._exit_stack = AsyncExitStack()
        read_stream, write_stream = await self._exit_stack.enter_async_context(stdio_client(self.server_params))
        self.session = await self._exit_stack.enter_async_context(ClientSession(read_stream, write_stream))
        await self.session.initialize()
        return self.session

    async def get_gemini_tools(self):
        if not self.session:
            await self.connect()
        
        tools = await self.session.list_tools()
        gemini_tools = []
        for tool in tools.tools:
            # Map MCP tool schema to Gemini FunctionDeclaration
            # Sanitize schema for Gemini compatibility
            parameters = self._sanitize_schema(tool.inputSchema)
            
            declaration = types.FunctionDeclaration(
                name=tool.name,
                description=tool.description,
                parameters=parameters
            )
            gemini_tools.append(declaration)
        return gemini_tools

    def _sanitize_schema(self, schema):
        """Sanitize JSON schema for Gemini compatibility."""
        if not schema or not isinstance(schema, dict):
            return schema

        new_schema = schema.copy()
        properties = new_schema.get("properties", {})
        required = new_schema.get("required", [])

        # 1. Ensure all 'required' properties actually exist in 'properties'
        valid_required = [r for r in required if r in properties]
        if valid_required:
            new_schema["required"] = valid_required
        elif "required" in new_schema:
            del new_schema["required"]

        # 2. Fix enums (Gemini doesn't allow empty strings in enums)
        for prop_name, prop_data in properties.items():
            if isinstance(prop_data, dict) and "enum" in prop_data:
                # Remove empty strings from enums
                fixed_enum = [v for v in prop_data["enum"] if v != ""]
                if fixed_enum:
                    prop_data["enum"] = fixed_enum
                else:
                    # If enum becomes empty after filtering, remove the enum constraint
                    del prop_data["enum"]
        
        return new_schema

    async def call_tool(self, name, arguments):
        if not self.session:
            await self.connect()
        return await self.session.call_tool(name, arguments)

    async def disconnect(self):
        if self._exit_stack:
            await self._exit_stack.aclose()
            self.session = None
            self._exit_stack = None

async def get_kipris_connector(use_mock=False):
    load_dotenv()
    api_key = os.getenv("KIPRIS_API_KEY")
    
    # Check if API key is missing or is just the placeholder
    is_placeholder = api_key in [None, "", "your_key_here", "YOUR_API_KEY"]
    
    if use_mock or is_placeholder:
        if use_mock:
            print("로그: Mock KIPRIS 서버를 사용합니다.")
        else:
            print("로그: 유효한 KIPRIS_API_KEY를 찾을 수 없어 Mock KIPRIS 서버를 사용합니다.")
        
        server_params = StdioServerParameters(
            command=sys.executable,
            args=["mock_kipris_server.py"],
            env={**os.environ}
        )
        return MCPKVConnector(server_params)

    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-c", "import asyncio; import mcp_kipris.server; asyncio.run(mcp_kipris.server.main())"],
        env={**os.environ, "KIPRIS_API_KEY": api_key}
    )
    
    return MCPKVConnector(server_params)
