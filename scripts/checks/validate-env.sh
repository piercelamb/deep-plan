#!/usr/bin/env bash
# Environment validator for deep-plan plugin
#
# SECURITY: This script NEVER outputs sensitive credentials.
# - API keys are checked with [ -n "$VAR" ] which only tests existence, never echoes
# - ADC validation discards token output (> /dev/null), only exit code is used
# - JSON output contains only auth METHOD ("api_key", "vertex_ai_adc") or boolean, never actual secrets
#
# Checks:
# 1. uv is installed (REQUIRED - all Python execution uses uv)
# 2. Gemini auth:
#    - DEEPPLAN_GEMINI_API_KEY (preferred) or GEMINI_API_KEY (AI Studio API) OR
#    - ADC + GCP project (Vertex AI API)
#      Project source: config.json → gcloud config → DEEPPLAN_GOOGLE_CLOUD_PROJECT/GOOGLE_CLOUD_PROJECT env
# 3. DEEPPLAN_OPENAI_API_KEY (preferred) or OPENAI_API_KEY is set (for ChatGPT)
# 4. Test actual client construction (calls test_llm_clients.py)
#
# Exit codes:
# 0 = all checks pass (may have warnings)
# 1 = missing/stale Gemini auth (when alert_if_missing=true)
# 2 = missing OpenAI key (when alert_if_missing=true)
# 3 = could not locate plugin root
# 5 = uv not installed

set -euo pipefail

# Derive plugin root from script location
# This works regardless of how the plugin was installed (cache, dev mode, etc.)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"

# Sanity check: verify we found the right place
if [[ ! -f "$PLUGIN_ROOT/config.json" ]] && [[ ! -d "$PLUGIN_ROOT/skills" ]]; then
    echo '{"valid": false, "errors": ["Could not locate plugin root from script location. Expected config.json or skills/ at: '"$PLUGIN_ROOT"'"], "warnings": [], "gemini_auth": null, "openai_auth": false}'
    exit 3
fi

# Initialize output arrays
errors=()
warnings=()
gemini_auth="null"
openai_auth="false"

# Check 1: uv must be installed
if ! command -v uv &> /dev/null; then
    echo '{"valid": false, "errors": ["uv not installed. Install from https://docs.astral.sh/uv/"], "warnings": [], "gemini_auth": null, "openai_auth": false}'
    exit 5
fi

# Load config values
config_file="${PLUGIN_ROOT}/config.json"
alert_if_missing="true"
config_gcp_project=""
config_gcp_location=""
gemini_model=""
openai_model=""

if [ -f "$config_file" ]; then
    # Parse values from config using jq
    alert_if_missing=$(jq -r '.external_review.alert_if_missing // true' "$config_file" 2>/dev/null || echo "true")

    # Get GCP project from config (null becomes empty string)
    config_gcp_project=$(jq -r '.vertex_ai.project // empty' "$config_file" 2>/dev/null || echo "")

    # Get GCP location from config (null becomes empty string)
    config_gcp_location=$(jq -r '.vertex_ai.location // empty' "$config_file" 2>/dev/null || echo "")

    # Get model names from config
    gemini_model=$(jq -r '.models.gemini // empty' "$config_file" 2>/dev/null || echo "")
    openai_model=$(jq -r '.models.chatgpt // empty' "$config_file" 2>/dev/null || echo "")
fi

# Resolve effective env vars (DEEPPLAN_ overrides generic vars)
effective_gemini_api_key="${DEEPPLAN_GEMINI_API_KEY:-${GEMINI_API_KEY:-}}"
effective_openai_api_key="${DEEPPLAN_OPENAI_API_KEY:-${OPENAI_API_KEY:-}}"
effective_openai_base_url="${DEEPPLAN_OPENAI_BASE_URL:-${OPENAI_BASE_URL:-}}"
effective_openai_model="${DEEPPLAN_OPENAI_MODEL:-${OPENAI_MODEL:-$openai_model}}"
effective_google_cloud_project="${DEEPPLAN_GOOGLE_CLOUD_PROJECT:-${GOOGLE_CLOUD_PROJECT:-}}"
effective_google_cloud_location="${DEEPPLAN_GOOGLE_CLOUD_LOCATION:-${GOOGLE_CLOUD_LOCATION:-}}"
effective_google_application_credentials="${DEEPPLAN_GOOGLE_APPLICATION_CREDENTIALS:-${GOOGLE_APPLICATION_CREDENTIALS:-}}"

