import sys
from pathlib import Path

from dotenv import load_dotenv

# 把 backend/ 加入模块搜索路径，这样 from app... 才能找到
BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

# 明确加载 backend/.env（不依赖当前工作目录）
load_dotenv(BACKEND_DIR / ".env")

from app.ai.llm_client import LLMClient

client = LLMClient()

result = client.chat(
    [
        {
            "role": "user",
            "content": "你好，请介绍一下你自己",
        }
    ]
)

print(result)
