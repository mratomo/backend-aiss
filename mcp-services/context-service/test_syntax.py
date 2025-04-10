#!/usr/bin/env python3
import sys
import ast

# Print Python version
print(f"Python version: {sys.version}")

# Read the main.py file
filename = "main.py"
with open(filename, "r") as f:
    content = f.read()

# Try to parse with AST
try:
    tree = ast.parse(content)
    print(f"AST Parse successful for {filename}")
except SyntaxError as e:
    print(f"Syntax error in {filename} at line {e.lineno}, column {e.offset}")
    print(f"Error details: {e}")

# Try to compile
try:
    compile(content, filename, 'exec')
    print(f"Compilation successful for {filename}")
except SyntaxError as e:
    print(f"Compilation error in {filename} at line {e.lineno}, column {e.offset}")
    print(f"Error details: {e}")
    
    # Print lines around the error
    lines = content.splitlines()
    start_line = max(0, e.lineno - 5)
    end_line = min(len(lines), e.lineno + 5)
    
    print("\nContext:")
    for i in range(start_line, end_line):
        prefix = ">>> " if i+1 == e.lineno else "    "
        print(f"{prefix}{i+1}: {lines[i]}")