from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VENV_PY = ROOT / "venv" / "bin" / "python"


class CheckFailed(RuntimeError):
    pass


def _run(cmd: list[str], cwd: Path | None = None, timeout: int = 180) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=str(cwd or ROOT), capture_output=True, text=True, timeout=timeout)


def _print_result(name: str, ok: bool, detail: str) -> None:
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {name}: {detail}")


def _python() -> str:
    if VENV_PY.exists():
        return str(VENV_PY)
    return sys.executable


def _docker_available() -> bool:
    return bool(shutil.which("docker")) and _run(["docker", "ps"], timeout=15).returncode == 0


def _container_exists(name: str) -> bool:
    proc = _run(["docker", "ps", "-a", "--filter", f"name=^/{name}$", "--format", "{{.Names}}"], timeout=15)
    return proc.returncode == 0 and name in (proc.stdout or "")


def _run_required(name: str, cmd: list[str], timeout: int = 240) -> None:
    proc = _run(cmd, timeout=timeout)
    if proc.returncode != 0:
        _print_result(name, False, (proc.stderr or proc.stdout or "failed").strip().splitlines()[-1][:220])
        raise CheckFailed(name)
    tail = (proc.stdout or "").strip().splitlines()
    _print_result(name, True, tail[-1][:220] if tail else "ok")


def _run_optional(name: str, cmd: list[str], why: str, timeout: int = 240) -> None:
    try:
        proc = _run(cmd, timeout=timeout)
    except Exception as exc:
        _print_result(name, True, f"SKIP ({why}: {exc})")
        return
    if proc.returncode != 0:
        _print_result(name, True, f"SKIP ({why}: non-zero)")
        return
    tail = (proc.stdout or "").strip().splitlines()
    _print_result(name, True, tail[-1][:220] if tail else "ok")


def _py_compile_changed(py: str) -> None:
    proc = _run(["git", "diff", "--name-only", "--", "*.py"])
    files = [x.strip() for x in (proc.stdout or "").splitlines() if x.strip().endswith(".py")]
    if not files:
        _print_result("py_compile_changed", True, "no changed python files")
        return
    failed: list[str] = []
    for rel in files:
        p = ROOT / rel
        c = _run([py, "-m", "py_compile", str(p)], timeout=60)
        if c.returncode != 0:
            failed.append(rel)
    if failed:
        _print_result("py_compile_changed", False, f"failed: {', '.join(failed[:5])}")
        raise CheckFailed("py_compile_changed")
    _print_result("py_compile_changed", True, f"compiled {len(files)} file(s)")


def _run_e2e_memory_isolated(py: str) -> None:
    candidate_path = ROOT / "runtime" / "assistant" / "memory" / "runtime" / "candidates.jsonl"
    backup = candidate_path.with_suffix(".jsonl.bak.validate")
    try:
        if candidate_path.exists():
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(candidate_path, backup)
        candidate_path.parent.mkdir(parents=True, exist_ok=True)
        candidate_path.write_text("", encoding="utf-8")
        _run_required("e2e_memory_handler", [py, "runtime/assistant/jobs/e2e_memory_handler.py"])
    finally:
        if backup.exists():
            shutil.move(str(backup), str(candidate_path))


