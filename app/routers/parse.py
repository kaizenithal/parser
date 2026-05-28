import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from ..models import CodeParsingResult, Language, ParseRequest
from ..parsers.factory import get_parser
from ..parsers.transformer import transform

logger = logging.getLogger("parser-service")

router = APIRouter()

# 50MB ceiling — explicit, not silent. Matches the uvicorn --limit-request-body flag.
MAX_REQUEST_BYTES = 50 * 1024 * 1024


async def _parse_request(request: Request) -> ParseRequest | JSONResponse:
    """Shared request validation for both endpoints."""
    body = await request.body()

    if len(body) > MAX_REQUEST_BYTES:
        return JSONResponse(
            status_code=413,
            content={
                "detail": (
                    f"Request body is {len(body):,} bytes, "
                    f"maximum is {MAX_REQUEST_BYTES:,} bytes ({MAX_REQUEST_BYTES // (1024 * 1024)}MB)"
                )
            },
        )

    try:
        return ParseRequest.model_validate_json(body)
    except ValidationError as exc:
        return JSONResponse(
            status_code=422,
            content={"detail": exc.errors()},
        )


def _do_parse(parse_request: ParseRequest) -> CodeParsingResult:
    """Run the parser and log results."""
    logger.info(
        "Parsing %s file: %s (%d bytes)",
        parse_request.language.value,
        parse_request.file_path,
        len(parse_request.source_text),
    )

    parser = get_parser(parse_request.language)
    result = parser.parse(parse_request.source_text, parse_request.file_path)

    if result.warnings:
        logger.warning(
            "Parse warnings for %s: %s",
            parse_request.file_path,
            result.warnings,
        )

    return result


@router.post("", response_model=CodeParsingResult)
async def parse_code(request: Request):
    """Parse source code and return the raw flat CodeUnit list."""
    parsed = await _parse_request(request)
    if isinstance(parsed, JSONResponse):
        return parsed
    return _do_parse(parsed)


@router.post("/structured", response_model=CodeParsingResult)
async def parse_code_structured(request: Request):
    """Parse source code and return a RAG-optimized hierarchical structure.

    The Module becomes a container with shared imports, and each top-level
    unit (Class, Function, Declaration) carries its full child hierarchy.
    """
    parsed = await _parse_request(request)
    if isinstance(parsed, JSONResponse):
        return parsed
    result = _do_parse(parsed)
    return transform(result)