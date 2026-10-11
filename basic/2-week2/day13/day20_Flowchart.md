# Day20 批量抽取容错 + 重试 + 日志 · 流程图

> 脚本：`basic/2-week2/day13/day20_batch_extract_cli.py`
> 复用：`day13_extractor.extract()`
> 产出：`{原名}_extracted.json` + `extract_log.jsonl`

---

## 一、全景流程图

```mermaid
flowchart TD
    Start([启动脚本]) --> GetDir["读取 sys.argv[1]<br/>有参数用参数<br/>无参数用 BASE_DIR"]
    GetDir --> CheckDir{"目录存在?"}
    CheckDir -->|否| Exit1["打印错误<br/>sys.exit(1)"]
    CheckDir -->|是| Glob["glob 匹配 resume*.txt<br/>sorted 排序"]
    Glob --> HasFiles{"有文件?"}
    HasFiles -->|否| Exit0["打印提示<br/>sys.exit(0)"]
    HasFiles -->|是| PrintCount["打印文件总数"]

    PrintCount --> Loop{"for 循环<br/>还有文件?"}
    Loop -->|否| Summary["打印成功/失败统计<br/>打印日志路径"]
    Summary --> End([结束])

    Loop -->|是| PF["调用 process_file(fp)"]

    PF --> Read["1. 读文件<br/>open utf-8"]
    Read --> ReadOK{"读取成功?"}
    ReadOK -->|否| FailRead["返回 failed 条目<br/>error=读取失败"]
    ReadOK -->|是| Empty{"text.strip() 为空?"}
    Empty -->|是| FailEmpty["返回 failed 条目<br/>error=文件为空<br/>（不调 API）"]
    Empty -->|否| Retry["2. extract_with_retry(text)"]

    Retry --> WriteJSON["3. 写 {base}_extracted.json<br/>ensure_ascii=False"]
    WriteJSON --> WriteOK{"写入成功?"}
    WriteOK -->|否| FailWrite["返回 failed 条目<br/>error=输出失败"]
    WriteOK -->|是| Success["返回 success 条目<br/>含 output 文件名"]

    FailRead --> Log["write_log(entry)"]
    FailEmpty --> Log
    FailWrite --> Log
    Success --> Log

    Log --> Print["按状态打印 [成功]/[失败]"]
    Print --> Loop
```

---

## 二、重试循环流程图（`extract_with_retry`）

```mermaid
flowchart TD
    Enter([进入 extract_with_retry]) --> Init["last_error = None<br/>attempt = 0"]
    Init --> Cond{"attempt <= max_retry?"}
    Cond -->|否| ReturnFail["return (None, last_error)"]

    Cond -->|是| TryCall["try: extract(text)"]
    TryCall --> Ok{"result is not None?"}
    Ok -->|是| ReturnOK["return (result, None)"]
    Ok -->|否| SetErr["last_error = 抽取失败"]
    SetErr --> Catch{"抛异常?"}
    TryCall --> Catch
    Catch -->|是| SetErr2["last_error = 抽取异常: xxx"]
    Catch -->|否| SleepCheck
    SetErr2 --> SleepCheck{"attempt < max_retry?"}
    SleepCheck -->|是| Sleep["time.sleep(1)"]
    Sleep --> Incr["attempt += 1"]
    SleepCheck -->|否| Incr
    Incr --> Cond
```

---

## 三、三层职责分离图

```mermaid
flowchart LR
    subgraph L1["main() —— 管「批」"]
        A1["决定目录"]
        A2["glob 找文件"]
        A3["for 循环派活"]
        A4["计数 + 打印统计"]
    end

    subgraph L2["process_file() —— 管「单」"]
        B1["读文件"]
        B2["空文本预检"]
        B3["调 extract_with_retry"]
        B4["写 JSON"]
        B5["返回日志条目<br/>（保证不抛异常）"]
    end

    subgraph L3["extract_with_retry() —— 管「重试」"]
        C1["调 extract()"]
        C2["失败 sleep 1s"]
        C3["再试一次"]
        C4["返回 (result, error)"]
    end

    A3 -->|传入 filepath| B3
    B3 -->|传入 text| C1
    C4 -->|返回值| B4
    B5 -->|返回 entry| A4
```

---

## 四、单文件流水线时序图

```mermaid
sequenceDiagram
    participant M as main()
    participant P as process_file()
    participant R as extract_with_retry()
    participant E as extract() (Day13)
    participant F as 文件系统
    participant L as 日志文件

    M->>P: process_file(fp)
    P->>F: open(fp, "r", utf-8)
    F-->>P: text

    alt text 为空
        P-->>M: {status: failed, error: 文件为空}
    else text 非空
        P->>R: extract_with_retry(text)
        R->>E: extract(text) 第 1 次
        alt 成功
            E-->>R: result dict
            R-->>P: (result, None)
        else 失败
            E-->>R: None 或异常
            R->>R: time.sleep(1)
            R->>E: extract(text) 第 2 次
            E-->>R: result 或 None
            R-->>P: (result, error)
        end

        alt result is None
            P-->>M: {status: failed, error: xxx}
        else result 非空
            P->>F: 写 {base}_extracted.json
            P-->>M: {status: success, output: xxx.json}
        end
    end

    M->>L: write_log(entry)
    M->>M: 按状态计数 + 打印
```

