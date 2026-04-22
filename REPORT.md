# LLM YouTube Landscape Tracker Project Report (Detailed Version)

## 1. Project Objectives and Scope

The objective of this project is to build an automated LLM YouTube content tracking pipeline that periodically scrapes new videos from specified channels, extracts subtitles, generates structured summaries via a large language model (LLM), and finally publishes the results as a publicly accessible web page.

The current scope focuses on the following capabilities:
- Incremental channel-level collection (defaults to the most recent `N` videos per channel)
- Subtitle retrieval and status annotation (successful/unavailable/error)
- Structured information extraction via an OpenAI-compatible interface
- Static site generation and automatic deployment to GitHub Pages

## 2. Code Structure and Responsibilities

The project employs a three-stage pipeline, corresponding to three Python scripts:

- `src/fetch.py`: Data collection layer
  - Reads channel configuration from `channels.json` (falls back to built-in default channel list if the file does not exist)
  - Supports two scraping paths: channel page scraping and RSS feed scraping
  - Retrieves subtitles, performs keyword filtering, and outputs `data/raw_videos.json`

- `src/process.py`: Semantic processing layer
  - Reads `data/raw_videos.json`
  - Truncates subtitle text and feeds it to the LLM to generate a standardized JSON structure
  - Reuses historical analysis results (indexed by `channel + video_id` for caching)
  - Outputs `data/processed_videos.json`

- `src/build_site.py`: Publishing and presentation layer
  - Reads the processed data
  - Generates `docs/index.html` (including a table, topic badges, and a status column)
  - Ready for direct hosting on GitHub Pages

Supporting files:
- `requirements.txt`: `feedparser`, `youtube-transcript-api`, `openai`, `requests`, `python-dotenv`
- `.github/workflows/update.yml`: Triggers automatic updates and deployments every 15 minutes
- `.env.example`: Provides configuration templates for both OpenAI and GitHub Models providers

## 3. Fetch Stage Implementation Details

### 3.1 Channel Source and Fallback Strategy

`fetch.py` first attempts to read `channels.json` from the root directory; if the file does not exist, it uses the `DEFAULT_CHANNELS` defined within the script. This ensures the project runs out-of-the-box while still supporting custom channel lists later.

### 3.2 Video Discovery Strategy

Different branches handle YouTube URLs:
- If a single video link is provided, the `video_id` is extracted directly
- For `@handle` / `channel` / `c` page URLs, the HTML is fetched and regex is used to extract `/watch?v=...`
- If the above fails, it falls back to parsing RSS using `feedparser`

When scraping channel pages, the script also attempts to supplement the publication date by:
1) Matching `datePublished` from the page's JSON-LD
2) Falling back to parsing relative time strings like "X days ago / X weeks ago"

### 3.3 Subtitle Collection and Status Annotation

Subtitles are handled using `youtube-transcript-api`:
- Prioritizes a specified language list (default: `en,zh-Hans,zh-Hant`)
- Attempts auto-generated captions if no manual subtitles are available
- Normalizes returned segments into the `{text, start, duration}` format

Each video record includes a `transcript_status` field. Common values include:
- `ok`
- `unavailable`
- `error: <ExceptionName>` (e.g., `error: IpBlocked`)

### 3.4 Keyword Filtering

Default keywords cover LLM-related terminology (e.g., `llm`, `gpt`, `transformer`, `generative ai`).
Filtering is applied to the combined text of `title + link + transcript`. Videos that do not match any keywords are marked as `filtered_out` for that channel.

## 4. Process Stage Implementation Details

### 4.1 Model Provider and Environment Variables

Two types of OpenAI-compatible endpoints are supported:
- `LLM_PROVIDER=openai`: Uses `OPENAI_API_KEY`, `OPENAI_MODEL`
- `LLM_PROVIDER=github`: Uses `GITHUB_TOKEN`, `GITHUB_MODEL`, `GITHUB_MODELS_BASE_URL`

