#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# Autonomous Claude Code Runner
# Implements the long-running agent framework with automatic session management
# =============================================================================

# Configuration
PROJECT_DIR="${1:-.}"
MAX_ITERATIONS="${2:-100}"
PAUSE_BETWEEN_SESSIONS="${3:-5}"  # seconds

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Navigate to project directory
cd "$PROJECT_DIR"
PROJECT_DIR="$(pwd)"

echo -e "${BLUE}=============================================${NC}"
echo -e "${BLUE}   Autonomous Claude Code Framework${NC}"
echo -e "${BLUE}=============================================${NC}"
echo -e "Project: ${GREEN}$PROJECT_DIR${NC}"
echo -e "Max Iterations: ${YELLOW}$MAX_ITERATIONS${NC}"
echo ""

# -----------------------------------------------------------------------------
# Helper Functions
# -----------------------------------------------------------------------------

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

get_test_counts() {
    if [[ -f "feature_list.json" ]]; then
        PASSING=$(grep -c '"passes": true' feature_list.json 2>/dev/null || echo "0")
        FAILING=$(grep -c '"passes": false' feature_list.json 2>/dev/null || echo "0")
        TOTAL=$((PASSING + FAILING))
        echo "$PASSING/$TOTAL"
    else
        echo "N/A"
    fi
}

check_completion() {
    if [[ -f "feature_list.json" ]]; then
        FAILING=$(grep -c '"passes": false' feature_list.json 2>/dev/null || echo "0")
        if [[ "$FAILING" -eq 0 ]]; then
            return 0  # Complete
        fi
    fi
    return 1  # Not complete
}

# -----------------------------------------------------------------------------
# Determine if this is initialization or continuation
# -----------------------------------------------------------------------------

if [[ ! -f "feature_list.json" ]]; then
    SESSION_TYPE="initializer"
    log_info "No feature_list.json found - running INITIALIZER session"
else
    SESSION_TYPE="coding"
    log_info "feature_list.json exists - running CODING session"
fi

# -----------------------------------------------------------------------------
# Prompts (embedded for portability)
# -----------------------------------------------------------------------------

INITIALIZER_PROMPT='## INITIALIZER AGENT - Autonomous Mode

You are setting up a new project for long-running autonomous development.
Work completely autonomously without asking for human input.

### MANDATORY TASKS (Complete ALL before stopping):

**1. Read app_spec.txt**
Read and understand the complete project specification.

**2. Create feature_list.json**
Based on app_spec.txt, create feature_list.json with 50-200 test cases:
```json
[
  {
    "id": 1,
    "category": "functional",
    "description": "Feature description",
    "steps": ["Step 1", "Step 2", "Step 3"],
    "passes": false,
    "priority": "high"
  }
]
```
Requirements:
- Categories: functional, style, performance, security
- Order by priority (critical features first)
- ALL start with "passes": false
- Mix of narrow (2-5 steps) and comprehensive (10+ steps) tests

**3. Create init.sh**
```bash
#!/bin/bash
# Install dependencies and start dev server
npm install 2>/dev/null || pip install -r requirements.txt 2>/dev/null || true
npm run dev &>/dev/null &
echo "Server starting on http://localhost:3000"
```

**4. Create claude-progress.txt**
```
# Claude Progress Log
## Session 1 - Initialization
- Created feature_list.json with X features
- Set up project structure
- Next: Implement Feature #1
Status: 0/X tests passing
```

**5. Initialize Git**
```bash
git init 2>/dev/null || true
git add -A
git commit -m "Initial setup: feature_list.json, init.sh, project structure"
```

**6. Create Basic Project Structure**
Set up directories and boilerplate based on tech stack.

### COMPLETION SIGNAL
When ALL tasks above are complete, output exactly:
<session>INIT_COMPLETE</session>

DO NOT ask for human input. DO NOT stop until outputting the completion signal.'

CODING_PROMPT='## CODING AGENT - Autonomous Mode

You are continuing autonomous development. Work without asking for human input.
Complete ONE feature fully, then signal completion.

