import os
import json
import sys
import asyncio
from typing import List, Dict, Any, Optional
from datetime import timedelta
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from contextlib import AsyncExitStack
from core.config import DATA_DIR

_SESSION_READ_TIMEOUT = timedelta(seconds=60)

MCP_SERVERS_FILE = os.path.join(DATA_DIR, "mcp_servers.json")

class MCPClientManager:
    def __init__(self, exit_stack: AsyncExitStack):
        self.exit_stack = exit_stack
        self.sessions: Dict[str, ClientSession] = {}
        self.servers_config: List[Dict[str, Any]] = self.load_servers()

    def load_servers(self) -> List[Dict[str, Any]]:
        if not os.path.exists(MCP_SERVERS_FILE):
            return []
        try:
            with open(MCP_SERVERS_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading MCP servers config: {e}")
            return []

    def save_servers(self):
        os.makedirs(os.path.dirname(MCP_SERVERS_FILE), exist_ok=True)
        with open(MCP_SERVERS_FILE, 'w') as f:
            json.dump(self.servers_config, f, indent=4)

    async def connect_server(self, config: Dict[str, Any]) -> Optional[ClientSession]:
        name = config.get("name")
        command = config.get("command")
        args = config.get("args", [])
        env_vars = config.get("env", {})

        if not name or not command:
            print(f"Skipping invalid server config: {config}")
            return None

        print(f"Connecting to MCP server '{name}' ({command} {args})...")
        
        # Prepare environment
        env = os.environ.copy()
        env.update(env_vars)

        # Handle 'npx' explicitly if needed, but often checking command is enough
        # If running on linux/mac, Ensure PATH is correct
        
        try:
            server_params = StdioServerParameters(
                command=command,
                args=args,
                env=env
            )

            read, write = await self.exit_stack.enter_async_context(stdio_client(server_params))
            session = await self.exit_stack.enter_async_context(
                ClientSession(read, write, read_timeout_seconds=_SESSION_READ_TIMEOUT)
            )
            await session.initialize()
            
            self.sessions[name] = session
            print(f"Connected to MCP server '{name}'.")
            return session
        except Exception as e:
            print(f"Failed to connect to MCP server '{name}': {e}")
            return None

    async def connect_all(self):
        """Connect to all configured servers."""
        for config in self.servers_config:
            name = config.get("name")
            # Avoid duplicate connections
            if name in self.sessions:
                continue
            session = await self.connect_server(config)
            if session:
                for s in self.servers_config:
                    if s["name"] == name:
                        s["status"] = "connected"
                        break
        return self.sessions

    async def add_server(self, name: str, command: str, args: List[str], env: Dict[str, str] = None):
        """Add a new server configuration and try to connect to it.
        
        The config is saved immediately regardless of connection success.
        Returns a dict with 'config' and 'connected' keys.
        """
        import shutil
        
        # Check if exists
        for s in self.servers_config:
            if s["name"] == name:
                raise ValueError(f"Server with name '{name}' already exists.")

        # Check if command is installed
        if shutil.which(command) is None:
            if command == "uvx":
                raise ValueError(f"Command '{command}' not found. Please install uv (e.g., curl -LsSf https://astral.sh/uv/install.sh | sh).")
            elif command == "npx":
                raise ValueError(f"Command '{command}' not found. Please install Node.js/npm.")
            else:
                raise ValueError(f"Command '{command}' not found in system PATH. Please install it first.")

        new_config = {
            "name": name,
            "command": command,
            "args": args,
            "env": env or {},
            "status": "disconnected"
        }
        
        # Save config immediately — connection attempt is best-effort
        self.servers_config.append(new_config)
        self.save_servers()
        
        # Try connecting (may fail for OAuth flows like mcp-remote)
        session = await self.connect_server(new_config)
        if session:
            new_config["status"] = "connected"
            # Update saved status
            for s in self.servers_config:
                if s["name"] == name:
                    s["status"] = "connected"
                    break
            self.save_servers()
            return {"config": new_config, "connected": True}
        else:
            # Config is already saved; return with connection failure info
            return {"config": new_config, "connected": False}

    async def reconnect_server(self, name: str):
        """Try to reconnect a previously saved server by name."""
        config = self.get_server_config(name)
        if not config:
            raise ValueError(f"Server '{name}' not found in configuration.")
        
        session = await self.connect_server(config)
        if session:
            for s in self.servers_config:
                if s["name"] == name:
                    s["status"] = "connected"
                    break
            self.save_servers()
            return True
        else:
            return False

    async def remove_server(self, name: str):
        """Remove a server configuration."""
        self.servers_config = [s for s in self.servers_config if s["name"] != name]
        self.save_servers()
        
        # We can't easily "disconnect" a session in mcp python client explicitely without closing the whole stack?
        # Actually ClientSession doesn't have a close/disconnect method that isolates it from the transport?
        # The transport is managed by the exit_stack. 
        # For now, we will just remove it from our tracking. 
        # A full restart might be best for clean cleanup, but for this MVP:
        if name in self.sessions:
            del self.sessions[name]
            # Note: The underlying process might still be running until server restart
            # This is a known limitation of the ExitStack approach for dynamic resource management unfortunately.
            # Ideally we should manage individual ExitStacks per connection.
        return True

    def get_server_config(self, name: str) -> Optional[Dict[str, Any]]:
        for s in self.servers_config:
            if s["name"] == name:
                return s
        return None
