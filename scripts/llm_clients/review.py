#!/usr/bin/env python3
"""
Unified plan review orchestrator.

Usage:
  uv run review.py --planning-dir /path/to/planning

Checks which LLMs are available (Gemini, OpenAI) and runs reviews in parallel.
Writes results to <planning_dir>/reviews/ directory.

Returns JSON with combined results from all available reviewers.
"""

import sys
import os
import json
import time
import argparse
import subprocess
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

# Add parent to path for lib imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from lib.config import load_session_config
from lib.prompts import load_prompts, format_prompt


def get_env(name, default=None):
    """Read env with DEEPPLAN_ override precedence."""
    return os.environ.get(f"DEEPPLAN_{name}") or os.environ.get(name, default)


def load_plan(planning_dir: Path) -> str:
    """Load claude-plan.md from planning directory."""
    plan_file = planning_dir / "claude-plan.md"
    if not plan_file.exists():
        raise FileNotFoundError(f"Required file not found: {plan_file}")
    return plan_file.read_text()


def call_with_retry(func, config):
    """Call function with retry logic from config."""
    llm_config = config["llm_client"]
    max_retries = llm_config["max_retries"]
    retry_codes = llm_config["retry_codes"]

    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            error_code = getattr(e, 'status_code', None) or getattr(e, 'code', None)
            if error_code in retry_codes and attempt < max_retries - 1:
                wait = 2 ** attempt
                time.sleep(wait)
                continue
            raise


