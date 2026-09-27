# Day12 Function Calling 核心概念详解

> 整理自 Day12 学习过程中的关键问题：
> - `assistant` 是什么？
> - `tool_call` 是什么？
> - 第一次调用和第二次调用有什么区别？
>
> 配合 `day12_function_calling.py` 和 `day12_flowchart.txt` 一起看。

---

## 一、核心概念速查

| 概念 | 一句话解释 |
|---|---|
| `assistant` | 模型返回的消息对象。普通聊天时里面是 `content`；Function Calling 时里面是 `tool_calls` |
| `tool_call` | 模型发出的“调用请求”，包含 `id`、`function.name`、`function.arguments` |
| 第一次调用 | 带上 `tools`，让模型决策：要不要调工具？调哪个？传什么参？ |
| 本地执行 | 你的 Python 代码真正执行函数，模型不执行任何东西 |
| 第二次调用 | 把“用户提问 + 模型决策 + 工具结果”一起发回模型，让它组织自然语言回答 |

**一句话总结：模型只做决策和总结，真正执行的是你的代码。**

---

## 二、`assistant` 到底是什么

### 2.1 定义

`assistant` 是模型返回的消息对象，代表“模型说的话”。

在代码中，它来自：

```python
assistant_msg = first_resp.choices[0].message
```

### 2.2 两种形态

| 场景 | `assistant` 消息里有什么 |
|---|---|
| 普通聊天 | `content`：一段文本 |
| Function Calling | `tool_calls`：一个列表，里面是模型要求调用的工具 |

### 2.3 在 Function Calling 中的样子

```python
ChatCompletionMessage(
    role="assistant",
    tool_calls=[
        ChatCompletionMessageFunctionToolCall(
            id="call_00_umBphINB2k9PAUfHoDnh9541",
            function=Function(
                name="calculator",
                arguments='{"a": 123, "b": 456, "operator": "*"}'
            ),
            type="function",
            index=0
        )
    ]
)
```

### 2.4 关键理解

- `assistant` 不是“模型理解的话语”，而是**模型返回的消息对象**。
- 在 Function Calling 里，`assistant` 的主要内容是 `tool_calls`，即模型的决策。
- 必须把 `assistant_msg` 追加进 `messages`，否则第二次调用会报错。

---

## 三、`tool_call` 到底是什么

### 3.1 定义

`tool_call` 是 `assistant` 消息里的一个元素，代表**模型发出的一个调用请求**。

它**不是工具本身**，也**不执行任何东西**。它只是告诉开发者：

> “我要调 `calculator`，参数是 `123`、`456`、`*`。”

### 3.2 结构拆解

以实际输出为例：

```python
ChatCompletionMessageFunctionToolCall(
    id='call_00_umBphINB2k9PAUfHoDnh9541',
    function=Function(
        arguments='{"a": 123, "b": 456, "operator": "*"}',
        name='calculator'
    ),
    type='function',
    index=0
)
```

| 字段 | 值 | 含义 |
|---|---|---|
| `id` | `call_00_...` | 本次调用的唯一编号，回传结果时必须带上 |
| `function.name` | `calculator` | 模型要调哪个函数 |
| `function.arguments` | `'{"a": 123, ...}'` | 传给函数的参数，**是 JSON 字符串，不是字典** |
| `type` | `"function"` | 工具类型，固定值 |
| `index` | `0` | 多个 tool_calls 时的序号 |

### 3.3 关键理解

- `tool_call` 是“请求”，不是“结果”。
- `arguments` 必须用 `json.loads()` 解析成 Python 字典。
- `tool_call.id` 必须原样传给 `role:"tool"` 消息的 `tool_call_id`，模型靠它对号入座。

---

## 四、第一次调用 vs 第二次调用

| 维度 | 第一次调用 | 第二次调用 |
|---|---|---|
| **目的** | 让模型决策：要不要调工具？调哪个？传什么参？ | 让模型根据工具结果，组织自然语言回答 |
| **传入 messages** | 只有 `user` 消息 | `user` + `assistant(tool_calls)` + `tool(result)` |
| **传入 tools** | **必须传** | 通常不传（单轮场景） |
| **模型返回** | `assistant` 消息，里面是 `tool_calls` | `assistant` 消息，里面是普通文本 `content` |
| **本地函数执行了吗** | 没执行 | 也没执行（中间那步已执行完） |
| **关键动作** | `json.loads(arguments)` 解析参数 | 直接读 `content` 作为最终回答 |
| **温度** | `temperature=0`（稳定决策） | `temperature=0`（稳定总结） |

