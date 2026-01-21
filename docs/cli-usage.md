# Research Digest CLI Documentation

Research Digest is a CLI tool for automated research paper ingestion, filtering, and summarization from arXiv. It uses LLM providers to analyze and generate digests of relevant papers based on your research topics.

## Installation

```bash
# Install from local source
uv install

# The CLI will be available as 'research-digest'
```

## Configuration

The tool uses a configuration file (`config.yaml`) or environment variables. Create a `config.yaml` file:

```yaml
llm:
  provider: "openai"  # or "ollama"
  model: "gpt-4o-mini"
  api_key: "your-api-key"  # optional, can be set via env vars
  base_url: null  # optional, for custom endpoints

app:
  throttling_delay: 3.0  # seconds between topic processing
  db_path: "research.db"  # SQLite database path
```

Environment variables use the prefix `RD_`:
- `RD_LLM__PROVIDER` - LLM provider
- `RD_LLM__MODEL` - Model name
- `RD_LLM__API_KEY` - API key
- `RD_APP__THROTTLING_DELAY` - Delay between topics
- `RD_APP__DB_PATH` - Database path

## Commands

### `add-topic`

Add a new research topic to track.

```bash
research-digest add-topic <name> <description>
```

**Arguments:**
- `name` - Short name for the research topic
- `description` - Natural language description of what you're researching

**Example:**
```bash
research-digest add-topic "machine-learning" "Recent advances in transformer architectures for natural language processing and computer vision"
```

**Behavior:**
1. Translates your natural language description into an arXiv search query using the configured LLM
2. Stores the topic in the database with the generated query
3. The topic becomes active and will be processed during updates

---

### `list-topics`

Display all configured research topics.

```bash
research-digest list-topics
```

**Output:**
A table showing:
- ID - Topic ID for reference
- Name - Topic name
- Description - Topic description (truncated)
- Active - Whether the topic is currently active (✓/✗)
- Last Run - Date of last update (or "Never")

---

### `update` (Detailed)

Main update loop to fetch and process new papers for all active topics.

```bash
research-digest update [OPTIONS]
```

**Options:**
- `--quiet, -q` - Run without output (useful for cron jobs)
- `--since <date>` - Fetch papers since specific date (format: dd-mm-yyyy)

**Timeframe and Paper Selection:**
The update command uses a sophisticated timeframe system to avoid reprocessing papers:

1. **Primary Time Gate**: Uses `topic.last_run_at` from previous runs
2. **Override Option**: `--since` flag overrides the stored timestamp
3. **Cut-off Logic**: Stops fetching when `published_at <= cutoff_date`
4. **Sorting**: Papers fetched in descending order by submission date (newest first)
5. **Deduplication**: Papers are tracked by base arXiv ID (without version suffix)

**Paper Processing Logic:**
```
For each active topic:
├── Query arXiv using topic's generated search query
├── Process papers in reverse chronological order
├── Stop when published_date <= cutoff_date
├── For each new/updated paper:
│   ├── Check if paper exists in database (by base ID)
│   ├── If exists: Update if newer version, skip if same/older
│   ├── If new: Add to database
│   ├── Filter for relevance using LLM (score 0-10)
│   ├── If relevant (score > threshold): Generate digest
│   └── Store PaperTopicLink with score, relevance flag, and digest
└── Update topic.last_run_at to current timestamp
```

**Version Handling:**
- arXiv papers have version suffixes (e.g., "2310.00012v1" → "2310.00012")
- Base ID (without version) is used for deduplication
- If same paper appears with newer version, metadata is updated and reprocessed
- Older versions are ignored if newer version already exists

**Status Handling:**
- **ZERO_RESULTS** - Warns if no papers found for a topic (check your query)
- **ERROR** - Reports any fetch errors and continues with other topics
- **Processing Errors** - Logs individual paper failures without stopping

**State Persistence:**
- Each topic maintains `last_run_at` timestamp
- Only papers published after this timestamp are processed
- This prevents duplicate processing and enables incremental updates
- `--since` flag allows manual override for backfilling or reprocessing

---

### `digest-report` (Detailed)

Generate human-readable digest reports for processed papers.

```bash
research-digest digest-report [TOPIC_ID]
```

**Arguments:**
- `TOPIC_ID` (optional) - Specific topic ID, or omit for all active topics

**Report Scope and Filtering:**
The digest report does NOT show ALL papers on a topic. It specifically displays:

1. **Relevant Papers Only**: Only papers marked `is_relevant = True` by the LLM filter
2. **With Generated Digests**: Only papers where a digest was successfully generated
3. **No Duplicates**: Uses PaperTopicLink to avoid showing same paper multiple times
4. **Chronological Order**: Sorted by creation date (newest first)

**Database Query Logic:**
```sql
SELECT links.*, papers.*
FROM paper_topic_links links
JOIN papers ON links.paper_id = papers.id
WHERE links.topic_id = ?
  AND links.is_relevant = TRUE
  AND links.digest IS NOT NULL
ORDER BY links.created_at DESC
```

**What's Included in Each Paper Entry:**
- Paper metadata (title, authors, publication date)
- Relevance score (0-10 scale from LLM assessment)
- Generated digest containing (all derived from title + abstract only):
  - **TL;DR**: One-sentence summary
  - **Key Contribution**: Main finding in 2-3 sentences  
  - **Methodology**: Methods used in 2-3 sentences
  - **Tags**: 5 relevant keywords for categorization

**Previous Report Handling:**
- **No duplicate detection**: Reports are generated on-demand from current database state
- **Idempotent**: Running multiple times produces same output (unless data changes)
- **Historical persistence**: All digests remain in database unless manually deleted
- **No "generated previously" logic**: Each run shows current state, not incremental changes

**Output Structure:**
```
Digest for: [Topic Name]
[Topic Description]
==================================================

1. [Paper Title]
   Authors: [Author names]
   Published: YYYY-MM-DD
   Relevance Score: X.X/10
   
   [Digest content with TL;DR, Key Contribution, Methodology]
   ----------------------------------------
```

**Example Usage:**
```bash
# All active topics with relevant papers
research-digest digest-report

# Specific topic (shows only that topic's relevant papers)
research-digest digest-report 3
```

**Key Behavior Notes:**
- Irrelevant papers are completely excluded from reports
- Papers with failed digest generation are excluded
- Each paper appears once per topic (even if relevant to multiple topics)
- Reports are real-time views, not cached or versioned documents

## Workflow

1. **Setup Topics**: Use `add-topic` to define your research interests
2. **Run Updates**: Use `update` (manually or via cron) to fetch and process new papers
3. **Review Results**: Use `digest-report` to see relevant papers and their summaries
4. **Manage Topics**: Use `list-topics` to track your research topics

## Database

The tool uses SQLite to store:
- Topics and their generated queries
- Paper metadata from arXiv
- Relevance scores and digests
- Processing history and timestamps

## LLM Integration

Supports multiple LLM providers:
- **OpenAI** - GPT models with API key
- **Ollama** - Local models via Ollama server
- Custom endpoints via `base_url` configuration

The LLM is used for:
- Converting natural language to arXiv queries
- Determining paper relevance (0-10 scoring)
- Generating structured paper digests

## Error Handling

- Network failures are logged but don't stop processing
- Individual paper errors don't affect other papers
- Configuration errors are reported clearly
- API rate limiting is handled via throttling

## Automation

The `update` command is designed for automation:
```bash
# Daily cron job
0 8 * * * cd /path/to/research-digest && uv run research-digest update --quiet
```

The tool maintains state between runs, only processing new papers since the last update.