from __future__ import annotations

from pathlib import Path

from scripts import bench3r_mr0_contract as K
from scripts.bench3r_mr0_io import git_blob_sha, load_object, read_text, require

ROOT = Path(__file__).resolve().parents[1]
TOOLSET = ROOT / "fixtures/bench-3r/mr0-synthetic-toolset.json"
EXPECTED_BOUNDARIES = {
    "case_local_only": True,
    "external_io": False,
    "model_launch": False,
    "persistent_changes": False,
}
EXPECTED_TOOLS = [
    {
        "name": "mr0_session_search",
        "inputs": ["query", "synthetic_corpus_id"],
        "outputs": ["matches", "evidence_ids"],
        "effects": "none",
        "model_launch": False,
        "terminal": False,
    },
    {
        "name": "mr0_memory_proposal",
        "inputs": ["target", "operation", "content", "evidence_ids"],
        "outputs": ["proposal_id", "proposal_status"],
        "effects": "proposal_only",
        "model_launch": False,
        "terminal": False,
    },
    {
        "name": "mr0_route_request",
        "inputs": ["lane", "requirements", "completion_contract"],
        "outputs": ["request_id", "request_status"],
        "effects": "request_only",
        "model_launch": False,
        "terminal": False,
    },
    {
        "name": "mr0_profile_resolve",
        "inputs": ["lane"],
        "outputs": ["profile_id", "model_digest", "context_length", "toolset_id"],
        "effects": "none",
        "model_launch": False,
        "terminal": False,
    },
    {
        "name": "mr0_finish",
        "inputs": ["decision_object"],
        "outputs": ["terminal_status"],
        "effects": "none",
        "model_launch": False,
        "terminal": True,
    },
]


def validate_toolset() -> dict[str, str]:
    payload = load_object(TOOLSET)
    require(payload.get("schema_version") == K.TOOLSET_SCHEMA, "toolset schema drifted")
    require(payload.get("toolset_id") == K.STACK["toolset"], "toolset id drifted")
    require(payload.get("scope") == "case_local_simulation", "toolset scope drifted")
    require(payload.get("boundaries") == EXPECTED_BOUNDARIES, "toolset boundaries drifted")
    require(payload.get("tools") == EXPECTED_TOOLS, "tool inventory or contract drifted")
    return {
        "synthetic_toolset_path": TOOLSET.relative_to(ROOT).as_posix(),
        "synthetic_toolset_git_blob_sha": git_blob_sha(read_text(TOOLSET)),
    }
