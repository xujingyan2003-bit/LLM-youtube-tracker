"""Build a public HTML page from processed video analysis results."""

from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
PROCESSED_DATA_FILE = DATA_DIR / "processed_videos.json"
DOCS_DIR = PROJECT_ROOT / "docs"
INDEX_FILE = DOCS_DIR / "index.html"


def safe_text(value: Any) -> str:
		if value is None:
				return ""
		return html.escape(str(value))


def load_dataset() -> dict[str, Any]:
		if not PROCESSED_DATA_FILE.exists():
				raise FileNotFoundError(
						f"Missing input file: {PROCESSED_DATA_FILE}. Run src/fetch.py and src/process.py first."
				)

		with PROCESSED_DATA_FILE.open("r", encoding="utf-8") as f:
				return json.load(f)


def build_rows(dataset: dict[str, Any]) -> str:
		rows: list[str] = []
		channels = dataset.get("channels", [])

		for channel in channels:
				channel_name = channel.get("name", "Unknown Channel")
				for video in channel.get("videos", []):
						analysis = video.get("llm_analysis", {}) if isinstance(video.get("llm_analysis"), dict) else {}
						topics = analysis.get("topics", [])
						if not isinstance(topics, list):
								topics = []

						topic_badges = "".join(
								f'<span class="badge">{safe_text(topic)}</span>' for topic in topics[:6]
						)
						if not topic_badges:
								topic_badges = '<span class="muted">N/A</span>'

						title = safe_text(video.get("title", "Untitled"))
						link = safe_text(video.get("link", ""))
						published_raw = video.get("published")
						published = safe_text(published_raw) if published_raw else '<span class="muted">N/A</span>'
						speaker = safe_text(analysis.get("speaker", "Unknown"))
						summary = safe_text(analysis.get("summary", ""))
						themes = safe_text(analysis.get("themes", ""))
						relations = safe_text(analysis.get("relations", ""))
						status = safe_text(video.get("transcript_status", "unknown"))

						title_cell = title
						if link:
								title_cell = f'<a href="{link}" target="_blank" rel="noopener noreferrer">{title}</a>'

						rows.append(
								"\n".join(
										[
												"<tr>",
												f"  <td>{safe_text(channel_name)}</td>",
												f"  <td>{title_cell}</td>",
												f"  <td>{published}</td>",
												f"  <td>{speaker}</td>",
												f"  <td>{topic_badges}</td>",
												f"  <td>{themes}</td>",
												f"  <td>{relations}</td>",
												f"  <td>{summary}</td>",
												f"  <td>{status}</td>",
												"</tr>",
										]
								)
						)

		if not rows:
				return (
						"<tr><td colspan=\"9\" class=\"muted\">No processed videos found yet. "
						"Run the pipeline and refresh.</td></tr>"
				)

		return "\n".join(rows)


def build_html(rows_html: str, generated_at: str) -> str:
		return f"""<!doctype html>
<html lang=\"en\">
<head>
	<meta charset=\"utf-8\" />
	<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
	<title>LLM YouTube Landscape Tracker</title>
	<style>
		:root {{
			--bg-1: #0f1227;
			--bg-2: #1a2452;
			--surface: rgba(255, 255, 255, 0.08);
			--text: #f8f9ff;
			--muted: #c9cbe6;
			--accent: #2dd4bf;
			--accent-2: #f59e0b;
			--border: rgba(255, 255, 255, 0.18);
		}}

		* {{ box-sizing: border-box; }}
		body {{
			margin: 0;
			color: var(--text);
			background:
				radial-gradient(circle at 10% 20%, rgba(45, 212, 191, 0.22), transparent 30%),
				radial-gradient(circle at 85% 10%, rgba(245, 158, 11, 0.2), transparent 35%),
				linear-gradient(135deg, var(--bg-1), var(--bg-2));
			font-family: "Segoe UI", "Noto Sans", sans-serif;
			min-height: 100vh;
			padding: 24px;
		}}
		.wrap {{
			max-width: 1400px;
			margin: 0 auto;
			animation: fadeIn 420ms ease-out;
		}}
		h1 {{
			margin: 0 0 8px;
			font-size: clamp(1.6rem, 2.6vw, 2.4rem);
			letter-spacing: 0.2px;
		}}
		.sub {{
			color: var(--muted);
			margin-bottom: 18px;
		}}
		.card {{
			background: var(--surface);
			border: 1px solid var(--border);
			border-radius: 16px;
			overflow: hidden;
			backdrop-filter: blur(6px);
			box-shadow: 0 12px 36px rgba(6, 8, 20, 0.28);
		}}
		.table-wrap {{ overflow: auto; }}
		table {{
			width: 100%;
			border-collapse: collapse;
			min-width: 1200px;
		}}
		th, td {{
			padding: 12px;
			border-bottom: 1px solid var(--border);
			vertical-align: top;
			text-align: left;
			font-size: 14px;
			line-height: 1.4;
		}}
		th {{
			position: sticky;
			top: 0;
			background: rgba(15, 18, 39, 0.9);
			color: #fff;
			z-index: 1;
			font-weight: 700;
		}}
		tr:hover td {{ background: rgba(255, 255, 255, 0.05); }}
		a {{ color: var(--accent); text-decoration: none; }}
		a:hover {{ text-decoration: underline; }}
		.badge {{
			display: inline-block;
			margin: 0 6px 6px 0;
			padding: 2px 8px;
			border-radius: 999px;
			background: rgba(45, 212, 191, 0.16);
			border: 1px solid rgba(45, 212, 191, 0.45);
			font-size: 12px;
			white-space: nowrap;
		}}
		.muted {{ color: var(--muted); }}
		.footer {{
			margin-top: 14px;
			color: var(--muted);
			font-size: 13px;
			display: flex;
			justify-content: space-between;
			gap: 12px;
			flex-wrap: wrap;
		}}
		@keyframes fadeIn {{
			from {{ opacity: 0; transform: translateY(10px); }}
			to {{ opacity: 1; transform: translateY(0); }}
		}}
		@media (max-width: 700px) {{
			body {{ padding: 14px; }}
			th, td {{ padding: 10px; font-size: 13px; }}
		}}
	</style>
</head>
<body>
	<div class=\"wrap\">
		<h1>LLM YouTube Landscape Tracker</h1>
		<div class=\"sub\">Structured transcript-driven view of creator discussions about LLMs.</div>
		<div class=\"card\">
			<div class=\"table-wrap\">
				<table>
					<thead>
						<tr>
							<th>Channel</th>
							<th>Video</th>
							<th>Published</th>
							<th>Speaker</th>
							<th>Topics</th>
							<th>Themes</th>
							<th>Relations</th>
							<th>Summary</th>
							<th>Transcript Status</th>
						</tr>
					</thead>
					<tbody>
						{rows_html}
					</tbody>
				</table>
			</div>
		</div>
		<div class=\"footer\">
			<span>Last update (UTC): {safe_text(generated_at)}</span>
			<span>Built by automated pipeline (fetch -> process -> publish)</span>
		</div>
	</div>
</body>
</html>
"""


def main() -> None:
		DOCS_DIR.mkdir(exist_ok=True)
		dataset = load_dataset()
		rows = build_rows(dataset)
		generated_at = dataset.get("generated_at") or datetime.now(tz=timezone.utc).isoformat()
		html_output = build_html(rows, generated_at)

		with INDEX_FILE.open("w", encoding="utf-8") as f:
				f.write(html_output)

		print(f"Site generated: {INDEX_FILE}")


if __name__ == "__main__":
		main()
