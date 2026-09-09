"""stdio MCP server: bounded tool responses and persistent background jobs."""
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field

from .jobs import JobManager, check_environment as inspect_environment

mcp = FastMCP("videocaptioner", instructions="Local media workflow. Transcription uses MLX; the client must proofread, segment and translate caption batches. Do not use a translation API or computer control.")
manager = JobManager()


class Caption(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start_word_id: str
    end_word_id: str
    source: str = Field(min_length=1)
    translation: str = Field(min_length=1)


@mcp.tool()
def check_environment(model: str | None = None) -> dict:
    """Check local MLX model, Python packages and FFmpeg; does not download models."""
    return inspect_environment(model)


@mcp.tool()
def start_job(url: str, source_language: str = "en", target_language: str = "zh-CN",
              output_dir: str | None = None, model: str | None = None, format_selector: str = "",
              proxy_url: str | None = None, cookie_file: str | None = None, initial_prompt: str = "") -> dict:
    """Start one video download and native MLX transcription in a background process. Returns job ID immediately. Empty proxy_url disables proxy; None uses saved settings. Source auto detects language."""
    return manager.start_job(url, source_language, target_language, output_dir, model, format_selector, proxy_url, cookie_file, initial_prompt)


@mcp.tool()
def get_job(job_id: str) -> dict:
    """Read progress, errors, completed batch counts and output paths. Poll every 5-15 seconds during local processing."""
    return manager.get_job(job_id)


@mcp.tool()
def list_jobs(limit: int = 20) -> list[dict]:
    """List recent persistent jobs to find and resume work after a conversation interruption."""
    return manager.list_jobs(limit)


@mcp.tool()
def get_caption_batch(job_id: str, batch_id: str | None = None) -> dict:
    """Read next untranslated batch (or a specific batch), immutable word IDs, original timestamps, context and glossary."""
    return manager.get_caption_batch(job_id, batch_id)


@mcp.tool()
def submit_caption_batch(job_id: str, batch_id: str, revision: int, captions: list[Caption],
                         glossary: dict[str, str] | None = None, notes: list[str] | None = None) -> dict:
    """Save Codex's proofreading, semantic segments and translations. Cover batch words exactly once with inclusive continuous ID ranges. Time is computed locally. Exact retries are idempotent; changed stale revisions are rejected. Notes record uncertain transcription."""
    return manager.submit_caption_batch(job_id, batch_id, revision, [c.model_dump() for c in captions], glossary, notes)


@mcp.tool()
def retranscribe_range(job_id: str, start_word_id: str, end_word_id: str, revision: int, initial_prompt: str = "") -> dict:
    """Start local MLX re-transcription; expands to complete affected batches. Replaces their word IDs, invalidates their translations, and retains other completed batches. Fetch new batch IDs afterwards."""
    return manager.retranscribe_range(job_id, start_word_id, end_word_id, revision, initial_prompt)


@mcp.tool()
def validate_job(job_id: str) -> dict:
    """Check complete translation coverage, word timing, overlapping captions and reading speed. Structural errors block export; warnings require review."""
    return manager.validate_job(job_id)


@mcp.tool()
def get_cover_source(job_id: str) -> dict:
    """Return the downloaded original thumbnail path and the constrained GPT image-edit brief."""
    return manager.get_cover_source(job_id)


@mcp.tool()
def set_generated_cover(job_id: str, image_path: str) -> dict:
    """Validate a locally generated 4:3 cover and save it into this job for final export."""
    return manager.set_generated_cover(job_id, image_path)


@mcp.tool()
def export_job(job_id: str) -> dict:
    """Export named original/translated SRT, proofread source transcript, template description and final video into <title>/output."""
    return manager.export_job(job_id)


@mcp.tool()
def cancel_job(job_id: str) -> dict:
    """Stop only this job's worker and subprocesses, retaining checkpoints and downloaded partial files."""
    return manager.cancel_job(job_id)


@mcp.tool()
def resume_job(job_id: str) -> dict:
    """Resume failed/interrupted/cancelled work from completed stages without repeating accepted caption batches."""
    return manager.resume_job(job_id)


if __name__ == "__main__":
    mcp.run(transport="stdio")
