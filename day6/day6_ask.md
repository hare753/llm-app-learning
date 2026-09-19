背下来：
1.messages.append(user) 为什么要放在 try 之前？
我：因为要先设定好ai的记忆（前置条件），再使用ai。代码的顺序是默认从上到下执行。
ai：模型只能看到本次请求的 messages，user 是本次请求的一部分，必须先加进去；同时保证出错时 pop 能弹掉它

2.messages.pop() 在 except 里是弹掉哪一条？
我：try的pop()删除是出错的当下这一条信息
ai：弹掉列表最后一条，也就是刚加的 user，避免出现没有 assistant 回复的“孤儿”消息

3.为什么 messages.append(assistant) 必须写在最后？
我：因为要把ai的反回信息放到最后
ai：历史必须按时间顺序排列，assistant 是对当前 user 的回复，必须紧跟其后；下一轮 user 再 append 到它后面

4.如果把 system 消息删掉，模型会怎样？
我：不会报错，只是会变回默认风格
ai：不会报错。只是失去人设和全局约束，回答变成默认风格