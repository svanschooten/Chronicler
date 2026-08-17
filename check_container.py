import os

# Let's try to read the container.py file contents
try:
    with open('chronicler/core/container.py', 'r') as f:
        content = f.read()
        print(content)
except Exception as e:
    print(f"Error reading file: {e}")