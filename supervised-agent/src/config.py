"""
Centralized Configuration for Legal Agent Swarm.
Defines model constants to eliminate magic strings in compliance with the 2026 Development Manifesto.
"""

# Core Models
GEMINI_3_1_PRO = "gemini-3.1-pro"
GEMINI_3_PRO = "gemini-3-pro"
GEMINI_3_FLASH = "gemini-3-flash"
GEMINI_2_5_FLASH = "gemini-2.5-flash"
GEMINI_2_5_FLASH_LITE = "gemini-2.5-flash-lite"

# Fallback Chains
REASONING_MODEL_CHAIN = [GEMINI_3_1_PRO, GEMINI_3_PRO, "gemini-1.5-pro"]
HIGH_THROUGHPUT_MODEL_CHAIN = [GEMINI_3_FLASH, GEMINI_2_5_FLASH, "gemini-1.5-flash"]
LIGHTWEIGHT_MODEL_CHAIN = [GEMINI_2_5_FLASH_LITE, GEMINI_2_5_FLASH, GEMINI_3_FLASH]
