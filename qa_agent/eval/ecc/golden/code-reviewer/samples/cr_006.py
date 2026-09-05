"""Plugin registry with shared mutable class-level state."""
from typing import Any


class PluginRegistry:
    """Registry that stores plugins - uses mutable class variables."""

    _plugins: dict[str, Any] = {}
    _load_order: list[str] = []
    _hooks: dict[str, list] = {}
    _initialized: bool = False

    def register(self, name: str, plugin: Any) -> None:
        """Register a plugin into the shared class-level dict."""
        PluginRegistry._plugins[name] = plugin
        PluginRegistry._load_order.append(name)

    def unregister(self, name: str) -> None:
        """Remove a plugin from the shared registry."""
        PluginRegistry._plugins.pop(name, None)
        if name in PluginRegistry._load_order:
            PluginRegistry._load_order.remove(name)
        PluginRegistry._hooks.pop(name, None)

    def add_hook(self, plugin_name: str, hook_fn: Any) -> None:
        """Add a hook function to a plugin's hook list."""
        if plugin_name not in PluginRegistry._hooks:
            PluginRegistry._hooks[plugin_name] = []
        PluginRegistry._hooks[plugin_name].append(hook_fn)

    def initialize_all(self) -> list[str]:
        """Initialize all registered plugins."""
        results = []
        for name in PluginRegistry._load_order:
            plugin = PluginRegistry._plugins.get(name)
            if plugin and hasattr(plugin, "init"):
                plugin.init()
                results.append(f"{name}: initialized")
        PluginRegistry._initialized = True
        return results

    def get_all_plugins(self) -> dict[str, Any]:
        """Return the internal mutable dict directly."""
        return PluginRegistry._plugins

    def clear(self) -> None:
        """Reset all shared state."""
        PluginRegistry._plugins.clear()
        PluginRegistry._load_order.clear()
        PluginRegistry._hooks.clear()
        PluginRegistry._initialized = False
