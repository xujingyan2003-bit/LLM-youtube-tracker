"""LLM YouTube Landscape Tracker - 第三阶段数据处理脚本。"""

import json
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RAW_DATA_FILE = DATA_DIR / "raw_videos.json"
PROCESSED_DATA_FILE = DATA_DIR / "processed_videos.json"

# 从项目根目录读取 .env，而不是依赖当前工作目录
load_dotenv(PROJECT_ROOT / ".env")


def resolve_llm_settings() -> dict[str, str]:
    """Resolve provider settings for OpenAI-compatible clients."""
    provider = os.getenv("LLM_PROVIDER", "openai").strip().lower()

    if provider == "github":
        token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
        if not token:
            raise RuntimeError(
                "LLM_PROVIDER=github requires GITHUB_TOKEN (or GH_TOKEN)."
            )

        return {
            "provider": "github",
            "api_key": token,
            "base_url": os.getenv("GITHUB_MODELS_BASE_URL", "https://models.inference.ai.azure.com"),
            "model": os.getenv("GITHUB_MODEL", "gpt-4o-mini"),
        }

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is missing. Copy .env.example to .env and set a valid OpenAI API key."
        )

    return {
        "provider": "openai",
        "api_key": api_key,
        "base_url": os.getenv("OPENAI_BASE_URL", ""),
        "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
    }


def create_llm_client(settings: dict[str, str]) -> OpenAI:
    """Create an OpenAI-compatible client from resolved settings."""
    base_url = settings.get("base_url", "").strip()
    if base_url:
        return OpenAI(api_key=settings["api_key"], base_url=base_url)
    return OpenAI(api_key=settings["api_key"])


def load_existing_analysis_index() -> dict[tuple[str, str], dict[str, Any]]:
    """Load previously processed results keyed by channel name and video id."""
    if not PROCESSED_DATA_FILE.exists():
        return {}

    try:
        with PROCESSED_DATA_FILE.open("r", encoding="utf-8") as f:
            previous_dataset = json.load(f)
    except Exception:
        return {}

    existing_index: dict[tuple[str, str], dict[str, Any]] = {}
    for channel in previous_dataset.get("channels", []):
        channel_name = str(channel.get("name", "Unknown Channel"))
        for video in channel.get("videos", []):
            video_id = video.get("video_id")
            analysis = video.get("llm_analysis")
            if video_id and isinstance(analysis, dict):
                existing_index[(channel_name, str(video_id))] = analysis

    return existing_index

SYSTEM_PROMPT = """
You are an expert AI researcher analyzing YouTube video transcripts. 
Your task is to extract structured information about Large Language Models (LLMs) from the transcript.
The user will provide the video title, channel name, and the transcript text.

You MUST respond with a valid JSON object matching this schema:
{
  "speaker": "Name of the main speaker(s)",
  "topics": ["topic1", "topic2", "topic3"],
  "summary": "A concise 2-3 sentence summary of what the creator actually says about LLMs",
  "themes": "How this relates to broader LLM themes (e.g., 'Model Evaluation', 'Architecure', 'AI Ethics')",
  "relations": "Any relations/mentions to other researchers, models, or channels"
}
Return only JSON and nothing else.
"""

def truncate_transcript(transcript: list[dict[str, Any]], max_chars: int = 15000) -> str:
    """拼接并截断字幕文本，防止 token 溢出"""
    if not isinstance(transcript, list):
        return ""
    full_text = " ".join([seg.get("text", "") for seg in transcript if "text" in seg])
    return full_text[:max_chars]

def process_video(client: OpenAI, model: str, channel_name: str, title: str, transcript_text: str) -> dict[str, Any]:
    """调用大模型 API 分析视频内容"""
    if not transcript_text.strip():
        return {
            "speaker": "Unknown",
            "topics": [],
            "summary": "No transcript available.",
            "themes": "None",
            "relations": "None"
        }

    user_content = (
        f"Channel: {channel_name}\n"
        f"Title: {title}\n"
        f"Transcript:\n{transcript_text}\n"
    )

    try:
        response = client.chat.completions.create(
            model=model,
            response_format={ "type": "json_object" },
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content}
            ],
            temperature=0.3
        )
        
        result_json = response.choices[0].message.content
        if result_json:
            return json.loads(result_json)
        return {}
    except Exception as e:
        print(f"Error processing video '{title}': {e}")
        return {
            "speaker": "Error",
            "topics": [],
            "summary": f"Error calling LLM: {str(e)}",
            "themes": "Error",
            "relations": "Error"
        }

def main():
    if not RAW_DATA_FILE.exists():
        print(f"找不到原始数据文件：{RAW_DATA_FILE}")
        print("请先运行 src/fetch.py 抓取数据。")
        return

    try:
        llm_settings = resolve_llm_settings()
    except RuntimeError as exc:
        print(str(exc))
        print("Please verify your .env settings and retry.")
        sys.exit(1)

    client = create_llm_client(llm_settings)
    model = llm_settings["model"]
    provider = llm_settings["provider"]
    existing_analysis_index = load_existing_analysis_index()

    print(f"LLM provider: {provider}, model: {model}")

    print("正在加载原始数据...")
    with open(RAW_DATA_FILE, "r", encoding="utf-8") as f:
        dataset = json.load(f)

    # 遍历每个频道和视频进行处理
    for channel in dataset.get("channels", []):
        channel_name = channel.get("name", "Unknown Channel")
        print(f"处理频道: {channel_name}")
        
        for video in channel.get("videos", []):
            title = video.get("title", "Unknown Title")
            print(f"  - 分析视频: {title}")

            cache_key = (channel_name, str(video.get("video_id", "")))
            cached_analysis = existing_analysis_index.get(cache_key)
            if cached_analysis:
                video["llm_analysis"] = cached_analysis
                continue
            
            # 如果已有处理结果且不需要强制刷新，可以跳过（这里默认每次复写）
            text = truncate_transcript(video.get("transcript", []))
            llm_result = process_video(client, model, channel_name, title, text)
            
            # 将分析结果注入到原有的视频对象中
            video["llm_analysis"] = llm_result
            
            # 不在结果中保留冗长的字幕，以减小最终生成文件体积供前端使用
            # 如果你需要保留原始字幕，可以注释掉这行
            video.pop("transcript", None)

    # 保存处理后的结果
    print(f"\n正在保存处理后数据至 {PROCESSED_DATA_FILE}...")
    with open(PROCESSED_DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(dataset, f, ensure_ascii=False, indent=2)
    print("第三阶段：LLM 数据提取完成！")

if __name__ == "__main__":
    main()