---

## 五、纯文本 ASCII 版（无 mermaid 环境可用）

```text
┌──────────────────────────────────────────────────────────────┐
│                         启动脚本                              │
│                    python day20_xxx.py [dir]                 │
└───────────────────────────┬──────────────────────────────────┘
                            ▼
                 ┌─────────────────────┐
                 │  决定 target_dir     │
                 │  argv[1] 或 BASE_DIR │
                 └──────────┬──────────┘
                            ▼
                    ╱ 目录存在？ ╲
                  是 ╱             ╲ 否
                    ▼               ▼
        ┌────────────────┐   ┌──────────────┐
        │ glob resume*.txt│   │ 打印错误      │
        │ sorted 排序     │   │ sys.exit(1)  │
        └───────┬────────┘   └──────────────┘
                ▼
          ╱ 有文件？ ╲
        是╱         ╲否
         ▼           ▼
  ┌────────────┐  ┌──────────────┐
  │ 进入 for   │  │ 打印提示      │
  │ 循环       │  │ sys.exit(0)  │
  └─────┬──────┘  └──────────────┘
        │
        ▼
  ┌──────────────────────────────────────────────────┐
  │          process_file(fp) 单文件流水线            │
  │                                                    │
  │  ┌──────────────┐                                │
  │  │ 1. 读文件     │──失败──▶ 返回 failed 条目      │
  │  └──────┬───────┘                                │
  │         ▼                                         │
  │  ┌──────────────┐                                │
  │  │ 2. 空文本预检 │──空───▶ 返回 failed（不调 API） │
  │  └──────┬───────┘                                │
  │         ▼                                         │
  │  ┌──────────────────────────────┐                │
  │  │ 3. extract_with_retry(text)   │                │
  │  │   ┌────────────────────────┐  │                │
  │  │   │ for attempt in 0..1:    │  │                │
  │  │   │   extract(text)         │  │                │
  │  │   │   成功 → return         │  │                │
  │  │   │   失败 → sleep 1s       │  │                │
  │  │   └────────────────────────┘  │                │
  │  │   两次都失败 → 返回 failed 条目 │                │
  │  └──────┬───────────────────────┘                │
  │         ▼                                         │
  │  ┌──────────────┐                                │
  │  │ 4. 写 JSON    │──失败──▶ 返回 failed 条目      │
  │  └──────┬───────┘                                │
  │         ▼                                         │
  │  ┌──────────────┐                                │
  │  │ 5. 返回 success│                               │
  │  └──────────────┘                                │
  └──────────────────┬───────────────────────────────┘
                     ▼
        ┌────────────────────────┐
        │ write_log(entry)       │  ← 追加一行 JSONL
        │ 打印 [成功] 或 [失败]   │
        └───────────┬────────────┘
                    ▼
              ╱ 还有下一个？ ╲
            是╱             ╲否
             ▼               ▼
      （回到 for）    ┌──────────────────┐
                     │ 打印成功/失败统计 │
                     │ 打印日志文件路径   │
                     └──────────┬───────┘
                                ▼
                             [结束]
```

---

## 六、关键设计点速查

| 设计点 | 做法 | 为什么 |
| :--- | :--- | :--- |
| 路径锚定 | `BASE_DIR = os.path.dirname(os.path.abspath(__file__))` | 不依赖当前工作目录，Day15/Day19 已踩两次 |
| 三层职责 | `main` 管批 / `process_file` 管单 / `extract_with_retry` 管重试 | 改一处不动全身 |
| 异常契约 | `process_file` 保证不抛异常 | 主循环 `for` 里不写 `try/except`，单条失败天然不中断 |
| 空文本预检 | `.strip()` 一判，直接返回 failed | 省两次 API 调用 + 2 秒 sleep |
| 重试范围 | 只重试「返回 None」和「抛异常」 | 空文件、读失败等确定性错误不重试 |
| 重试间隔 | `time.sleep(1)` | 防 429 限流 |
| 判定成功 | `if result is not None` | 空字典 `{}` 是假值，`if result` 会误判 |
| 日志格式 | JSONL，`json.dumps(..., ensure_ascii=False)` | 追加写 O(1)，中文不变 `\uXXXX` |
| 落盘时机 | 每个文件处理完立刻 `write_log`，再打印 | 进程被 Ctrl+C 也不丢日志 |
| 退出码 | 目录不存在 `exit(1)`，无文件 `exit(0)` | CI/shell 可区分「错误」和「没活干」 |

---

## 七、四件套对照（今天必须记住）

```text
try/except   →  process_file 内部分段捕获（读 / 抽 / 写）
continue     →  单文件失败返回 failed 条目，for 循环继续下一个
重试          →  extract_with_retry 内部 for + sleep 1s，最多 2 次
日志          →  write_log 追加写 JSONL，先落盘再打印
```

**一句话**：单条失败不中断整体，所有异常必须留痕可回溯。