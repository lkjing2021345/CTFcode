# IDA MCP（通过 MCP 操作 IDA Pro）

> 前提：先起服务（每个二进制一个服务）
>   `~/CTF/agent/scripts/ida_mcp_serve.sh <binary> 8745`
> 并在 config.yaml 启用 `mcp.ida`（`http://127.0.0.1:8745/sse`，**这里要 /sse**）。
> 工具名前缀 `ida__`，用 `/mcp` 看全部（约 47 个）。

## 典型流程
1. 定位函数：用工具列表里的查找/列表类工具（如按名字/地址查找函数）。
2 **反编译**：`ida__decompile_function`（传函数名或地址）→ 读 C 伪代码。
3. 看细节：`ida__disassemble_function`（汇编）。
4. 读数据：`ida__data_read_string` / `_byte` / `_word` / `_dword` / `_qword`。
5. 调用关系：`ida__get_callers`（谁调用它）、`ida__get_callees`（它调用了谁）。
6. 数值换算：`ida__convert_number`（**别自己算进制**）。
7. 结构体：`ida__analyze_struct_detailed`、`ida__declare_c_type`。

## 常见工具速查
| 工具 | 作用 |
|---|---|
| `ida__decompile_function` | 反编译为 C |
| `ida__disassemble_function` | 反汇编 |
| `ida__get_callers` / `ida__get_callees` | 调用者 / 被调用者 |
| `ida__data_read_string` | 读字符串 |
| `ida__data_read_byte/word/dword/qword` | 读整数 |
| `ida__convert_number` | 进制/字节换算 |
| `ida__declare_c_type` | 声明 C 类型 |
| `ida__analyze_struct_detailed` | 分析结构体 |
| `ida__create_stack_frame_variable` / `delete_stack_frame_variable` | 栈变量 |
| `ida__get_current_address` | 当前光标地址 |

## 注意
- **一个服务只对应一个二进制**；换目标要重起 `ida_mcp_serve.sh`。
- 参数名/取值以工具 schema 为准（`/mcp` 能看到；也可先调一次看报错提示）。
- 只想**快速静态分析**、不想起服务 → 用 `ida` skill 的 `scripts/ida_headless.py`（更省事）。
  MCP 版胜在**工具更丰富**（改名、注释、类型、结构体分析、交叉引用等）。