# Determine whether provider intent was explicitly scoped via DEEPPLAN_* variables.
# If at least one provider is explicitly scoped, validate only those providers.
explicit_openai_scope="false"
if [ -n "${DEEPPLAN_OPENAI_API_KEY:-}" ] || [ -n "${DEEPPLAN_OPENAI_MODEL:-}" ] || [ -n "${DEEPPLAN_OPENAI_BASE_URL:-}" ]; then
    explicit_openai_scope="true"
fi

explicit_gemini_scope="false"
if [ -n "${DEEPPLAN_GEMINI_API_KEY:-}" ] || [ -n "${DEEPPLAN_GOOGLE_CLOUD_PROJECT:-}" ] || [ -n "${DEEPPLAN_GOOGLE_CLOUD_LOCATION:-}" ] || [ -n "${DEEPPLAN_GOOGLE_APPLICATION_CREDENTIALS:-}" ]; then
    explicit_gemini_scope="true"
fi

validate_gemini="true"
validate_openai="true"
if [ "$explicit_gemini_scope" = "true" ] || [ "$explicit_openai_scope" = "true" ]; then
    validate_gemini="$explicit_gemini_scope"
    validate_openai="$explicit_openai_scope"
fi

# Get GCP project from gcloud config (if gcloud is available)
gcloud_gcp_project=""
if command -v gcloud &> /dev/null; then
    gcloud_gcp_project=$(gcloud config get-value project 2>/dev/null || echo "")
fi

# Resolve GCP project: config.json → gcloud config → env var
# Resolve GCP location: config.json → env var (no default - must be explicitly set for ADC)
gcp_project="${config_gcp_project:-${gcloud_gcp_project:-${effective_google_cloud_project:-}}}"
gcp_location="${config_gcp_location:-${effective_google_cloud_location:-}}"

# Check 2: Gemini auth
# Priority: API key (AI Studio) > ADC + Project (Vertex AI)
# SECURITY: We only check if API key EXISTS ([ -n ] test), never echo its value
if [ "$validate_gemini" = "true" ]; then
    if [ -n "$effective_gemini_api_key" ]; then
        gemini_auth='"api_key"'
    else
        # Check for ADC (either explicit path or default location)
        adc_path="${HOME}/.config/gcloud/application_default_credentials.json"
        has_adc="false"
        if [ -n "$effective_google_application_credentials" ] && [ -f "$effective_google_application_credentials" ]; then
            has_adc="true"
        elif [ -f "$adc_path" ]; then
            has_adc="true"
        fi

        if [ "$has_adc" = "true" ]; then
            # ADC exists - check if GCP project AND location are set (both required for Vertex AI)
            if [ -z "$gcp_project" ]; then
                gemini_auth='"adc_no_project"'
                if [ "$alert_if_missing" = "true" ]; then
                    errors+=("ADC found but no GCP project. Set vertex_ai.project in $config_file or export GOOGLE_CLOUD_PROJECT=your-project-id")
                fi
            elif [ -z "$gcp_location" ]; then
                gemini_auth='"adc_no_location"'
                if [ "$alert_if_missing" = "true" ]; then
                    errors+=("ADC found but no GCP location. Set vertex_ai.location in $config_file or export GOOGLE_CLOUD_LOCATION=your-region (e.g., us-central1)")
                fi
            else
                # ADC, project, and location exist - verify credentials are still valid
                # SECURITY: Token output discarded (> /dev/null), only exit code used
                if gcloud auth application-default print-access-token > /dev/null 2>&1; then
                    gemini_auth='"vertex_ai_adc"'
                else
                    gemini_auth='"adc_stale"'
                    if [ "$alert_if_missing" = "true" ]; then
                        errors+=("Gemini ADC credentials are stale. Run: gcloud auth application-default login")
                    fi
                fi
            fi
        else
            # No auth found
            if [ "$alert_if_missing" = "true" ]; then
                errors+=("Gemini auth not found. Options: 1) export GEMINI_API_KEY=key 2) export GOOGLE_CLOUD_PROJECT=proj && gcloud auth application-default login")
            fi
        fi
    fi
fi

# Check 3: OpenAI API key
# SECURITY: We only check if API key EXISTS ([ -n ] test), never echo its value
openai_base_url="$effective_openai_base_url"
if [ "$validate_openai" = "true" ]; then
    if [ -n "$effective_openai_api_key" ]; then
        openai_auth="true"
        if [ -n "$openai_base_url" ]; then
            # Note: We don't validate the URL format here, just note it exists
            # The actual connectivity test happens in test_llm_clients.py
            warnings+=("Using custom OpenAI endpoint: $openai_base_url")
        fi
    else
        if [ "$alert_if_missing" = "true" ]; then
            errors+=("OPENAI_API_KEY not set")
        fi
    fi
