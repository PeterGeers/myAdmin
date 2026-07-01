ggshield is een python pip install in de file pre-push
Staat in folder /home/peter/projects/myAdmin/.githooks
voor het h-dcn *windows) project in
C:\Users\peter\aws\h-dcn\.githooks



Voorstel van copilot
#!/bin/sh
# Pre-push hook: quota-safe secret scan.
# Uses ggshield if available, falls back to local scanner when quota is exhausted.

echo "Running secret scan before push..."

REPO_ROOT=$(git rev-parse --show-toplevel)

# Read push info from stdin (local_ref local_sha remote_ref remote_sha)
while read -r local_ref local_sha remote_ref remote_sha; do

    # Skip delete pushes
    if [ "$local_sha" = "0000000000000000000000000000000000000000" ]; then
        continue
    fi

    # Determine changed files only (quota-safe)
    changed_files=$(git diff --name-only --diff-filter=ACM "$remote_sha" "$local_sha")

    if [ -z "$changed_files" ]; then
        echo "No changed files to scan."
        exit 0
    fi

    echo "Scanning $(echo "$changed_files" | wc -l | tr -d ' ') changed files..."

    if command -v ggshield >/dev/null 2>&1; then
        # Scan only changed files (not commit-range)
        output=$(ggshield secret scan path $changed_files 2>&1)
        code=$?

        # Detect quota exhaustion
        if echo "$output" | grep -qiE "no more API calls|quota|rate.limit"; then
            echo "ggshield quota exhausted - falling back to local scanner"
            "$REPO_ROOT/scripts/scan-secrets-local.sh" --pre-push "$remote_sha" "$local_sha"
            exit $?
        fi

        echo "$output"
        exit $code
    else
        echo "ggshield not found - running local scanner"
        "$REPO_ROOT/scripts/scan-secrets-local.sh" --pre-push "$remote_sha" "$local_sha"
        exit $?
    fi
done

exit 0

