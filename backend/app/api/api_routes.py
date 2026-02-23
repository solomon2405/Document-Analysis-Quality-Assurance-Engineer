from __future__ import annotations

import asyncio
import hashlib
import logging
import time
import uuid
from dataclasses import dataclass, field
from tempfile import SpooledTemporaryFile

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.config import settings
from app.schemas import ComparisonResponse, JobCreateResponse, JobStatusResponse
from app.services.diff_engine import run_diff_layers
from app.services.ingestion_service import ingest_files
from app.services.report_generator import assemble_response
from app.services.risk_analyzer import assess_risk
from app.services.semantic_engine import run_semantic_layer

logger = logging.getLogger(__name__)
router = APIRouter()


@dataclass(slots=True)
class JobState:
    job_id: str
    status: str = "queued"
    stage_progress: dict[str, int] = field(
        default_factory=lambda: {
            "ingestion": 0,
            "structural": 0,
            "lexical": 0,
            "ocr": 0,
            "semantic": 0,
            "risk": 0,
            "report": 0,
        }
    )
    error: str | None = None
    result: ComparisonResponse | None = None
    created_at: float = field(default_factory=time.time)


_JOBS: dict[str, JobState] = {}
_CACHE: dict[str, tuple[float, ComparisonResponse]] = {}
_LOCK = asyncio.Lock()


def _validate_files(files: list[UploadFile], label: str) -> None:
    if not files:
        raise HTTPException(status_code=400, detail=f"{label} files are required.")
    if len(files) > settings.max_files_per_side:
        raise HTTPException(status_code=400, detail=f"{label} exceeds {settings.max_files_per_side} files.")


async def _read_and_hash(files: list[UploadFile]) -> tuple[list[tuple[str, bytes]], str]:
    ordered = sorted(files, key=lambda f: (f.filename or "").lower())
    entries: list[tuple[str, bytes]] = []
    digest = hashlib.sha256()
    for f in ordered:
        data = await f.read()
        if len(data) > settings.max_file_size_mb * 1024 * 1024:
            raise HTTPException(status_code=400, detail=f"File {f.filename} exceeds size limit.")
        name = f.filename or "unknown"
        entries.append((name, data))
        digest.update(name.encode("utf-8", errors="ignore"))
        digest.update(data)
    return entries, digest.hexdigest()


def _clone_uploads(payload: list[tuple[str, bytes]]) -> list[UploadFile]:
    clones: list[UploadFile] = []
    for name, data in payload:
        spooled = SpooledTemporaryFile()
        spooled.write(data)
        spooled.seek(0)
        uf = UploadFile(file=spooled, filename=name)
        clones.append(uf)
    return clones


def _cleanup_cache() -> None:
    now = time.time()
    expired = [k for k, (ts, _) in _CACHE.items() if now - ts > settings.cache_ttl_seconds]
    for k in expired:
        _CACHE.pop(k, None)
    if len(_CACHE) <= settings.max_cached_results:
        return
    for key in sorted(_CACHE, key=lambda x: _CACHE[x][0])[: len(_CACHE) - settings.max_cached_results]:
        _CACHE.pop(key, None)


async def _run_pipeline(job_id: str, input_payload: list[tuple[str, bytes]], output_payload: list[tuple[str, bytes]], cache_key: str) -> None:
    job = _JOBS[job_id]
    job.status = "processing"
    try:
        async with _LOCK:
            _cleanup_cache()
            cached = _CACHE.get(cache_key)
        if cached and (time.time() - cached[0]) < settings.cache_ttl_seconds:
            job.result = cached[1]
            job.stage_progress = {k: 100 for k in job.stage_progress}
            job.status = "completed"
            return

        input_files = _clone_uploads(input_payload)
        output_files = _clone_uploads(output_payload)
        job.stage_progress["ingestion"] = 25
        input_doc, output_doc = await asyncio.gather(
            ingest_files(input_files, side="input"),
            ingest_files(output_files, side="output"),
        )
        job.stage_progress["ingestion"] = 100

        diff = run_diff_layers(input_doc, output_doc)
        job.stage_progress["structural"] = diff.stage_progress["structural"]
        job.stage_progress["lexical"] = diff.stage_progress["lexical"]
        job.stage_progress["ocr"] = diff.stage_progress["ocr"]

        semantic_score, semantic_mismatches, semantic_critical = run_semantic_layer(input_doc, output_doc)
        job.stage_progress["semantic"] = 100

        all_mismatches = diff.mismatches + semantic_mismatches
        critical_changes = diff.critical_changes + semantic_critical

        risk = assess_risk(all_mismatches, critical_changes, semantic_score)
        job.stage_progress["risk"] = 100

        overall_similarity = (0.4 * diff.lexical_similarity) + (0.3 * diff.structural_similarity) + (0.3 * semantic_score)
        response = assemble_response(
            overall_similarity_score=overall_similarity,
            structural_similarity=diff.structural_similarity,
            semantic_similarity=semantic_score,
            risk_assessment=risk,
            critical_changes=critical_changes,
            mismatches=all_mismatches,
            entity_comparison_rows=diff.entity_table,
            stage_progress={k: 100 for k in job.stage_progress},
            input_files=input_doc.source_files,
            output_files=output_doc.source_files,
        )

        job.result = response
        job.stage_progress["report"] = 100
        job.status = "completed"
        async with _LOCK:
            _CACHE[cache_key] = (time.time(), response)
    except Exception as exc:
        logger.exception("Pipeline failed for job %s", job_id)
        job.status = "failed"
        job.error = str(exc)


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/compare/jobs", response_model=JobCreateResponse)
async def create_compare_job(
    input_files: list[UploadFile] = File(...),
    output_files: list[UploadFile] = File(...),
) -> JobCreateResponse:
    _validate_files(input_files, "Input")
    _validate_files(output_files, "Output")

    input_payload, input_hash = await _read_and_hash(input_files)
    output_payload, output_hash = await _read_and_hash(output_files)
    cache_key = f"{input_hash}:{output_hash}"

    job_id = str(uuid.uuid4())
    _JOBS[job_id] = JobState(job_id=job_id)
    asyncio.create_task(_run_pipeline(job_id, input_payload, output_payload, cache_key))
    return JobCreateResponse(job_id=job_id, status="queued")


@router.get("/compare/jobs/{job_id}", response_model=JobStatusResponse)
async def get_compare_job(job_id: str) -> JobStatusResponse:
    job = _JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    return JobStatusResponse(
        job_id=job.job_id,
        status=job.status,  # type: ignore[arg-type]
        stage_progress=job.stage_progress,
        error=job.error,
        result=job.result,
    )


@router.post("/compare", response_model=ComparisonResponse)
async def compare_direct(
    input_files: list[UploadFile] = File(...),
    output_files: list[UploadFile] = File(...),
) -> ComparisonResponse:
    create = await create_compare_job(input_files=input_files, output_files=output_files)
    deadline = time.time() + 180
    while time.time() < deadline:
        status = await get_compare_job(create.job_id)
        if status.status == "completed" and status.result:
            return status.result
        if status.status == "failed":
            raise HTTPException(status_code=500, detail=status.error or "Comparison failed")
        await asyncio.sleep(0.35)
    raise HTTPException(status_code=504, detail="Comparison timed out")