### 4.1 第一次调用代码

```python
first_resp = client.chat.completions.create(
    model="deepseek-chat",
    messages=messages,       # 只有 user
    tools=tools,             # 关键：告诉模型有哪些工具
    temperature=0,
)
assistant_msg = first_resp.choices[0].message
```

### 4.2 第二次调用代码

```python
second_resp = client.chat.completions.create(
    model="deepseek-chat",
    messages=messages,       # user + assistant(tool_calls) + tool(result)
    temperature=0,
)
final_answer = second_resp.choices[0].message.content
```

### 4.3 为什么第二次不传 tools？

因为决策已经做完了，第二次只是让模型总结。  
如果要让模型连续调多个工具，才需要继续传 `tools`。

---

## 五、完整五步流程

### 5.1 文字版五步

1. **发问**：用户提问 + `tools` 一起发给模型
2. **决策**：模型返回 `assistant` 消息，含 `tool_calls`
3. **执行**：你的 Python 代码执行 `calculator(**args)`，得到结果
4. **回传**：把 `assistant_msg` 和 `role:"tool"` 消息追加进 `messages`
5. **总结**：第二次调用，模型组织自然语言回答

### 5.2 流程图

完整流程图见同目录 `day12_flowchart.txt`。

---

## 六、为什么必须 `messages.append(assistant_msg)`

第二次调用时，模型需要看到自己之前的决策（`tool_calls`），才能把 `tool` 结果和 `tool_call_id` 对应起来。

如果不追加，API 会报错：

```
tool_call_id ... does not have a corresponding tool_call
```

这是 Function Calling 最常见的坑之一。

---

## 七、常见误区与踩坑

| 误区 / 坑 | 正确理解 |
|---|---|
| “assistant 是模型理解的话语” | `assistant` 是模型返回的消息对象，Function Calling 时主要内容是 `tool_calls` |
| “tool_call 是调用函数的工具” | `tool_call` 是模型发出的**调用请求**，不是工具本身，也不执行 |
| “第一次调用把文本解析成 Python 字符串” | 第一次调用让模型做决策；`arguments` 是模型生成的 JSON 字符串，解析是你后面用 `json.loads` 做的 |
| “第二次把解析出来和需求塞给 AI” | 第二次塞给 AI 的是：用户需求 + 模型决策 + 工具结果 |
| `arguments` 当字典用 | 它是 JSON 字符串，必须先 `json.loads` |
| `content` 传数字 | 必须是字符串，用 `str(result)` |
| 忘记传 `tools` | 模型永远不调工具，只返回文本 |
| `tool_call_id` 写错 | 必须用 `tool_call.id` 原样传 |

---

## 八、生活比喻

- **你**：顾客
- **模型**：服务员
- **calculator**：后厨的厨师
- **tools**：菜单（告诉服务员有哪些菜）
- **第一次调用**：你问服务员“123 乘以 456 等于几？”
- **tool_call**：服务员说“我去叫厨师算一下，参数是 123、456、乘”
- **本地执行**：厨师真的去算了，得到 56088
- **第二次调用**：你把“顾客的问题 + 服务员的点单 + 厨师算出的结果”一起给服务员
- **最终回答**：服务员说“123 乘以 456 等于 56088”

**服务员（模型）自己不会算，它只负责点单和总结。真正算的是厨师（你的 Python 函数）。**

---

## 九、与 Day12 代码的对应关系

| 概念 | 代码位置 |
|---|---|
| `assistant` | `assistant_msg = first_resp.choices[0].message` |
| `tool_call` | `for tool_call in assistant_msg.tool_calls:` |
| `tool_call.id` | `"tool_call_id": tool_call.id` |
| `tool_call.function.name` | `if tool_call.function.name == "calculator":` |
| `tool_call.function.arguments` | `raw_args = tool_call.function.arguments` |
| 解析参数 | `args = json.loads(raw_args)` |
| 本地执行 | `result = calculator(**args)` |
| 回传结果 | `messages.append({"role":"tool", ...})` |
| 第一次调用 | `first_resp = client.chat.completions.create(..., tools=tools)` |
| 第二次调用 | `second_resp = client.chat.completions.create(..., messages=messages)` |

---

## 十、一句话总结

> **模型决策 → 你的代码执行 → 结果回传 → 模型总结。**
> **模型不执行任何东西，它只做决策和总结。**