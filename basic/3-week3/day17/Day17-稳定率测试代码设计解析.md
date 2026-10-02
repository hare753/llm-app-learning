# Day17 稳定率测试代码设计解析

> 配套代码：`basic/3-week3/day17/day17_stability_test.py`
> 目的：讲清「稳定率测试脚本」的分层设计、调用关系、完整执行流程。
> 适用：Day17 复盘、面试讲解准备。

---

## 目录

1. [设计思维：这份代码在模拟什么](#一设计思维这份代码在模拟什么)
2. [各模块调用关系](#二各模块调用关系谁调用谁)
3. [完整流程图](#三完整流程图覆盖全部代码)
4. [数据变化示例](#四数据变化示例)
5. [极简图](#五极简图只记一件事)
6. [一句话记住每层](#六一句话记住每层)

---

## 一、设计思维：这份代码在模拟什么

一句话：**它是一个「测试流水线」，不是「一个脚本」。**

真实流水线：

```text
准备原料 → 加工 → 质检 → 记录废品 → 出报表
```

对应到代码：

| 流水线角色 | 代码里是谁                        | 职责           |
| :--------- | :-------------------------------- | :------------- |
| 原料       | `cases`                           | 4 条待测文本   |
| 加工机器   | `extract_with_fields()`           | 调 API 抽取    |
| 质检标准   | `expect_null` / `expect_complete` | 预期是什么     |
| 质检员     | `main()` 循环里的 if/for          | 判断结果对不对 |
| 废品箱     | `failed_items` + `write_failed()` | 失败的统一记录 |
| 出报表     | `main()` 最后的 print             | 统计成功率     |

**为什么这样拆，而不是全部塞进 main()？**

如果全塞进去，main() 会变成 100 行，改 API 调用、改统计、改日志都混在一起，改一处崩三处。
拆开后，每个函数只负责一件事，改哪里就动哪里。

---

## 二、各模块调用关系（谁调用谁）

```text
                         ┌─────────────────────┐
                         │  模块加载（import）  │
                         └──────────┬──────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    │               │               │
              load_dotenv      _require_env()   client = OpenAI(...)
                    │               │               │
                    │         缺变量就抛错      MODEL = os.getenv(...)
                    │
                    ▼
        ┌──────────────────────────────┐
        │  if __name__ == "__main__"   │
        │         main()               │
        └──────────────┬───────────────┘
                       │
        ┌──────────────┴──────────────────────────────────┐
        │                                                 │
        │  main() 内部：                                   │
        │                                                 │
        │  1. 定义 cases                                  │
        │  2. 初始化计数器                                 │
        │  3. 打印标题                                     │
        │  4. for case in cases:                          │
        │       for i in range(3):                        │
        │           ┌─────────────────────────────────┐   │
        │           │ extract_with_fields(text, FIELDS)│   │
        │           └──────────────┬──────────────────┘   │
        │                          │                       │
        │                          ▼                       │
        │           ┌─────────────────────────────────┐   │
        │           │ build_extract_prompt(fields)     │   │
        │           │   → 拼 system prompt             │   │
        │           └──────────────┬──────────────────┘   │
        │                          │                       │
        │                          ▼                       │
        │           ┌─────────────────────────────────┐   │
        │           │ client.chat.completions.create() │   │
        │           │   → 调 API                       │   │
        │           └──────────────┬──────────────────┘   │
        │                          │                       │
        │                          ▼                       │
        │           ┌─────────────────────────────────┐   │
        │           │ clean_json(raw)                  │   │
        │           │   → 清洗 markdown 包裹            │   │
        │           └──────────────┬──────────────────┘   │
        │                          │                       │
        │                          ▼                       │
        │           ┌─────────────────────────────────┐   │
        │           │ json.loads(cleaned)              │   │
        │           │   → 转 dict                      │   │
        │           └──────────────┬──────────────────┘   │
        │                          │                       │
        │                          ▼                       │
        │           返回 (result, raw, error_info)         │
        │                          │                       │
        │           ┌──────────────┴──────────────┐        │
        │           │                             │        │
        │       result is None                result 是 dict│
        │           │                             │        │
        │           ▼                             ▼        │
        │   记录 failed_items               parse_ok += 1  │
        │   continue                       检查字段完整    │
        │                                  检查 null 正确  │
        │                                  打印结果        │
        │                                                 │
        │  5. 循环结束                                     │
        │  6. write_failed(failed_items)                  │
        │  7. 打印统计                                     │
        └─────────────────────────────────────────────────┘
```

---

## 三、完整流程图（覆盖全部代码）

按执行顺序，从文件被运行的那一刻开始。

```text
┌─────────────────────────────────────────────────────────────┐
│ 阶段 0：模块加载（import 时执行一次）                          │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
              import os / json / time / Path
              from dotenv import load_dotenv
              from openai import OpenAI
                            │
                            ▼
              BASE_DIR = 当前脚本目录
              ENV_PATH = basic/.env
              load_dotenv(ENV_PATH)
                            │
                            ▼
              FIELDS = ["name","skills","years","education"]
              FIELD_DESC = {...}
                            │
                            ▼
              ┌──────────────────────────┐
              │ _require_env()            │
              │ 检查三个环境变量           │
              └────────────┬─────────────┘
                           │
               ┌───────────┴───────────┐
               │                       │
            缺变量                   齐全
               │                       │
               ▼                       ▼
         抛 RuntimeError         client = OpenAI(...)
         脚本停止                 MODEL = os.getenv(...)
                                       │
                                       ▼
                              定义 clean_json()
                              定义 build_extract_prompt()
                              定义 extract_with_fields()
                              定义 write_failed()
                              定义 main()
                                       │
                                       ▼
                        ┌──────────────────────────┐
                        │ if __name__ == "__main__" │
                        │        main()             │
                        └────────────┬─────────────┘
                                     │
┌────────────────────────────────────┴────────────────────────┐
│ 阶段 1：进入 main()                                           │
└─────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
                        定义 cases（4 条用例）
                        repeat = 3
                        初始化 6 个计数器 + failed_items
                                     │
                                     ▼
                        打印 "开始结构化输出稳定率测试"
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────┐
│ 阶段 2：外层循环（4 个用例）                                  │
└─────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
                      for case in cases:  ←─────────────────┐
                                     │                       │
                                     ▼                       │
                        打印 ">>> 测试用例：完整信息"          │
                                     │                       │
                                     ▼                       │
┌─────────────────────────────────────────────────────────────┐
│ 阶段 3：内层循环（每个用例 3 次）                              │
└─────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
                     for i in range(3):  ←───────────────┐   │
                                     │                    │   │
                                     ▼                    │   │
                          total += 1                      │   │
                          打印 "第 N 次调用..."             │   │
                                     │                    │   │
                                     ▼                    │   │
┌─────────────────────────────────────────────────────────────┐
│ 阶段 4：调用 extract_with_fields()                            │
└─────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
                     prompt = build_extract_prompt(FIELDS)
                                     │
                                     ▼
                          raw = ""
                                     │
                                     ▼
                     try: client.chat.completions.create(...)
                                     │
                          ┌──────────┴──────────┐
                          │                     │
                       成功                   异常
                          │                     │
                          ▼                     ▼
                  raw = content          打包 error_info
                  clean_json(raw)        return None, raw, error_info
                  json.loads(cleaned)
                  return result, raw, None
                          │                     │
                          └──────────┬──────────┘
                                     │
                                     ▼
                     返回 (result, raw, error_info)
                                     │
                                     ▼
                     time.sleep(1)  # 防限流
                                     │
┌─────────────────────────────────────────────────────────────┐
│ 阶段 5：判断结果                                              │
└─────────────────────────────────────────────────────────────┘
                                     │
                          ┌──────────┴──────────┐
                          │                     │
                    result is None           result 是 dict
                          │                     │
                          ▼                     ▼
                  print("[FAIL]...")      parse_ok += 1
                  failed_items.append()         │
                  continue ──────────┐          ▼
                                     │   ┌──────────────────────┐
                                     │   │ expect_complete?      │
                                     │   └──────────┬───────────┘
                                     │              │
                                     │      ┌───────┴───────┐
                                     │      │               │
                                     │     是               否
                                     │      │               │
                                     │      ▼               │
                                     │  complete_total += 1 │
                                     │  all_has_value = all(│
                                     │    result.get(f)     │
                                     │    is not None       │
                                     │    for f in FIELDS)  │
                                     │      │               │
                                     │  ┌───┴───┐           │
                                     │  │       │           │
                                     │ 是       否           │
                                     │  │       │           │
                                     │  ▼       ▼           │
                                     │ complete_ok += 1    │
                                     │ print OK  print WARN │
                                     │                      │
                                     │   ┌──────────────────┘
                                     │   │
                                     │   ▼
                                     │ for f in expect_null:
                                     │     null_total += 1
                                     │     if result.get(f) is None:
                                     │         null_ok += 1
                                     │     else:
                                     │         print WARN
                                     │   │
                                     │   ▼
                                     │ print("结果：" + json.dumps(...))
                                     │   │
                                     └───┘ 回到内层循环
                                         │
                                    内层循环结束
                                         │
                                    回到外层循环 ────────────┘
                                         │
┌─────────────────────────────────────────────────────────────┐
│ 阶段 6：所有用例跑完                                          │
└─────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
                     write_failed(failed_items)
                                     │
                          ┌──────────┴──────────┐
                          │                     │
                    failed_items 为空      failed_items 有内容
                          │                     │
                          ▼                     ▼
                    直接 return            写 failed_raw.txt
                                           print 路径
                                     │
                                     ▼
                     打印 "测试统计结果"
                     打印 总调用次数
                     打印 JSON 解析成功率
                     if complete_total: 打印字段完整率
                     if null_total: 打印 null 正确率
                                     │
                                     ▼
                             main() 结束
                                     │
                                     ▼
                             脚本正常退出
```

---

## 四、数据变化示例

用「部分缺失」这条用例的第 1 次调用走一遍：

```text
进入前：
  case = {
      "id": "部分缺失",
      "text": "李四，熟悉Java和Spring开发...",
      "expect_null": ["years", "education"],
      "expect_complete": False,
  }
  total = 3

extract_with_fields() 内部：
  prompt = "你是专业信息抽取助手...\n- name: 姓名...\n- skills: ...\n..."
  调 API → raw = '{"name":"李四","skills":["Java","Spring"],"years":null,"education":null}'
  clean_json(raw) → 同样的字符串
  json.loads → {"name":"李四","skills":["Java","Spring"],"years":None,"education":None}
  返回 (dict, raw, None)

回到 main()：
  result is None? → False
  parse_ok: 4 → 5
  expect_complete? → False，跳过字段完整率检查
  for f in ["years","education"]:
    "years": result.get("years") is None → True → null_total 9→10, null_ok 9→10
    "education": result.get("education") is None → True → null_total 10→11, null_ok 10→11
  print("[OK] 结果：{...}")

进入下一次内层循环：
  total = 4
```

**核心：每跑一次，6 个计数器 + failed_items 被增量更新。跑完 12 次，最后一次性汇总。**

---

## 五、极简图（只记一件事）

```text
模块加载
   │
   ├─ 校验环境 ──┐
   │             │ 缺 → 抛错，脚本停止
   │             │ 齐 → 建 client
   │
   └─ 定义 5 个函数
         │
         ▼
    main()
         │
         ├─ 定义 cases
         ├─ 初始化计数器
         │
         ├─ 双层循环
         │     │
         │     └─ 每次循环：
         │           extract_with_fields()
         │              ├─ build_extract_prompt()
         │              ├─ 调 API
         │              ├─ clean_json()
         │              └─ json.loads()
         │           ↓
         │           判断结果 → 累加计数器
         │
         ├─ write_failed()
         └─ 打印统计
```

---

## 六、一句话记住每层

| 层                     | 一句话                         |
| :--------------------- | :----------------------------- |
| 模块加载               | 校验环境、建 client、定义函数  |
| `build_extract_prompt` | 拼 system prompt               |
| `extract_with_fields`  | 调 API、解析、返回三元组       |
| `write_failed`         | 失败统一落盘                   |
| `main`                 | 定义用例、跑循环、统计、出报表 |
| `if __name__`          | 只有直接运行才跑 main          |

**整份代码的本质：一个双层循环 + 6 个计数器 + 1 个失败列表。**
循环里调 API，计数器记成功/失败，最后打印百分比。所有分层都是为了让这三件事互不干扰。