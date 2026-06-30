---
name: example-greet
description: 通过运行一个小 Python 脚本来向某人打招呼
---

当用户要求向某人打招呼时：

1. 使用 `run_bash` 工具执行本 skill 目录下捆绑的 `greet.py` 脚本，把对方的名字作为第一个参数传入。
   命令示例：
       python skills/example-greet/greet.py "Alice"
2. 把脚本的 stdout 原样返回作为回复（去掉末尾空白）。如果用户没有提供名字，默认使用 "world"。
