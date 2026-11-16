"""Contrato de los proveedores de embeddings."""

from __future__ import annotations

from abc import ABC, abstractmethod

from core.database.models import EMBEDDING_DIM


class EmbeddingError(RuntimeError):
    """El proveedor no pudo generar vectores."""


class EmbeddingProvider(ABC):
    """Convierte textos en vectores de ``EMBEDDING_DIM`` dimensiones.

    Los umbrales dependen del proveedor porque cada espacio vectorial reparte
    las similitudes de forma distinta.
    """

    name: str = "base"
    model: str = ""
    dim: int = EMBEDDING_DIM
    #: Similitud coseno a partir de la cual dos textos se marcan como posible duplicado.
    duplicate_threshold: float = 0.95
    #: Similitud a partir de la cual se propone una relación automática.
    related_threshold: float = 0.6
    #: Similitud mínima para aceptar un resultado puramente semántico.
    min_relevance: float = 0.3
    #: ¿Captura significado (sinónimos, paráfrasis) o solo parecido léxico?
    semantic: bool = True
    #: ¿Envía el texto a un servicio externo?
    external: bool = False

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Devuelve un vector normalizado por texto."""

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]

    def _check(self, vectors: list[list[float]]) -> list[list[float]]:
        for vector in vectors:
            if len(vector) != self.dim:
                raise EmbeddingError(
                    f"El proveedor '{self.name}' ({self.model}) devolvió {len(vector)} "
                    f"dimensiones y la base de datos espera {self.dim}. "
                    "Consulta docs/architecture/embeddings.md."
                )
        return vectors

    def describe(self) -> dict:
        return {
            "provider": self.name,
            "model": self.model,
            "dimensions": self.dim,
            "semantic": self.semantic,
            "external": self.external,
        }
