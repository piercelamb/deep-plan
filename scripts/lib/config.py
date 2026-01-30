"""Configuration management for deep-plan plugin.

Two types of config:
1. Global config (config.json) - plugin-wide settings in plugin root
2. Session config (deep_plan_config.json) - session-specific values in planning dir
"""

import json
import os
from pathlib import Path


# Session config file name (stored in planning directory)
SESSION_CONFIG_FILENAME = "deep_plan_config.json"

# Fully qualified subagent type for section-writer
# Used by SubagentStart/SubagentStop hooks to identify section-writer agents
SECTION_WRITER_AGENT_TYPE = "deep-plan:section-writer"

# Required keys in session config
SESSION_REQUIRED_KEYS = ["plugin_root", "planning_dir", "initial_file"]


class ConfigError(Exception):
    """Raised when config is missing or invalid."""
    pass


# =============================================================================
# Global Config (plugin-wide settings)
# =============================================================================

def load_global_config() -> dict:
    """Load global config from plugin root.

    Looks for config.json at CLAUDE_PLUGIN_ROOT, falling back to
    relative path resolution if env var not set.

    Returns:
        dict: Parsed configuration

    Raises:
        FileNotFoundError: If config.json doesn't exist
        json.JSONDecodeError: If config.json is malformed
    """
    plugin_root = os.environ.get(
        "CLAUDE_PLUGIN_ROOT",
        Path(__file__).parent.parent.parent
    )
    config_path = Path(plugin_root) / "config.json"
    return json.loads(config_path.read_text())


# Backwards compatibility alias
load_config = load_global_config


# =============================================================================
# Session Config (planning directory specific)
# =============================================================================

def get_session_config_path(planning_dir: Path) -> Path:
    """Get the path to the session config file for a planning directory."""
    return planning_dir / SESSION_CONFIG_FILENAME


def session_config_exists(planning_dir: Path) -> bool:
    """Check if a session config file exists in the planning directory."""
    return get_session_config_path(planning_dir).exists()


def load_session_config(planning_dir: Path) -> dict:
    """Load session config from a planning directory.

    Args:
        planning_dir: Path to the planning directory

    Returns:
        dict with session config values

    Raises:
        ConfigError: If config doesn't exist or is invalid
    """
    config_path = get_session_config_path(planning_dir)

    if not config_path.exists():
        raise ConfigError(f"Session config not found: {config_path}")

    try:
        with open(config_path) as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        raise ConfigError(f"Invalid JSON in session config: {e}")

    # Validate required keys
    missing_keys = [key for key in SESSION_REQUIRED_KEYS if key not in config]
    if missing_keys:
        raise ConfigError(f"Session config missing required keys: {missing_keys}")

    return config


def save_session_config(planning_dir: Path, config: dict) -> Path:
    """Save session config to a planning directory.

    Args:
        planning_dir: Path to the planning directory
        config: dict with config values

    Returns:
        Path to the saved config file

    Raises:
        ConfigError: If config is missing required keys
    """
    # Validate required keys before saving
    missing_keys = [key for key in SESSION_REQUIRED_KEYS if key not in config]
    if missing_keys:
        raise ConfigError(f"Cannot save config missing required keys: {missing_keys}")

    config_path = get_session_config_path(planning_dir)

    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)

    return config_path


def create_session_config(
    planning_dir: Path,
    plugin_root: str,
    initial_file: str,
) -> dict:
    """Create a new session config by copying global config and adding session keys.

    The session config is a copy of the plugin's global config.json with
    session-specific keys (plugin_root, planning_dir, initial_file) added.
    This allows scripts to reference a single config file for both plugin
    settings and session paths.

    Args:
        planning_dir: Path to the planning directory
        plugin_root: Path to the plugin root
        initial_file: Path to the initial spec file

    Returns:
        The created config dict

    Raises:
        ConfigError: If global config.json cannot be loaded
    """
    # Start with a copy of the global config
    plugin_root_path = Path(plugin_root)
    global_config_path = plugin_root_path / "config.json"

    if not global_config_path.exists():
        raise ConfigError(f"Global config not found: {global_config_path}")

    try:
        with open(global_config_path) as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        raise ConfigError(f"Invalid JSON in global config: {e}")

    # Add session-specific keys
    config["plugin_root"] = plugin_root
    config["planning_dir"] = str(planning_dir)
    config["initial_file"] = initial_file

    save_session_config(planning_dir, config)
    return config


def get_or_create_session_config(
    planning_dir: Path,
    plugin_root: str,
    initial_file: str,
) -> tuple[dict, bool]:
    """Get existing session config or create a new one.

    Args:
        planning_dir: Path to the planning directory
        plugin_root: Path to the plugin root (used if creating)
        initial_file: Path to the initial spec file (used if creating)

    Returns:
        Tuple of (config dict, was_created bool)

    Raises:
        ConfigError: If existing config is invalid
    """
    if session_config_exists(planning_dir):
        config = load_session_config(planning_dir)
        return config, False
    else:
        config = create_session_config(planning_dir, plugin_root, initial_file)
        return config, True
