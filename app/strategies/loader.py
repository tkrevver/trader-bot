"""Strategy loader for dynamically loading strategy modules.

This module discovers and loads strategy classes from the strategies/ directory.
Strategies must inherit from the Strategy base class to be discovered.
"""

import importlib
import importlib.util
import inspect
import os
import sys
from pathlib import Path
from typing import Optional, Type

from app.strategies.base import Strategy
from app.utils.logger import get_logger

logger = get_logger(__name__)


class StrategyLoader:
    """Load and manage strategy instances."""

    def __init__(self, strategies_dir: str = "strategies"):
        """Initialize strategy loader.

        Args:
            strategies_dir: Directory containing strategy files
        """
        self.strategies_dir = Path(strategies_dir)
        self._loaded_strategies: dict[str, Type[Strategy]] = {}
        self._strategy_instances: dict[str, Strategy] = {}

    def discover_strategies(self) -> list[str]:
        """Discover all strategy files in the strategies directory.

        Returns:
            List of strategy file names (without .py extension)
        """
        if not self.strategies_dir.exists():
            logger.warning(f"Strategies directory not found: {self.strategies_dir}")
            return []

        strategy_files = []
        for file in self.strategies_dir.glob("*.py"):
            if file.name.startswith("_") or file.name == "__init__.py":
                continue
            strategy_files.append(file.stem)

        logger.info(f"Discovered {len(strategy_files)} strategy files: {strategy_files}")
        return strategy_files

    def load_strategy_module(self, module_name: str) -> Optional[Type[Strategy]]:
        """Load a strategy class from a module file.

        Args:
            module_name: Name of the module (file name without .py)

        Returns:
            Strategy class if found, None otherwise
        """
        module_path = self.strategies_dir / f"{module_name}.py"

        if not module_path.exists():
            logger.error(f"Strategy file not found: {module_path}")
            return None

        try:
            # Load the module
            spec = importlib.util.spec_from_file_location(module_name, module_path)
            if spec is None or spec.loader is None:
                logger.error(f"Failed to load spec for {module_name}")
                return None

            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            # Find Strategy classes in the module
            strategy_classes = []
            for name, obj in inspect.getmembers(module, inspect.isclass):
                # Check if it's a Strategy subclass (but not the base Strategy class)
                if (
                    issubclass(obj, Strategy)
                    and obj is not Strategy
                    and obj.__module__ == module_name
                ):
                    strategy_classes.append(obj)

            if not strategy_classes:
                logger.warning(f"No Strategy classes found in {module_name}")
                return None

            if len(strategy_classes) > 1:
                logger.warning(
                    f"Multiple Strategy classes found in {module_name}, using first: {strategy_classes[0].__name__}"
                )

            strategy_class = strategy_classes[0]
            self._loaded_strategies[module_name] = strategy_class
            logger.info(
                f"Loaded strategy class: {strategy_class.__name__} from {module_name}"
            )
            return strategy_class

        except Exception as e:
            logger.error(f"Error loading strategy {module_name}: {e}", exc_info=True)
            return None

    def load_all_strategies(self) -> dict[str, Type[Strategy]]:
        """Load all discovered strategies.

        Returns:
            Dictionary mapping module names to Strategy classes
        """
        strategy_files = self.discover_strategies()

        for module_name in strategy_files:
            self.load_strategy_module(module_name)

        logger.info(f"Loaded {len(self._loaded_strategies)} strategies")
        return self._loaded_strategies.copy()

    def get_strategy_class(self, name: str) -> Optional[Type[Strategy]]:
        """Get a loaded strategy class by name.

        Args:
            name: Module name or strategy class name

        Returns:
            Strategy class if found, None otherwise
        """
        # Try by module name first
        if name in self._loaded_strategies:
            return self._loaded_strategies[name]

        # Try by class name
        for module_name, strategy_class in self._loaded_strategies.items():
            if strategy_class.__name__ == name:
                return strategy_class

        return None

    def instantiate_strategy(
        self, name: str, config: Optional[dict] = None
    ) -> Optional[Strategy]:
        """Instantiate a strategy by name.

        Args:
            name: Module name or strategy class name
            config: Strategy configuration

        Returns:
            Strategy instance if successful, None otherwise
        """
        strategy_class = self.get_strategy_class(name)
        if strategy_class is None:
            logger.error(f"Strategy class not found: {name}")
            return None

        try:
            instance = strategy_class(config=config)
            instance.initialize()

            # Cache instance with strategy metadata name
            metadata = instance.get_metadata()
            self._strategy_instances[metadata.name] = instance

            logger.info(
                f"Instantiated strategy: {metadata.name} (v{metadata.version})"
            )
            return instance

        except Exception as e:
            logger.error(f"Error instantiating strategy {name}: {e}", exc_info=True)
            return None

    def get_strategy_instance(self, name: str) -> Optional[Strategy]:
        """Get a cached strategy instance.

        Args:
            name: Strategy name (from metadata)

        Returns:
            Strategy instance if cached, None otherwise
        """
        return self._strategy_instances.get(name)

    def reload_strategy(self, module_name: str) -> Optional[Type[Strategy]]:
        """Reload a strategy module.

        Useful for development when strategy code changes.

        Args:
            module_name: Module name to reload

        Returns:
            Reloaded strategy class if successful, None otherwise
        """
        # Remove from cache
        if module_name in self._loaded_strategies:
            del self._loaded_strategies[module_name]

        # Remove instances
        instances_to_remove = []
        for name, instance in self._strategy_instances.items():
            if instance.__class__.__module__ == module_name:
                instances_to_remove.append(name)

        for name in instances_to_remove:
            del self._strategy_instances[name]

        # Reload the module
        return self.load_strategy_module(module_name)

    def get_all_strategy_metadata(self) -> list[dict]:
        """Get metadata for all loaded strategies.

        Returns:
            List of strategy metadata dictionaries
        """
        metadata_list = []

        for module_name, strategy_class in self._loaded_strategies.items():
            try:
                # Create temporary instance to get metadata
                temp_instance = strategy_class()
                metadata = temp_instance.get_metadata()
                metadata_list.append(
                    {
                        "module_name": module_name,
                        "class_name": strategy_class.__name__,
                        "name": metadata.name,
                        "description": metadata.description,
                        "version": metadata.version,
                        "author": metadata.author,
                        "symbols": metadata.symbols,
                        "timeframes": metadata.timeframes,
                        "parameters": metadata.parameters,
                    }
                )
            except Exception as e:
                logger.error(
                    f"Error getting metadata for {module_name}: {e}", exc_info=True
                )
                continue

        return metadata_list

    def clear_cache(self) -> None:
        """Clear all cached strategies and instances."""
        self._loaded_strategies.clear()
        self._strategy_instances.clear()
        logger.info("Cleared strategy cache")