The `.env` file is loaded explicitly using the project root path to avoid dependency on the current working directory.

### 4.2 Prompt and Structured Output

The system prompt instructs the model to return a fixed JSON structure:
- `speaker`
- `topics` (array)
- `summary` (2–3 sentences)
- `themes`
- `relations`

The request includes `response_format = {"type": "json_object"}` to minimize the risk of unstructured output.

### 4.3 Cost and Stability Control

- Subtitles are truncated to `max_chars=15000` to prevent excessive token usage
- Empty transcripts return a default result immediately to avoid invalid API calls
- API exceptions result in error placeholder entries, ensuring the pipeline does not halt

### 4.4 Reuse of Historical Results

`process.py` first reads the existing `processed_videos.json`, indexes previously analyzed videos, and reuses their results. This reduces redundant inference costs and overall runtime.

## 5. Build Site Stage Implementation Details

The static page is generated at `docs/index.html` with the following features:
- Responsive wide table including columns for Channel, Video, Publish Date, Speaker, Topics, Themes, Relations, Summary, and Transcript Status
- `topics` are rendered as badges (displaying up to the first 6 items)
- HTML escaping (`safe_text`) prevents injection risks
- Footer displays `generated_at` timestamp and pipeline description

## 6. Automation Deployment and Execution

GitHub Actions workflow `update.yml`:
- Trigger: Manual dispatch + `cron("*/15 * * * *")`
- Runtime environment: `ubuntu-latest` + Python 3.11
- Execution order:
  1) `python src/fetch.py --limit 5 --languages en,zh-Hans,zh-Hant`
  2) `python src/process.py`
  3) `python src/build_site.py`
  4) Upload `docs` and deploy to GitHub Pages

## 7. Current Data Observations (Based on Repository Artifacts)

The following observations can be made from existing data files:

- `data/raw_videos.json` (with a newer timestamp) contains multiple entries with `transcript_status = error: IpBlocked`, indicating network/region/IP restriction issues during subtitle retrieval.
- `data/processed_videos.json` (with an older timestamp) contains numerous records with `transcript_status = ok` and populated `llm_analysis` fields, indicating the pipeline ran successfully in a previous environment.
- The discrepancy in timestamps and statuses between the two files highlights differences in availability between the current and historical runtime environments.

This also explains why the published page may display "historically successful analysis results" while the most recent fetch batch experienced subtitle failures.

## 8. Identified Issues and Improvement Suggestions

### 8.1 Insufficient Anti-Blocking Measures for Subtitle Retrieval

Suggestions:
- Add configurable proxy/egress options
- Implement retry and backoff strategies for `IpBlocked` errors
- Move failed videos to a "pending retry queue" rather than terminating the value extraction for that run

### 8.2 Potential Mismatch Between Published Data and Latest Fetch

Suggestions:
- Output a summary statistic in `process.py` (e.g., count of successes/failures/reused items for the current run)
- Display a "batch ID or generation time comparison" on the page to explicitly indicate data freshness

### 8.3 Quality Assessment Not Yet Quantified

Suggestions:
- Perform manual sampling reviews of `summary/topics/themes` accuracy
- Introduce an `llm_analysis_confidence` metric or rule-based validation (e.g., checking for empty fields)

### 8.4 Keyword Filtering Trade-offs in Recall/Precision

Suggestions:
- Split keywords into "hard filter" terms and "soft scoring" terms
- Retain metadata summaries of filtered-out samples for future parameter tuning

## 9. Conclusion

The project has established a complete closed-loop pipeline of "Collection -> Processing -> Publishing -> Automated Deployment," with a clear engineering structure and a solid foundation for continuous operation.
The primary current bottlenecks are subtitle source stability (particularly `IpBlocked` scenarios) and consistency management across runtime batches. By prioritizing improvements in these two areas and adding quality assessment metrics, the project can evolve from a "demonstrable prototype" to a "long-term operational LLM observatory platform."