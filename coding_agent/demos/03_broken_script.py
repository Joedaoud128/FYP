#!/usr/bin/env python3
"""
Intentionally broken script for debugging demo
Contains multiple common errors:
1. Division by zero
2. Domain error (negative square root)
3. Type error
"""

import math

def calculate_average(numbers):
    """Calculate average of a list of numbers"""
    total = sum(numbers)
    count = len(numbers)
    # Bug: Division by zero if numbers is empty
    average = total / count
    return average


def get_square_root(number):
    """Calculate square root"""
    # Bug: No check for negative numbers
    result = math.sqrt(number)
    return result


def concatenate_strings(str1, str2):
    """Concatenate two strings"""
    # Bug: No type checking
    return str1 + str2


if __name__ == "__main__":
    # Test 1: Empty list causes division by zero
    print("Test 1: Calculate average")
    data = []
    print("Average:", calculate_average(data))
    
    # Test 2: Negative number causes domain error
    print("\nTest 2: Square root")
    negative_num = -16
    print("Square root:", get_square_root(negative_num))
    
    # Test 3: Type error
    print("\nTest 3: Concatenation")
    result = concatenate_strings("Hello ", 42)
    print("Result:", result)
