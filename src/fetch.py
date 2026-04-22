"""LLM YouTube Landscape Tracker - 第二阶段数据采集脚本。"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import feedparser
import requests
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import NoTranscriptFound, TranscriptsDisabled

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR.mkdir(exist_ok=True)

CHANNEL_CONFIG_FILE = PROJECT_ROOT / "channels.json"

DEFAULT_KEYWORDS = [
    "llm",
    "large language model",
    "language model",
    "gpt",
    "chatgpt",
    "transformer",
    "prompt",
    "generative ai",
    "ai model",
    "artificial intelligence",
    "machine learning",
    "ai",
]

DEFAULT_CHANNELS = [
    {
        "name": "Adam Goodyer",
        "rss_url": "https://www.youtube.com/@AdamGoodyer",
    },
    {
        "name": "Yannic Kilcher",
        "rss_url": "https://www.youtube.com/@YannicKilcher",
    },
    {
        "name": "AI Explained",
        "rss_url": "https://www.youtube.com/@aiexplained",
    },
    {
        "name": "Matt Pocock",
        "rss_url": "https://www.youtube.com/@mattpocockuk/videos",
    }
]


def load_channels() -> list[dict[str, str]]:
    """Load channel list from channels.json, fallback to defaults."""
    if CHANNEL_CONFIG_FILE.exists():
        with CHANNEL_CONFIG_FILE.open("r", encoding="utf-8") as f:
            channels = json.load(f)
        if not isinstance(channels, list):
            raise ValueError("channels.json 必须是数组")
        return channels
    return DEFAULT_CHANNELS


def extract_video_id(url: str) -> str | None:
    """Extract a YouTube video id from a watch URL if possible."""
    parsed = urlparse(url)
    if "youtube.com" not in parsed.netloc:
        return None

    query_video_ids = parse_qs(parsed.query).get("v", [])
    if query_video_ids:
        return query_video_ids[0]

    path_parts = [part for part in parsed.path.split("/") if part]
    if parsed.netloc.endswith("youtu.be") and path_parts:
        return path_parts[0]

    return None


def fetch_video_metadata(video_id: str) -> dict[str, str]:
    """Fetch basic video metadata from YouTube oEmbed."""
    url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
    response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
    response.raise_for_status()
    payload = response.json()
    return {
        "title": payload.get("title", video_id),
        "author_name": payload.get("author_name", ""),
        "author_url": payload.get("author_url", ""),
    }


def matches_keywords(text: str, keywords: list[str]) -> bool:
    """Check whether text contains any keyword, case-insensitively."""
    normalized_text = text.lower()

    for keyword in keywords:
        normalized_keyword = keyword.strip().lower()
        if not normalized_keyword:
            continue
        if len(normalized_keyword) <= 2:
            if re.search(rf"\b{re.escape(normalized_keyword)}\b", normalized_text):
                return True
            continue
        if normalized_keyword in normalized_text:
            return True

    return False


def fetch_channel_videos(rss_url: str, limit: int) -> list[dict[str, Any]]:
    """Fetch latest videos from a YouTube RSS feed or channel page."""
    video_id = extract_video_id(rss_url)
    if video_id:
        return [
            {
                "video_id": video_id,
                "title": video_id,
                "link": rss_url,
                "published": None,
            }
        ]

    if "youtube.com/@" in rss_url or "/channel/" in rss_url or "/c/" in rss_url:
        response = requests.get(rss_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
        response.raise_for_status()

        seen_ids: set[str] = set()
        videos: list[dict[str, Any]] = []
        for match in re.finditer(r"/watch\?v=([A-Za-z0-9_-]{11})", response.text):
            extracted_id = match.group(1)
            if extracted_id in seen_ids:
                continue
            seen_ids.add(extracted_id)
            metadata = {}
            try:
                metadata = fetch_video_metadata(extracted_id)
            except Exception:
                metadata = {}
            videos.append(
                {
                    "video_id": extracted_id,
                    "title": metadata.get("title", extracted_id),
                    "link": f"https://www.youtube.com/watch?v={extracted_id}",
                    "published": None,
                }
            )
            if len(videos) >= limit:
                break

        if videos:
            return videos

    feed = feedparser.parse(rss_url)
    videos: list[dict[str, Any]] = []

    for entry in feed.entries[:limit]:
        entry_video_id = entry.get("yt_videoid")
        entry_title = entry.get("title") or entry_video_id or ""
        videos.append(
            {
                "video_id": entry_video_id,
                "title": entry_title,
                "link": entry.get("link"),
                "published": entry.get("published"),
            }
        )

    if not videos:
        print(f"警告：未从 RSS 获取到任何条目：{rss_url}")

    return videos


def fetch_transcript(video_id: str, languages: list[str]) -> tuple[list[dict[str, Any]], str]:
    """Return transcript segments and selected language for a video."""
    api = YouTubeTranscriptApi()
    transcript_list = api.list(video_id)

    try:
        transcript = transcript_list.find_transcript(languages)
    except NoTranscriptFound:
        transcript = transcript_list.find_generated_transcript(languages)

    segments = transcript.fetch()
    normalized_segments: list[dict[str, Any]] = []
    for segment in segments:
        # youtube-transcript-api may return either dict-like or object-like snippets.
        if isinstance(segment, dict):
            text = str(segment.get("text", "")).strip()
            start = segment.get("start")
            duration = segment.get("duration")
        else:
            text = str(getattr(segment, "text", "")).strip()
            start = getattr(segment, "start", None)
            duration = getattr(segment, "duration", None)

        normalized_segments.append(
            {
                "text": text,
                "start": start,
                "duration": duration,
            }
        )

    return normalized_segments, transcript.language_code


def collect_dataset(limit: int, languages: list[str], keywords: list[str]) -> dict[str, Any]:
    """Collect videos and transcripts for configured channels."""
    channels = load_channels()
    dataset: dict[str, Any] = {
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "languages": languages,
        "keywords": keywords,
        "channels": [],
    }

    for channel in channels:
        name = channel.get("name", "Unknown Channel")
        rss_url = channel.get("rss_url")
        if not rss_url:
            continue

        videos = fetch_channel_videos(rss_url=rss_url, limit=limit)
        channel_payload: dict[str, Any] = {
            "name": name,
            "rss_url": rss_url,
            "videos": [],
            "filtered_out": 0,
        }

        for video in videos:
            video_id = video.get("video_id")
            if not video_id:
                video["transcript_status"] = "missing_video_id"
                channel_payload["videos"].append(video)
                continue

            try:
                segments, transcript_language = fetch_transcript(video_id=video_id, languages=languages)
                video["transcript_status"] = "ok"
                video["transcript_language"] = transcript_language
                video["transcript"] = segments
                transcript_text = " ".join(str(segment.get("text", "")) for segment in segments)
            except (TranscriptsDisabled, NoTranscriptFound):
                video["transcript_status"] = "unavailable"
                video["transcript"] = []
                transcript_text = ""
            except Exception as exc:  # noqa: BLE001
                video["transcript_status"] = f"error: {type(exc).__name__}"
                video["transcript"] = []
                transcript_text = ""

            searchable_text = " ".join(
                [
                    str(video.get("title", "")),
                    str(video.get("link", "")),
                    transcript_text,
                ]
            )
            if keywords and not matches_keywords(searchable_text, keywords):
                channel_payload["filtered_out"] += 1
                continue

            channel_payload["videos"].append(video)

        dataset["channels"].append(channel_payload)

    return dataset


def save_dataset(dataset: dict[str, Any]) -> Path:
    """Save collected dataset into data/raw_videos.json."""
    output_path = OUTPUT_DIR / "raw_videos.json"
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(dataset, f, ensure_ascii=False, indent=2)
    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch YouTube videos and transcripts for LLM channels.")
    parser.add_argument("--limit", type=int, default=3, help="videos per channel")
    parser.add_argument(
        "--keywords",
        type=str,
        default=",".join(DEFAULT_KEYWORDS),
        help="comma-separated keywords used to keep only LLM-related videos",
    )
    parser.add_argument(
        "--languages",
        type=str,
        default="en,zh-Hans,zh-Hant",
        help="comma-separated transcript language preference",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    languages = [lang.strip() for lang in args.languages.split(",") if lang.strip()]
    keywords = [keyword.strip() for keyword in args.keywords.split(",") if keyword.strip()]

    dataset = collect_dataset(limit=args.limit, languages=languages, keywords=keywords)
    output_path = save_dataset(dataset)

    total_videos = sum(len(channel["videos"]) for channel in dataset["channels"])
    print(f"采集完成：{len(dataset['channels'])} 个频道，{total_videos} 个视频")
    print(f"输出文件：{output_path}")


if __name__ == "__main__":
    main()