def get_gemini_client(config: dict):
    """Create Gemini client using API key or ADC with Vertex AI."""
    try:
        from google import genai
    except ImportError:
        return None, "not_installed"

    # Option 1: API Key
    api_key = get_env("GEMINI_API_KEY")
    if api_key:
        client = genai.Client(api_key=api_key)
        return client, "api_key"

    # Option 2: ADC with Vertex AI
    vertex_config = config.get("vertex_ai", {})

    project = vertex_config.get("project")
    if not project:
        try:
            result = subprocess.run(
                ["gcloud", "config", "get-value", "project"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                project = result.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

    if not project:
        project = get_env("GOOGLE_CLOUD_PROJECT")

    location = vertex_config.get("location") or get_env("GOOGLE_CLOUD_LOCATION")

    adc_path = Path.home() / ".config/gcloud/application_default_credentials.json"
    google_creds = get_env("GOOGLE_APPLICATION_CREDENTIALS")
    has_adc = (google_creds and Path(google_creds).exists()) or adc_path.exists()

    if has_adc and project and location:
        # Validate ADC credentials are not stale (mirrors validate-env.sh)
        try:
            result = subprocess.run(
                ["gcloud", "auth", "application-default", "print-access-token"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode != 0:
                return None, "adc_stale"
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return None, "adc_validation_failed"

        try:
            client = genai.Client(vertexai=True, project=project, location=location)
            return client, "vertex_ai_adc"
        except Exception as e:
            return None, f"adc_error: {e}"

    return None, None


def check_openai_available() -> bool:
    """Check if OpenAI API key is available."""
    return bool(get_env("OPENAI_API_KEY"))


def review_with_gemini(plan_content: str, system_prompt: str, user_prompt: str, config: dict) -> dict:
    """Run Gemini review."""
    client, auth_method = get_gemini_client(config)

    if not client:
        return {"success": False, "provider": "gemini", "error": f"No auth available: {auth_method}"}

    model_name = get_env("GEMINI_MODEL") or config["models"]["gemini"]

    try:
        response = call_with_retry(
            lambda: client.models.generate_content(
                model=model_name,
                contents=user_prompt,
                config={"system_instruction": system_prompt}
            ),
            config
        )
        return {
            "success": True,
            "provider": "gemini",
            "model": model_name,
            "auth_method": auth_method,
            "analysis": response.text
        }
    except Exception as e:
        return {
            "success": False,
            "provider": "gemini",
            "model": model_name,
            "error": str(e)
        }


def review_with_openai(plan_content: str, system_prompt: str, user_prompt: str, config: dict) -> dict:
    """Run OpenAI review."""
    # DEEPPLAN_OPENAI_ prefix takes precedence over standard OPENAI_ variables
    api_key = get_env("OPENAI_API_KEY")
    if not api_key:
        return {"success": False, "provider": "openai", "error": "OPENAI_API_KEY not set"}

    try:
        from openai import OpenAI
    except ImportError:
        return {"success": False, "provider": "openai", "error": "openai package not installed"}

    model_name = get_env("OPENAI_MODEL") or config["models"]["chatgpt"]
    timeout = config["llm_client"]["timeout_seconds"]

    # Support custom base URL for OpenAI-compatible APIs (LiteLLM, LocalAI, etc.)
    base_url = get_env("OPENAI_BASE_URL")

    try:
        if base_url:
            client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout)
        else:
            client = OpenAI(api_key=api_key, timeout=timeout)

        response = call_with_retry(
            lambda: client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ]
            ),
            config
        )
        return {
            "success": True,
            "provider": "openai",
            "model": model_name,
            "base_url": base_url,
            "analysis": response.choices[0].message.content
        }
    except Exception as e:
        return {
            "success": False,
            "provider": "openai",
            "model": model_name,
            "base_url": base_url,
            "error": str(e)
        }


def write_review_file(reviews_dir: Path, provider: str, iteration: int, result: dict) -> Path:
    """Write review result to file."""
    reviews_dir.mkdir(parents=True, exist_ok=True)
    filename = f"iteration-{iteration}-{provider}.md"
    filepath = reviews_dir / filename

    if result["success"]:
        content = f"""# {provider.title()} Review

**Model:** {result.get('model', 'unknown')}
**Generated:** {datetime.now().isoformat()}

---

{result['analysis']}
"""
    else:
        content = f"""# {provider.title()} Review - FAILED

**Error:** {result.get('error', 'unknown error')}
**Generated:** {datetime.now().isoformat()}
"""

    filepath.write_text(content)
    return filepath


def main():
    parser = argparse.ArgumentParser(description="Run plan reviews with available LLMs")
    parser.add_argument("--planning-dir", required=True, type=Path, help="Path to planning directory")
    parser.add_argument("--iteration", type=int, default=1, help="Review iteration number")
    args = parser.parse_args()

    # Load plan
    try:
        plan_content = load_plan(args.planning_dir)
    except FileNotFoundError as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)

    config = load_session_config(args.planning_dir)

    # Load prompts from plugin_root (stored in session config)
    plugin_root = config.get("plugin_root", Path(__file__).parent.parent.parent)
    prompts_dir = Path(plugin_root) / "prompts" / "plan_reviewer"
    system_prompt, user_template, _ = load_prompts(str(prompts_dir))
    user_prompt = format_prompt(user_template, PLAN_CONTENT=plan_content)

    # Check which LLMs are available
    gemini_client, gemini_auth = get_gemini_client(config)
    gemini_available = gemini_client is not None
    openai_available = check_openai_available()

    if not gemini_available and not openai_available:
        print(json.dumps({
            "error": "No LLM providers available",
            "gemini_status": gemini_auth or "no_auth",
            "openai_status": "no_api_key"
        }))
        sys.exit(1)

    # Prepare review tasks
    results = {}
    reviews_dir = args.planning_dir / "reviews"

    if gemini_available and openai_available:
        # Run both in parallel
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = {
                executor.submit(review_with_gemini, plan_content, system_prompt, user_prompt, config): "gemini",
                executor.submit(review_with_openai, plan_content, system_prompt, user_prompt, config): "openai"
            }
            for future in as_completed(futures):
                provider = futures[future]
                try:
                    results[provider] = future.result()
                except Exception as e:
                    results[provider] = {"success": False, "provider": provider, "error": str(e)}
    elif gemini_available:
        results["gemini"] = review_with_gemini(plan_content, system_prompt, user_prompt, config)
    else:
        results["openai"] = review_with_openai(plan_content, system_prompt, user_prompt, config)

    # Write review files
    files_written = []
    for provider, result in results.items():
        filepath = write_review_file(reviews_dir, provider, args.iteration, result)
        files_written.append(str(filepath))

    # Output summary
    output = {
        "reviews": results,
        "files_written": files_written,
        "gemini_available": gemini_available,
        "openai_available": openai_available
    }

    print(json.dumps(output, indent=2))

    # Exit with error if all reviews failed
    all_failed = all(not r.get("success", False) for r in results.values())
    sys.exit(1 if all_failed else 0)


if __name__ == "__main__":
    main()
