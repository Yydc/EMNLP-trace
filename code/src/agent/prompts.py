"""Prompt templates and code extraction utilities for agent generation.

Migrated from legacy_run/src/utils_api.py to eliminate legacy dependencies.
"""

import re


# ============================================================================
# Code Extraction Utility
# ============================================================================

def extract_code(pred):
    """Extract the content of the last Python code block from the given string.

    If multiple code blocks exist, return the content of the last one;
    if no code block is found, return the original string with whitespace stripped.
    """
    patterns = [
        r'```python\s*(.*?)\s*```',  # Match ```python\n...content...\n```
    ]

    last_match = None
    for pattern in patterns:
        matches = list(re.finditer(pattern, pred, re.DOTALL))
        if matches:
            last_match = matches[-1].group(1)

    if last_match is None:
        return pred.strip()

    # Remove any trailing ``` or similar delimiters
    code = re.sub(r'(`{3,}.*)$', '', last_match.strip(), flags=re.IGNORECASE).strip()
    return code


# ============================================================================
# Prompt Templates for Multi-turn Code Generation
# ============================================================================

# First round (no dependencies, with test case)
PROMPT1 = """You are a Programming Expert. You always provide correct and reliable code solutions. You will be provided with the Background of the whole problem, a programming problem and may also some pre-implemented functions.If pre-implemented functions provided, you need to call the pre-implemented functions and write a new function to solve the problem.

## Background of the whole problem:
{problem_description}

## Problem Discription:
You need to complete {name} function.
{statement}

## Sample Test Case:
{sample_test_case}

## Guidelines:
- Ensure the function is executable and meets the requirement.
- Provide clear and concise comments to explain key parts of the code.

Return your response by filling the function following the function signature provided. Just generate the function itself and don't output anything else.
```python
"""


# Intermediate round with dependencies
PROMPT2 = """You are a Programming Expert. You always provide correct and reliable code solutions. You will be provided with the Background of the whole problem, a programming problem and may also some pre-implemented functions.If pre-implemented functions provided, you need to call the pre-implemented functions and write a new function to solve the problem.

## Background of the whole problem:
{problem_description}

## Problem Discription:
You need to complete {name} function.
{statement}

## Dependency information:
To solve the problem, you need to utilize the ## Pre-implemented functions {dependencies} provided.

## Pre-implemented functions:
{history}

## Sample Test Case:
{sample_test_case}

## Guidelines:
- Ensure the function is executable and meets the requirement.
- Handle ## Dependency information correctly.
- Provide clear and concise comments to explain key parts of the code.

Return your response by filling the function body following the function signature provided. Just generate the function itself and don't output any examples.
```python
"""


# Final round with dependencies
PROMPT3 = """You are a Programming Expert. You always provide correct and reliable code solutions. You will be provided with the Background of the whole problem, a programming problem and may also some pre-implemented functions.If pre-implemented functions provided, you need to call the pre-implemented functions and write a new function to solve the problem.

## Background of the whole problem:
{problem_description}

## Problem Discription:
You need to complete {name} function.
{statement}

## Dependency information:
To solve the problem, you need to utilize the ## Pre-implemented functions {dependencies} provided.

## Pre-implemented functions:
{history}

## Guidelines:
- Ensure the function is executable and meets the requirement.
- Handle ## Dependency information correctly.
- Provide clear and concise comments to explain key parts of the code.

Return your response by filling the function body following the function signature provided. Just generate the function itself and don't output any examples.
```python
import sys
def {name}():
    input = sys.stdin.read().split()
"""


# Final round without dependencies
PROMPT4 = """You are a Programming Expert. You always provide correct and reliable code solutions. You will be provided with the Background of the whole problem, a programming problem and may also some pre-implemented functions.If pre-implemented functions provided, you need to call the pre-implemented functions and write a new function to solve the problem.

## Background of the whole problem:
{problem_description}

## Problem Discription:
You need to complete {name} function.
{statement}

## Pre-implemented functions:
{history}

## Guidelines:
- Ensure the function is executable and meets the requirement.
- Provide clear and concise comments to explain key parts of the code.

Return your response by filling the function body following the function signature provided. Just generate the function itself and don't output any examples.

```python
import sys
def {name}():
    input = sys.stdin.read().split()
"""


# Intermediate round without dependencies
PROMPT5 = """You are a Programming Expert. You always provide correct and reliable code solutions. You will be provided with the Background of the whole problem, a programming problem and may also some pre-implemented functions.If pre-implemented functions provided, you need to call the pre-implemented functions and write a new function to solve the problem.

## Background of the whole problem:
{problem_description}

## Problem Discription:
You need to complete {name} function.
{statement}

## Pre-implemented functions:
{history}

## Sample Test Case:
{sample_test_case}

## Guidelines:
- Ensure the function is executable and meets the requirement.
- Provide clear and concise comments to explain key parts of the code.

Return your response by filling the function body following the function signature provided. Just generate the function itself and don't output any examples.
```python
"""