fi

# Check 4: Test actual client construction AND model access
# Only run if we have potential auth methods to test AND models configured
test_script="${SCRIPT_DIR}/test_llm_clients.py"
client_test_results=""

if [ -f "$test_script" ]; then
    test_args=""

    # Build test arguments based on what auth we found
    # Now includes model name to verify model access, not just auth
    if [ "$validate_gemini" = "true" ]; then
        if [ -n "$effective_gemini_api_key" ] && [ -n "$gemini_model" ]; then
            test_args="--gemini-api-key $gemini_model"
        elif [ "$gemini_auth" = '"vertex_ai_adc"' ] && [ -n "$gcp_project" ] && [ -n "$gemini_model" ]; then
            test_args="--vertex-ai $gcp_project $gcp_location $gemini_model"
        fi
    fi

    if [ "$validate_openai" = "true" ] && [ -n "$effective_openai_api_key" ] && [ -n "$effective_openai_model" ]; then
        test_args="$test_args --openai $effective_openai_model"
    fi

    # Run the test if we have any auth to test
    if [ -n "$test_args" ]; then
        client_test_results=$(uv run --directory "$PLUGIN_ROOT" "$test_script" $test_args 2>&1) || true

        # Parse test results and add errors if tests failed
        # NOTE: jq's // operator triggers on BOTH null AND false, so we use explicit checks
        if [ -n "$client_test_results" ]; then
            # Check for Gemini failures (check both api_key and vertex_ai results)
            if [ "$validate_gemini" = "true" ]; then
                if echo "$client_test_results" | jq -e '.gemini_api_key' > /dev/null 2>&1; then
                    gemini_success=$(echo "$client_test_results" | jq -r '.gemini_api_key.success' 2>/dev/null)
                    if [ "$gemini_success" = "false" ]; then
                        gemini_error=$(echo "$client_test_results" | jq -r '.gemini_api_key.error' 2>/dev/null)
                        errors+=("Gemini model test failed: $gemini_error")
                        gemini_auth='"test_failed"'
                    fi
                elif echo "$client_test_results" | jq -e '.gemini_vertex_ai' > /dev/null 2>&1; then
                    gemini_success=$(echo "$client_test_results" | jq -r '.gemini_vertex_ai.success' 2>/dev/null)
                    if [ "$gemini_success" = "false" ]; then
                        gemini_error=$(echo "$client_test_results" | jq -r '.gemini_vertex_ai.error' 2>/dev/null)
                        errors+=("Gemini model test failed: $gemini_error")
                        gemini_auth='"test_failed"'
                    fi
                fi
            fi

            # Check for OpenAI failures
            if [ "$validate_openai" = "true" ] && echo "$client_test_results" | jq -e '.openai' > /dev/null 2>&1; then
                openai_success=$(echo "$client_test_results" | jq -r '.openai.success' 2>/dev/null)
                if [ "$openai_success" = "false" ]; then
                    openai_error=$(echo "$client_test_results" | jq -r '.openai.error' 2>/dev/null)
                    errors+=("OpenAI model test failed: $openai_error")
                    openai_auth="false"
                fi
            fi
        fi
    fi
fi

# Build JSON output
errors_json="[]"
if [ ${#errors[@]} -gt 0 ]; then
    errors_json=$(printf '%s\n' "${errors[@]}" | jq -R . | jq -s .)
fi

warnings_json="[]"
if [ ${#warnings[@]} -gt 0 ]; then
    warnings_json=$(printf '%s\n' "${warnings[@]}" | jq -R . | jq -s .)
fi

valid="true"
exit_code=0
if [ ${#errors[@]} -gt 0 ]; then
    valid="false"
    # Determine exit code based on first error
    # ADC errors are Gemini/Vertex AI related
    if [[ "${errors[0]}" == *"Gemini"* ]] || [[ "${errors[0]}" == *"ADC"* ]]; then
        exit_code=1
    elif [[ "${errors[0]}" == *"OpenAI"* ]] || [[ "${errors[0]}" == *"OPENAI"* ]]; then
        exit_code=2
    fi
fi

echo "{\"valid\": $valid, \"errors\": $errors_json, \"warnings\": $warnings_json, \"gemini_auth\": $gemini_auth, \"openai_auth\": $openai_auth, \"plugin_root\": \"$PLUGIN_ROOT\"}"
exit $exit_code
