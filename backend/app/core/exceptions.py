import logging
from typing import Any
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)

DEFAULT_STATUS_MESSAGES_ES: dict[int, str] = {
    400: "Solicitud inválida",
    401: "No autenticado o sesión expirada",
    403: "No tienes permisos para realizar esta acción",
    404: "Recurso no encontrado",
    405: "Método no permitido",
    409: "Conflicto con el estado actual del recurso",
    500: "Error interno del servidor",
    503: "Servicio de base de datos no disponible",
}

ENGLISH_DEFAULT_PHRASES: dict[str, str] = {
    "Not Found": "Recurso no encontrado",
    "Method Not Allowed": "Método no permitido",
    "Unauthorized": "No autenticado o sesión expirada",
    "Not authenticated": "No autenticado o sesión expirada",
    "Forbidden": "No tienes permisos para realizar esta acción",
    "Bad Request": "Solicitud inválida",
    "Internal Server Error": "Error interno del servidor",
    "Service Unavailable": "Servicio de base de datos no disponible",
}


def _extract_field_name(loc: tuple[Any, ...] | list[Any]) -> str:
    parts = [str(item) for item in loc]
    if len(parts) > 1 and parts[0] in {"body", "query", "path", "header", "cookie"}:
        parts = parts[1:]
    return ".".join(parts) if parts else "body"


def _translate_validation_error(err: dict[str, Any]) -> str:
    err_type = str(err.get("type", ""))
    ctx = err.get("ctx") or {}
    msg = str(err.get("msg", ""))

    if err_type == "json_invalid":
        return "El cuerpo de la petición no es un JSON válido"
    if err_type == "extra_forbidden":
        return "Este campo no está permitido"
    if err_type == "missing":
        return "Este campo es obligatorio"
    if err_type == "string_too_short":
        min_length = ctx.get("min_length", "")
        return f"El texto debe tener al menos {min_length} caracteres".strip()
    if err_type == "string_too_long":
        max_length = ctx.get("max_length", "")
        return f"El texto no debe superar los {max_length} caracteres".strip()
    if err_type == "greater_than_equal":
        ge = ctx.get("ge", "")
        return f"El valor debe ser mayor o igual a {ge}".strip()
    if err_type == "greater_than":
        gt = ctx.get("gt", "")
        return f"El valor debe ser mayor que {gt}".strip()
    if err_type == "less_than_equal":
        le = ctx.get("le", "")
        return f"El valor debe ser menor o igual a {le}".strip()
    if err_type == "less_than":
        lt = ctx.get("lt", "")
        return f"El valor debe ser menor que {lt}".strip()
    if err_type in {"int_parsing", "int_type"}:
        return "El valor debe ser un número entero válido"
    if err_type in {"float_parsing", "float_type"}:
        return "El valor debe ser un número válido"
    if err_type in {"bool_parsing", "bool_type"}:
        return "El valor debe ser booleano"
    if err_type in {"string_type", "string_unicode"}:
        return "El valor debe ser una cadena de texto válida"
    if err_type.startswith("datetime") or err_type.startswith("date"):
        return "El formato de fecha u hora no es válido"
    if err_type == "enum":
        expected = ctx.get("expected", "")
        return f"Valor no permitido; valores válidos: {expected}".strip()
    if err_type == "string_pattern_mismatch":
        return "El formato del campo no es válido"
    if err_type == "value_error":
        custom_err = ctx.get("error")
        reason = ctx.get("reason")
        loc_parts = [str(item).lower() for item in (err.get("loc") or ())]
        combined_lower = f"{msg} {custom_err or ''} {reason or ''}".lower()
        if (
            "email" in combined_lower
            or "correo electrónico" in combined_lower
            or "email" in loc_parts
        ):
            return "El correo electrónico no es válido"
        if custom_err is not None:
            text = str(custom_err)
            if text and not text.lower().startswith("value error"):
                return text
        if msg.lower().startswith("value error, "):
            return msg[len("value error, ") :]
    return "Valor inválido para este campo"


async def http_exception_handler(
    request: Request,
    exc: StarletteHTTPException,
) -> JSONResponse:
    raw_detail = exc.detail
    if isinstance(raw_detail, str) and raw_detail.strip():
        detail = ENGLISH_DEFAULT_PHRASES.get(raw_detail, raw_detail)
    else:
        detail = DEFAULT_STATUS_MESSAGES_ES.get(
            exc.status_code,
            "Error al procesar la solicitud",
        )
    headers = dict(exc.headers or {})
    if exc.status_code == 401 and not any(
        k.lower() == "www-authenticate" for k in headers
    ):
        headers["WWW-Authenticate"] = "Bearer"
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": detail},
        headers=headers or None,
    )


async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    raw_errors = exc.errors()
    formatted_errors: list[dict[str, str]] = []
    is_json_invalid = False

    for err in raw_errors:
        if err.get("type") == "json_invalid":
            is_json_invalid = True
        field = _extract_field_name(err.get("loc", ()))
        message = _translate_validation_error(err)
        formatted_errors.append({"field": field, "message": message})

    if is_json_invalid:
        detail = "El cuerpo de la petición no es un JSON válido"
    else:
        detail = "Error de validación en los datos enviados"

    return JSONResponse(
        status_code=422,
        content={
            "detail": detail,
            "errors": formatted_errors,
        },
    )


async def unhandled_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    logger.exception(
        "Unhandled server exception on %s %s",
        request.method,
        request.url.path,
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Error interno del servidor"},
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)