### STEP 1: ORIENT (Run these commands first)
```bash
pwd && ls -la
cat app_spec.txt 2>/dev/null | head -50
cat feature_list.json 2>/dev/null | head -100
cat claude-progress.txt 2>/dev/null | tail -30
git log --oneline -10 2>/dev/null
echo "Remaining: $(grep -c "\"passes\": false" feature_list.json 2>/dev/null || echo 0)"
```

### STEP 2: START SERVERS
```bash
chmod +x init.sh 2>/dev/null; ./init.sh 2>/dev/null &
sleep 3
```

### STEP 3: CHECK FOR COMPLETION
If ALL features have "passes": true, output exactly:
<session>ALL_COMPLETE</session>
Then stop.

### STEP 4: IMPLEMENT ONE FEATURE
1. Find highest-priority feature with "passes": false
2. Implement it completely
3. Test thoroughly (use actual UI if web app)
4. Only change "passes": false → "passes": true after verification

NEVER remove or edit feature definitions. Only change the passes field.

### STEP 5: COMMIT & UPDATE PROGRESS
```bash
git add -A
git commit -m "Implement [feature name] - verified"
```

Update claude-progress.txt:
```
## Session N - [timestamp]
- Implemented: [feature]
- Test #X now passing
- Next: [next feature]
Status: X/Y tests passing
```

### STEP 6: SIGNAL COMPLETION
After completing ONE feature and committing, output exactly:
<session>FEATURE_COMPLETE</session>

### RULES
- Work on exactly ONE feature per session
- DO NOT ask for human input
- DO NOT stop without outputting a completion signal
- If stuck, commit partial progress and output: <session>NEEDS_HELP</session>'

# -----------------------------------------------------------------------------
# Main Loop
# -----------------------------------------------------------------------------

for (( iteration=1; iteration<=MAX_ITERATIONS; iteration++ )); do
    echo ""
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE} Session $iteration / $MAX_ITERATIONS${NC}"
    echo -e "${BLUE} Status: $(get_test_counts) tests passing${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""

    # Select prompt based on session type
    if [[ "$SESSION_TYPE" == "initializer" ]]; then
        PROMPT="$INITIALIZER_PROMPT"
        log_info "Running INITIALIZER session..."
    else
        PROMPT="$CODING_PROMPT"
        log_info "Running CODING session..."
    fi

    # Run Claude Code autonomously
    # --permission-mode acceptEdits: auto-approve file changes
    # -p: pass prompt directly (non-interactive mode)
    result="$(claude --permission-mode acceptEdits -p "$PROMPT" 2>&1)" || true

    echo "$result"

    # Check for completion signals
    if [[ "$result" == *"<session>ALL_COMPLETE</session>"* ]]; then
        echo ""
        log_success "🎉 ALL FEATURES COMPLETE!"
        log_success "Total iterations: $iteration"
        log_success "Final status: $(get_test_counts) tests passing"
        
        # Optional: Send notification
        command -v notify-send &>/dev/null && notify-send "Claude" "Project complete after $iteration sessions!"
        exit 0
    fi

    if [[ "$result" == *"<session>INIT_COMPLETE</session>"* ]]; then
        log_success "Initialization complete!"
        SESSION_TYPE="coding"  # Switch to coding mode for next iteration
    fi

    if [[ "$result" == *"<session>FEATURE_COMPLETE</session>"* ]]; then
        log_success "Feature completed successfully!"
    fi

    if [[ "$result" == *"<session>NEEDS_HELP</session>"* ]]; then
        log_warning "Agent requested help. Check claude-progress.txt for details."
        log_warning "Continuing anyway..."
    fi

    # Check if actually complete (belt and suspenders)
    if check_completion; then
        log_success "🎉 All tests passing! Project complete."
        exit 0
    fi

    # Brief pause between sessions
    log_info "Pausing ${PAUSE_BETWEEN_SESSIONS}s before next session..."
    sleep "$PAUSE_BETWEEN_SESSIONS"

done

log_warning "Reached maximum iterations ($MAX_ITERATIONS)"
log_info "Final status: $(get_test_counts) tests passing"
exit 1
