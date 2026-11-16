"""Registro de módulos: descubre, valida y expone los módulos activos."""

from __future__ import annotations

import importlib
import logging

from core.module_system.base import MODULE_API_VERSION, NMCModule
from core.module_system.events import EventBus, bus

logger = logging.getLogger("nmc.modules")


class ModuleLoadError(RuntimeError):
    pass


class ModuleRegistry:
    def __init__(self, event_bus: EventBus = bus) -> None:
        self._modules: dict[str, NMCModule] = {}
        self._bus = event_bus

    def register(self, module: NMCModule) -> None:
        manifest = getattr(module, "manifest", None)
        if manifest is None:
            raise ModuleLoadError(f"{module!r} no define 'manifest'.")
        if manifest.api_version != MODULE_API_VERSION:
            raise ModuleLoadError(
                f"El módulo '{manifest.name}' usa el contrato v{manifest.api_version}; "
                f"el núcleo ofrece v{MODULE_API_VERSION}."
            )
        if manifest.name in self._modules:
            raise ModuleLoadError(f"Ya hay un módulo registrado como '{manifest.name}'.")
        self._modules[manifest.name] = module
        module.register_events(self._bus)
        logger.info("Módulo cargado: %s %s", manifest.name, manifest.version)

    def load(self, names: list[str]) -> None:
        """Carga módulos por nombre corto (``tasks``) o ruta (``paquete.modulo``)."""
        for name in names:
            path = name if "." in name else f"modules.{name}"
            try:
                package = importlib.import_module(path)
            except ImportError as exc:
                raise ModuleLoadError(f"No se pudo importar el módulo '{name}': {exc}") from exc
            module = getattr(package, "module", None)
            if not isinstance(module, NMCModule):
                raise ModuleLoadError(
                    f"'{path}' debe exponer una variable 'module' de tipo NMCModule."
                )
            if module.manifest.name not in self._modules:
                self.register(module)
        self._check_dependencies()

    def _check_dependencies(self) -> None:
        for module in self._modules.values():
            missing = [d for d in module.manifest.depends_on if d not in self._modules]
            if missing:
                raise ModuleLoadError(
                    f"El módulo '{module.manifest.name}' requiere: {', '.join(missing)}."
                )

    def get(self, name: str) -> NMCModule | None:
        return self._modules.get(name)

    def all(self) -> list[NMCModule]:
        return list(self._modules.values())

    def names(self) -> list[str]:
        return list(self._modules)

    def clear(self) -> None:
        self._modules.clear()


registry = ModuleRegistry()


def import_module_models(names: list[str]) -> None:
    """Importa ``<módulo>.models`` (si existe) para que Alembic vea sus tablas."""
    for name in names:
        path = name if "." in name else f"modules.{name}"
        try:
            importlib.import_module(f"{path}.models")
        except ModuleNotFoundError as exc:
            if exc.name != f"{path}.models":
                raise
