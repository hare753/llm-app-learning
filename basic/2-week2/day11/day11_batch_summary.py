import os
import time
from openai import OpenAI
from dotenv import load_dotenv

# ============================================================
# 1. 加载配置与初始化客户端
# ============================================================

# 加载 .env 文件里的环境变量到 os.environ
# .env 文件内容形如：DEEPSEEK_API_KEY=sk-xxxx
# 这样做的好处：API Key 不写死在代码里，不会被提交到 GitHub
load_dotenv()

# 从环境变量里读取 API Key
# 注意：变量名必须与 .env 文件中完全一致（大小写敏感）
api_key = os.getenv("DEEPSEEK_API_KEY")

# 如果没读到 Key，主动报错并提示，避免后面调用 API 时报更难懂的错
if not api_key:
    raise ValueError("请在 .env 文件中设置 DEEPSEEK_API_KEY")

# 初始化 DeepSeek 客户端
# DeepSeek 完全兼容 OpenAI 的接口格式，所以直接用 openai 库
# base_url 必须改成 DeepSeek 的地址，否则默认会请求 OpenAI 官方
client = OpenAI(
    api_key=api_key,
    base_url="https://api.deepseek.com"
)


# ============================================================
# 2. 定位文件夹（用脚本自身位置做基准，避免"从哪运行找不到"）
# ============================================================

# __file__ 是当前脚本的路径（可能是相对路径）
# os.path.abspath 转成绝对路径
# os.path.dirname 取所在目录
# 这样无论你从哪个目录运行脚本，都能正确定位到 day11/ 这一层
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 输入文件夹：day11/articles/，里面放待处理的 txt
input_dir = os.path.join(BASE_DIR, "articles")

# 输出文件夹：day11/summaries/，用来存生成的摘要
output_dir = os.path.join(BASE_DIR, "summaries")

# 如果 output_dir 不存在就自动创建，exist_ok=True 表示已存在时不报错
# 避免后面 open(..., "w") 因文件夹不存在而报 FileNotFoundError
os.makedirs(output_dir, exist_ok=True)


# ============================================================
# 3. 遍历 articles/ 下所有 txt 文件，逐个生成摘要
# ============================================================

# os.listdir 返回文件夹里所有文件和子文件夹的名字（不含路径）
for filename in os.listdir(input_dir):

    # 只处理 .txt 文件，跳过其他类型（如 .md、.json、临时文件）
    if not filename.endswith(".txt"):
        continue

    # 拼出完整路径，例如 F:\...\day11\articles\article1.txt
    file_path = os.path.join(input_dir, filename)

    # 读取文件全部内容，encoding="utf-8" 必须加，否则中文会乱码
    # with 语句会在代码块结束后自动关闭文件，无需手动 f.close()
    with open(file_path, "r", encoding="utf-8") as f:
        article_text = f.read()

    # 用 try/except 包住 API 调用：
    # 单个文件失败（网络超时、限流、内容为空等）时，打印错误并 continue
    # 不影响其他文件的处理
    try:
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                # 构造用户消息，把"指令 + 正文"一起发给模型
                # \n\n 让指令和正文分隔开，模型更容易理解
                {"role": "user", "content": f"请用100字以内总结这篇文章：\n\n{article_text}"}
            ],
            temperature=0.3,   # 0.3 略偏稳定，摘要不需要太多创意
            max_tokens=200     # 限制输出长度，防止摘要过长或失控
        )
        # 取模型返回的第一条回复内容，strip 去掉首尾空白
        summary = resp.choices[0].message.content.strip()

    except Exception as e:
        # 打印失败信息，continue 跳过当前文件，处理下一个
        print(f"处理 {filename} 失败：{e}")
        continue

    # --------------------------------------------------------
    # 4. 构造输出文件名并写入摘要
    # --------------------------------------------------------

    # os.path.splitext("article1.txt") → ("article1", ".txt")
    # 取 [0] 得到 "article1"，拼上 "_summary.txt"
    # 这样输出文件名就和输入文件名区分开了
    out_name = f"{os.path.splitext(filename)[0]}_summary.txt"

    # 拼出输出文件的完整路径，例如 F:\...\summaries\article1_summary.txt
    out_path = os.path.join(output_dir, out_name)

    # 以写入模式打开输出文件，encoding="utf-8" 防中文乱码
    # 文件不存在会自动创建，已存在会覆盖
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(summary)

    # 打印处理进度：原文名 -> 摘要名
    print(f"已处理：{filename} -> {out_name}")

    # 每处理完一篇暂停 1 秒，防止请求太密集触发 API 频率限制（429）
    time.sleep(1)