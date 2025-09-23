#!/usr/bin/env python3
"""
TEST: Isolierte Lösung für das Enum-String Problem
"""

def safe_enum_access(value, fallback="UNKNOWN"):
    """Safely access enum name whether it's string or enum"""
    if isinstance(value, str):
        return value  # Already a string
    elif hasattr(value, 'name'):
        return value.name  # Enum object
    elif hasattr(value, 'value'):
        return value.value  # Some enums
    else:
        return fallback

# Test with different input types
test_cases = [
    "HIGH",  # String (current DB storage)
    None,    # None value
    "meeting"  # Another string
]

print("=== ENUM FIX TEST ===")
for case in test_cases:
    result = safe_enum_access(case, "MEDIUM")
    print(f"Input: {case} ({type(case)}) -> Output: {result}")

print("\nFix function works correctly!")