#!/usr/bin/env python3
"""example-greet skill 捆绑的小演示脚本。"""

import sys


def main() -> None:
    name = sys.argv[1] if len(sys.argv) > 1 else "world"
    print(f"Hello, {name}! 👋")


if __name__ == "__main__":
    main()