def main() -> int:
    py = _python()
    print(f"host_python={py}")
    _run_required("host_python_version", [py, "-c", "import sys;print(sys.version.split()[0])"]) 
    _run_required("host_import_telegram", [py, "-c", "import telegram; print('telegram_ok')"]) 
    _run_required("host_import_mcp", [py, "-c", "import mcp; print('mcp_ok')"]) 

    _run_required("git_status_sb", ["git", "status", "-sb"])
    _run_required("git_status_ignored", ["git", "status", "--ignored", "-sb"])
    _run_required("git_diff_check", ["git", "diff", "--check"])
    _py_compile_changed(py)

    diff = _run(["git", "diff", "-U0"]).stdout or ""
    secret_pattern = re.compile(r"(AKIA|ASIA|SECRET|TOKEN|PASSWORD|PRIVATE KEY|BEGIN RSA|BEGIN OPENSSH|xoxb-|ghp_|github_pat_|sk-[A-Za-z0-9]|HERMES_LLM_API_KEY|TELEGRAM_BOT_TOKEN)", re.I)
    secret_hits = [line for line in diff.splitlines() if secret_pattern.search(line)]
    if secret_hits:
        _print_result("secret_scan", False, secret_hits[0][:220])
        raise CheckFailed("secret_scan")
    _print_result("secret_scan", True, "clean")

    mutation_pattern = re.compile(r"paos_memory_write|controlled_write_apply|github.*(mutat|write|push|commit|merge|create issue|pull request)|public api|tunnel|enable hermes gateway|gateway.*start|crontab|systemctl.*enable|scheduler.*write", re.I)
    mutation_hits = [line for line in diff.splitlines() if mutation_pattern.search(line)]
    mutation_hits = [
        line
        for line in mutation_hits
        if "Do not mutate GitHub" not in line
        and "No GitHub mutation" not in line
        and "Tidak ada commit/push" not in line
        and "enable/start Hermes gateway" not in line
        and "gateway must remain stopped" not in line.lower()
    ]
    if mutation_hits:
        _print_result("mutation_safety_scan", False, mutation_hits[0][:220])
        raise CheckFailed("mutation_safety_scan")
    _print_result("mutation_safety_scan", True, "clean")

    _run_required("runtime_status_smoke", [py, "-c", "import sys;sys.path.insert(0,'runtime');from assistant.mcp.server import tool_paos_runtime_status_get as f;print((f().get('sections') or {}).get('hermes_gateway_status'))"]) 
    _run_required("smoke_action_loop", [py, "runtime/assistant/jobs/smoke_action_loop.py"])
    _run_required("e2e_action_loop_handler", [py, "runtime/assistant/jobs/e2e_action_loop_handler.py"])
    _run_e2e_memory_isolated(py)
    _run_required("smoke_agent_orchestration", [py, "runtime/assistant/jobs/smoke_agent_orchestration.py"])
    _run_required("e2e_agent_orchestration_handler", [py, "runtime/assistant/jobs/e2e_agent_orchestration_handler.py"])

    _run_required("source_status_smoke", [py, "-c", "import sys;sys.path.insert(0,'runtime');from assistant.mcp.server import tool_paos_source_status_get as f;print(f().get('status'))"]) 
    _run_required("operating_summary_smoke", [py, "-c", "import sys;sys.path.insert(0,'runtime');from assistant.mcp.server import tool_paos_operating_summary_get as f;print(f(category='ai').get('status'))"]) 
    _run_required("daily_plan_smoke", [py, "-c", "import sys;sys.path.insert(0,'runtime');from assistant.mcp.server import tool_paos_daily_plan_get as f;print(f(category='ai').get('status'))"]) 

    _run_required("mcp_import_smoke", [py, "-c", "import sys;sys.path.insert(0,'runtime');from assistant.mcp.server import tool_paos_agent_handoff_create,tool_paos_agent_result_review;print(bool(tool_paos_agent_handoff_create(target_agent='codex').get('ok')) and bool(tool_paos_agent_result_review(content='pass').get('ok')))"], timeout=120)

    if _docker_available() and _container_exists("paos-hermes"):
        _run_required(
            "hermes_mcp_interpreter",
            ["docker", "exec", "paos-hermes", "sh", "-lc", "test -x /opt/hermes/.venv/bin/python && echo /opt/hermes/.venv/bin/python"],
        )
        _run_required("docker_mcp_smoke", [py, "runtime/assistant/jobs/smoke_hermes_mcp_container.py"])
        gw = _run(
            ["docker", "exec", "paos-hermes", "sh", "-lc", "/workspace/paos-runtime/runtime/assistant/hermes/run_hermes.sh gateway status"],
            timeout=60,
        )
        gateway_output = f"{gw.stdout}\n{gw.stderr}".strip()
        gw_ok = gw.returncode == 0 and "Gateway is not running" in gateway_output
        _print_result("container_gateway_status", gw_ok, "Gateway is not running" if gw_ok else gateway_output.splitlines()[-1][:220])
        if not gw_ok:
            raise CheckFailed("container_gateway_status")
    else:
        _print_result("docker_mcp_smoke", True, "SKIP (docker/container unavailable)")

    _run_required(
        "runtime_artifact_ignore_audit",
        ["bash", "-lc", "git check-ignore -v assistant/action-loop/actions.jsonl assistant/action-loop/events.jsonl assistant/action-loop/index.json runtime/assistant/memory/local.jsonl runtime/assistant/memory/runtime/.gitkeep intelligence/raw/.gitkeep >/dev/null && echo ignored_ok"],
    )

    status = _run([py, "-c", "import sys;sys.path.insert(0,'runtime');from assistant.mcp.server import tool_paos_runtime_status_get as f;p=f();s=p.get('sections') or {};print(f\"hermes_gateway_status={s.get('hermes_gateway_status')} gateway_running={s.get('gateway_running')}\")"]) 
    if status.returncode != 0:
        raise CheckFailed("final_gateway_status")
    summary = (status.stdout or "").strip()
    ok = "hermes_gateway_status=stopped_expected" in summary and "gateway_running=False" in summary
    _print_result("final_gateway_status", ok, summary)
    if not ok:
        raise CheckFailed("final_gateway_status")

    print("validate_commit_readiness: PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CheckFailed:
        raise SystemExit(2)
