"""
Centralized Configuration for Legal Agent Swarm.
Defines model constants to eliminate magic strings in compliance with the 2026 Development Manifesto.
"""

# Core Models
CLAUDE_OPUS_5_5 = "claude-opus-5-5"

# Refusal fallback runs server-side (`fallbacks="default"` in src/claude_client.py), so no
# client-side model chain is kept here.
