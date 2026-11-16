import uuid
from datetime import UTC, datetime, timedelta

import pytest

from core.config import Settings
from core.errors import InvalidInputError
from core.ingestion.classifier import classify_type, detect_kind, suggest_tags
from core.memory_engine.service import normalize_tags
from core.module_system.base import ModuleManifest, NMCModule
from core.module_system.events import EventBus
from core.module_system.registry import ModuleLoadError, ModuleRegistry
from core.retrieval.answer import parse_llm_json
from core.retrieval.engine import fuse, recency_score
from core.retrieval.semantic_search import SemanticHit
from core.retrieval.text_search import TextHit, build_tsquery
from core.security.auth import (
    LoginThrottle,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from modules.documents.extract import extract_text


# ----------------------------------------------------------------- seguridad
def test_password_hash_roundtrip():
    hashed = hash_password("contraseña-segura-123")
    assert hashed != "contraseña-segura-123"
    assert verify_password("contraseña-segura-123", hashed)
    assert not verify_password("otra", hashed)
    assert not verify_password("x", "no-es-un-hash")


def test_token_roundtrip_and_tampering():
    class FakeUser:
        id = uuid.uuid4()
        username = "ana"
        role = "admin"

    settings = Settings(secret_key="k" * 40)
    token, expires = create_access_token(FakeUser(), settings)
    payload = decode_access_token(token, settings)
    assert payload["sub"] == str(FakeUser.id) and payload["role"] == "admin"
    assert expires > datetime.now(UTC)
    assert decode_access_token(token + "x", settings) is None
    assert decode_access_token(token, Settings(secret_key="z" * 40)) is None


def test_expired_token_is_rejected():
    class FakeUser:
        id = uuid.uuid4()
        username = "ana"
        role = "admin"

    settings = Settings(secret_key="k" * 40, access_token_minutes=-1)
    token, _ = create_access_token(FakeUser(), settings)
    assert decode_access_token(token, settings) is None


def test_settings_require_strong_secret():
    with pytest.raises(RuntimeError, match="NMC_SECRET_KEY"):
        Settings(secret_key="corta").validate_runtime()
    Settings(secret_key="k" * 32).validate_runtime()
    with pytest.raises(RuntimeError, match="CORS"):
        Settings(secret_key="k" * 32, environment="production", cors_origins="*").validate_runtime()


def test_login_throttle_blocks_and_recovers():
    throttle = LoginThrottle(max_attempts=3, window_seconds=60)
    for _ in range(3):
        assert not throttle.blocked("k")
        throttle.failure("k")
    assert throttle.blocked("k")
    assert not throttle.blocked("otra")
    throttle.success("k")
    assert not throttle.blocked("k")


# ---------------------------------------------------------------- recuperación
def test_build_tsquery_is_safe_or_query():
    assert build_tsquery(["base", "datos", "base"]) == "base | datos"
    assert build_tsquery(["a&b", "ok", "x|y", "!"]) == "ok"
    assert build_tsquery([]) == ""


def test_fuse_rewards_agreement_between_methods():
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    scores = fuse(
        [TextHit(a, 0.9, ""), TextHit(b, 0.5, "")],
        [SemanticHit(a, 0.8, 0, ""), SemanticHit(c, 0.7, 0, "")],
    )
    assert scores[a] == pytest.approx(1.0)
    assert scores[a] > scores[b] > 0
    assert scores[a] > scores[c] > 0


def test_recency_score_decays():
    now = datetime.now(UTC)
    assert recency_score(now, now) == pytest.approx(1.0)
    assert recency_score(now - timedelta(days=120), now) == pytest.approx(0.5, rel=1e-3)
    assert recency_score(now - timedelta(days=1000), now) < 0.01


def test_parse_llm_json_tolerates_wrapping():
    assert parse_llm_json('```json\n{"answer": "ok"}\n```') == {"answer": "ok"}
    with pytest.raises(ValueError):
        parse_llm_json("sin json")


# -------------------------------------------------------------- clasificación
@pytest.mark.parametrize(
    ("text", "source", "has_project", "expected"),
    [
        ("Prefiero trabajar con Python y FastAPI", "manual", False, "preference"),
        ("Ayer me reuní con el equipo de diseño", "manual", False, "episodic"),
        ("Decidimos usar Docker", "manual", True, "project"),
        ("Un grafo es un conjunto de nodos y aristas", "manual", False, "semantic"),
        ("cualquier cosa", "conversation", False, "episodic"),
        ("cualquier cosa", "document", False, "document"),
        ("Avance del sprint", "manual", True, "project"),
    ],
)
def test_classify_type(text, source, has_project, expected):
    memory_type, rule = classify_type(text, source_type=source, has_project=has_project)
    assert memory_type == expected and rule


def test_detect_kind():
    assert detect_kind("Se decidió migrar a PostgreSQL") == "decision"
    assert detect_kind("Nota cualquiera") is None


def test_suggest_tags_prefers_known_tags_and_repeated_words():
    tags = suggest_tags(
        "El backend usa FastAPI. FastAPI es rápido. Me gusta FastAPI para el backend.",
        None,
        ["backend", "finanzas"],
    )
    assert "backend" in tags and "fastapi" in tags and "finanzas" not in tags


def test_normalize_tags():
    assert normalize_tags(["  Python ", "python", "Base  de Datos", ""]) == [
        "python",
        "base de datos",
    ]


# -------------------------------------------------------------------- módulos
class _Dummy(NMCModule):
    def __init__(self, name, depends_on=(), api_version=1):
        self.manifest = ModuleManifest(
            name=name, version="1", description="", depends_on=depends_on, api_version=api_version
        )
        self.events_registered = False

    def register_events(self, bus):
        self.events_registered = True


def test_registry_registers_and_rejects_duplicates():
    registry = ModuleRegistry(EventBus())
    module = _Dummy("finanzas")
    registry.register(module)
    assert registry.names() == ["finanzas"] and module.events_registered
    with pytest.raises(ModuleLoadError, match="Ya hay"):
        registry.register(_Dummy("finanzas"))


def test_registry_rejects_incompatible_contract_and_missing_dependency():
    registry = ModuleRegistry(EventBus())
    with pytest.raises(ModuleLoadError, match="contrato"):
        registry.register(_Dummy("viejo", api_version=99))
    registry.register(_Dummy("a", depends_on=("b",)))
    with pytest.raises(ModuleLoadError, match="requiere"):
        registry._check_dependencies()


def test_registry_load_errors_are_clear():
    registry = ModuleRegistry(EventBus())
    with pytest.raises(ModuleLoadError, match="No se pudo importar"):
        registry.load(["modulo_que_no_existe"])
    with pytest.raises(ModuleLoadError, match="debe exponer"):
        registry.load(["core.textutils"])


def test_event_bus_isolates_failing_handlers():
    bus = EventBus()
    calls = []

    def broken(**_):
        raise RuntimeError("fallo del módulo")

    bus.subscribe("e", broken)
    bus.subscribe("e", lambda **payload: calls.append(payload))
    bus.publish("e", value=1)
    assert calls == [{"value": 1}]


# ----------------------------------------------------------------- documentos
def test_extract_plain_text_and_encodings():
    text, details = extract_text("nota.md", "título\ncañón".encode())
    assert "cañón" in text and details["extraction"] == "texto plano"
    text, _ = extract_text("nota.txt", "cañón".encode("latin-1"))
    assert text == "cañón"


def test_extract_rejects_unknown_and_binary():
    with pytest.raises(InvalidInputError, match="no admitido"):
        extract_text("foto.png", b"\x89PNG")
    with pytest.raises(InvalidInputError):
        extract_text("roto.pdf", b"esto no es un pdf")
