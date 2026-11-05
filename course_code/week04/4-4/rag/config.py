"""公共配置：路径、模型、Milvus 连接参数。"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "corpus"
RUNS = ROOT / "runs"
EVAL = ROOT / "eval"

MILVUS_URI = str(ROOT / "milvus_login_demo.db")
COLLECTION = "login_demo_chunks"
EMBED_DIM = 1536  # MiniMax embo-01 输出维度

EMBED_MODEL = "embo-01"
LLM_MODEL = "MiniMax-Text-01"
API_BASE = "https://api.minimaxi.com/v1"


def api_key() -> str:
    """从项目根目录的 .env 读取 MiniMax key。"""
    env = ROOT / ".env"
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("MINIMAX_CN_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError("MINIMAX_CN_API_KEY not found in project .env")
