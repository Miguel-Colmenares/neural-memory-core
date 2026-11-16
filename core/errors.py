"""Errores de dominio. La API los traduce a respuestas HTTP."""

from __future__ import annotations


class NMCError(Exception):
    status_code = 400

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class NotFoundError(NMCError):
    status_code = 404


class InvalidInputError(NMCError):
    status_code = 422


class ConflictError(NMCError):
    status_code = 409


class ServiceUnavailableError(NMCError):
    status_code = 503
