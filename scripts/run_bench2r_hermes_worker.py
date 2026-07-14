from __future__ import annotations

import argparse
import io
import json
import os
import sys
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any, Iterator


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return repr(value)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(_json_safe(value), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _usage_from_result(result: dict[str, Any], failure: str | None) -> dict[str, Any]:
    usage = {
        key: result.get(key)
        for key in (
            "estimated_cost_usd",
            "cost_status",
            "cost_source",
            "input_tokens",
            "output_tokens",
            "cache_read_tokens",
            "cache_write_tokens",
            "reasoning_tokens",
            "total_tokens",
            "api_calls",
            "model",
            "provider",
            "session_id",
            "completed",
        )
    }
    usage["failed"] = bool(result.get("failed")) or failure is not None
    if failure is not None:
        usage["failure"] = failure
    return usage


@contextmanager
def _force_native_trajectory_capture() -> Iterator[None]:
    """Force the pinned oneshot-created AIAgent to save its native trajectory."""
    from run_agent import AIAgent

    original_init = AIAgent.__init__

    def trajectory_init(self, *args, **kwargs):
        kwargs["save_trajectories"] = True
        return original_init(self, *args, **kwargs)

    AIAgent.__init__ = trajectory_init
    try:
        yield
    finally:
        AIAgent.__init__ = original_init


def _selected_toolsets(toolset: str) -> list[str]:
    # Preserve the reviewed S1 default as an explicit runtime branch while
    # allowing S2 to select its isolated held-out toolset.
    if toolset == "bench2_fixture":
        toolsets=["bench2_fixture"]
    else:
        toolsets = [toolset]
    return toolsets


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run one observed Hermes conversation for BENCH-2R."
    )
    parser.add_argument("--model", required=True)
    parser.add_argument("--arm", choices=("profile_only", "profile_plus_skill"), required=True)
    parser.add_argument("--toolset", default="bench2_fixture")
    parser.add_argument("--prompt-file", type=Path, required=True)
    parser.add_argument("--usage-file", type=Path, required=True)
    parser.add_argument("--result-file", type=Path, required=True)
    parser.add_argument("--debug-file", type=Path, required=True)
    args = parser.parse_args()

    if not args.toolset.strip():
        parser.error("--toolset must be non-empty")
    selected_toolsets = _selected_toolsets(args.toolset)

    os.environ["HERMES_YOLO_MODE"] = "1"
    os.environ["HERMES_ACCEPT_HOOKS"] = "1"

    prompt = args.prompt_file.read_text(encoding="utf-8")
    skill_expanded = False
    trajectory_capture_forced = False
    failure: str | None = None
    result: dict[str, Any] = {}
    response = ""
    debug_stdout = io.StringIO()
    debug_stderr = io.StringIO()

    try:
        if args.arm == "profile_plus_skill":
            from agent.skill_commands import (
                build_skill_invocation_message,
                scan_skill_commands,
            )

            scan_skill_commands()
            expanded = build_skill_invocation_message(
                "/bounded-tool-orchestration",
                user_instruction=prompt,
            )
            if not isinstance(expanded, str) or not expanded.strip():
                raise RuntimeError("bounded-tool-orchestration skill expansion failed")
            prompt = expanded
            skill_expanded = True

        from hermes_cli.oneshot import _run_agent

        with _force_native_trajectory_capture():
            trajectory_capture_forced = True
            with redirect_stdout(debug_stdout), redirect_stderr(debug_stderr):
                response, result = _run_agent(
                    prompt,
                    model=args.model,
                    provider="custom",
                    toolsets=selected_toolsets,
                    use_config_toolsets=False,
                )
    except BaseException as exc:  # noqa: BLE001 - worker must persist evidence
        failure = f"{type(exc).__name__}: {exc}"

    args.debug_file.parent.mkdir(parents=True, exist_ok=True)
    args.debug_file.write_text(
        "=== CAPTURED STDOUT ===\n"
        + debug_stdout.getvalue()
        + "\n=== CAPTURED STDERR ===\n"
        + debug_stderr.getvalue(),
        encoding="utf-8",
    )
    payload = {
        "arm": args.arm,
        "toolset": args.toolset,
        "failure": failure,
        "final_response": response,
        "messages": result.get("messages"),
        "api_calls": result.get("api_calls"),
        "completed": result.get("completed"),
        "failed": result.get("failed"),
        "partial": result.get("partial"),
        "turn_exit_reason": result.get("turn_exit_reason"),
        "model": result.get("model"),
        "provider": result.get("provider"),
        "base_url": result.get("base_url"),
        "skill_expanded": skill_expanded,
        "trajectory_capture_forced": trajectory_capture_forced,
        "input_tokens": result.get("input_tokens"),
        "output_tokens": result.get("output_tokens"),
        "reasoning_tokens": result.get("reasoning_tokens"),
        "total_tokens": result.get("total_tokens"),
        "schema_version": "bench.hermes-s1-worker-result.v1",
    }
    _write_json(args.result_file, payload)
    _write_json(args.usage_file, _usage_from_result(result, failure))

    if response:
        sys.stdout.write(response)
        if not response.endswith("\n"):
            sys.stdout.write("\n")
        sys.stdout.flush()

    if failure is not None:
        sys.stderr.write(failure + "\n")
        return 1
    if not response.strip():
        sys.stderr.write("worker produced no final response\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
