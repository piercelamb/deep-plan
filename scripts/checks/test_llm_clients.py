#!/usr/bin/env python3
"""
Test LLM client construction AND model access with pre-validated auth.

Called by validate-env.sh AFTER it has validated that credentials exist.
This script validates that:
1. Clients can be constructed (auth works)
2. The specific model from config.json is accessible

Usage:
  uv run test_llm_clients.py --gemini-api-key MODEL      # Test Gemini API key + model
  uv run test_llm_clients.py --vertex-ai PROJECT LOC MODEL  # Test Vertex AI + model
  uv run test_llm_clients.py --openai MODEL              # Test OpenAI + model

Returns JSON with test results. Exit 0 if tested clients work, 1 if any fail.
"""

import sys
import os
import json
import argparse


def test_gemini_api_key(model: str) -> dict:
    """Test Gemini client with API key and verify model can generate.

    Uses a minimal generation call (~1 token) to verify the model is actually
    accessible, not just listed in the catalog.

    Args:
        model: Model name from config (e.g., 'gemini-2.0-flash')
    """
    try:
        from google import genai

        gemini_api_key = os.environ.get("DEEPPLAN_GEMINI_API_KEY") or os.environ["GEMINI_API_KEY"]
        client = genai.Client(api_key=gemini_api_key)
        # Make a minimal generation call to verify model is actually accessible
        # models.get() only checks catalog, not actual access permissions
        response = client.models.generate_content(
            model=model,
            contents="hi"
        )
        return {
            "success": True,
            "method": "api_key",
            "model": model,
            "test": "generation"
        }
    except Exception as e:
        error_str = str(e)
        # Check if it's a model not found error vs auth error
        if "404" in error_str or "not found" in error_str.lower():
            return {
                "success": False,
                "method": "api_key",
                "model": model,
                "error": f"Model '{model}' not found or not accessible for generation",
                "details": error_str
            }
        return {"success": False, "method": "api_key", "model": model, "error": error_str}


def test_gemini_vertex_ai(project: str, location: str, model: str) -> dict:
    """Test Gemini client with Vertex AI and verify model can generate.

    Uses a minimal generation call (~1 token) to verify the model is actually
    accessible in this project/region, not just listed in the catalog.

    Args:
        project: GCP project ID
        location: GCP region (e.g., 'us-central1')
        model: Model name from config (e.g., 'gemini-2.0-flash')
    """
    try:
        from google import genai

        client = genai.Client(vertexai=True, project=project, location=location)
        # Make a minimal generation call to verify model is actually accessible
        response = client.models.generate_content(
            model=model,
            contents="hi"
        )
        return {
            "success": True,
            "method": "vertex_ai",
            "project": project,
            "location": location,
            "model": model,
            "test": "generation"
        }
    except Exception as e:
        error_str = str(e)
        # Check if it's a model not found error vs auth error
        if "404" in error_str or "not found" in error_str.lower():
            return {
                "success": False,
                "method": "vertex_ai",
                "project": project,
                "location": location,
                "model": model,
                "error": f"Model '{model}' not found or not accessible for generation in {location}",
                "details": error_str
            }
        return {
            "success": False,
            "method": "vertex_ai",
            "project": project,
            "location": location,
            "model": model,
            "error": error_str
        }


def test_openai(model: str) -> dict:
    """Test OpenAI client and verify model can generate.

    Uses a minimal chat completion call (~1 token) to verify the model is
    actually accessible, not just listed in the catalog.

    Args:
        model: Model name from config (e.g., 'gpt-4o')
    """
    try:
        from openai import OpenAI, NotFoundError

        # Support DEEPPLAN_ overrides for OpenAI-compatible APIs
        api_key = os.environ.get("DEEPPLAN_OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            return {
                "success": False,
                "model": model,
                "base_url": None,
                "error": "OPENAI_API_KEY not set"
            }

        # Support custom base URL for OpenAI-compatible APIs
        base_url = os.environ.get("DEEPPLAN_OPENAI_BASE_URL") or os.environ.get("OPENAI_BASE_URL")

        if base_url:
            client = OpenAI(api_key=api_key, base_url=base_url)
        else:
            client = OpenAI(api_key=api_key)

        # Make a minimal chat completion to verify model is actually accessible
        # Use max_completion_tokens (not max_tokens) for GPT-5.x and o-series models
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "hi"}],
            max_completion_tokens=5
        )
        return {
            "success": True,
            "model": model,
            "base_url": base_url,
            "test": "generation"
        }
    except NotFoundError as e:
        return {
            "success": False,
            "model": model,
            "base_url": base_url,
            "error": f"Model '{model}' not found or not accessible for generation",
            "details": str(e)
        }
    except Exception as e:
        return {
            "success": False,
            "model": model,
            "base_url": base_url,
            "error": str(e)
        }


def main():
    parser = argparse.ArgumentParser(description="Test LLM client construction and model access")
    parser.add_argument("--gemini-api-key", metavar="MODEL", help="Test Gemini with API key")
    parser.add_argument("--vertex-ai", nargs=3, metavar=("PROJECT", "LOCATION", "MODEL"),
                        help="Test Gemini with Vertex AI")
    parser.add_argument("--openai", metavar="MODEL", help="Test OpenAI with specific model")
    args = parser.parse_args()

    results = {}
    any_failure = False

    if args.gemini_api_key:
        results["gemini_api_key"] = test_gemini_api_key(args.gemini_api_key)
        if not results["gemini_api_key"]["success"]:
            any_failure = True

    if args.vertex_ai:
        project, location, model = args.vertex_ai
        results["gemini_vertex_ai"] = test_gemini_vertex_ai(project, location, model)
        if not results["gemini_vertex_ai"]["success"]:
            any_failure = True

    if args.openai:
        results["openai"] = test_openai(args.openai)
        if not results["openai"]["success"]:
            any_failure = True

    print(json.dumps(results))
    sys.exit(1 if any_failure else 0)


if __name__ == "__main__":
    main()
