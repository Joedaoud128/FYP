def calculate_sum(numbers):
    total = 0
    for num in numbers:
        total += num
    return total

result = calculate_sum([1, 2, 3, 4, 5])
print("Sum:", result)