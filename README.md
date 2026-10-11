# dropbox-organizer

A CLI tool (`dbo`) that labels photos in your Dropbox using Claude's vision API. Labels are stored in a local SQLite database and written back to each file as Dropbox tags and file properties.

## Installation

```bash
pip install -e .
alias dbo='dropbox-organizer'
```

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

```
DROPBOX_APP_KEY=your_dropbox_app_key
ANTHROPIC_API_KEY=your_anthropic_api_key
```

## Authentication

Authentication uses a two-step PKCE flow. First, generate an authorization URL:

```bash
dbo auth
```

Visit the URL shown, click Allow, then complete authentication with the code:

```bash
dbo auth --code <paste-code-here>
```

Your token is saved to `data/.dropbox_token`.

## Commands

### `dbo scan`

List photos in a Dropbox folder and show which are already labeled.

```bash
dbo scan --path "/Camera Uploads/2024"
```

### `dbo label`

Download and label photos using Claude vision. Labels are saved to the local database and written to Dropbox as tags and file properties.

```bash
# Label everything under a path
dbo label --path "/Camera Uploads/2024"

# Limit to specific labels only (strict mode)
dbo label --path "/Camera Uploads/2024" \
  --strict \
  --labels screenshot --labels child --labels man --labels woman \
  --labels cat --labels dog \
  --model claude-haiku-4-5

# Preferred labels (model may add others)
dbo label --path "/Camera Uploads/2024" \
  --labels screenshot --labels child

# Dry run — estimate API cost without calling Claude
dbo label --path "/Camera Uploads/2024" --dry-run --model claude-haiku-4-5

# Process at most 100 photos
dbo label --path "/Camera Uploads/2024" --limit 100

# Re-process already-labeled files
dbo label --path "/Camera Uploads/2024" --force
```

**Options:**

| Option | Default | Description |
|--------|---------|-------------|
| `--path` | `/` | Dropbox folder to label |
| `--recursive / --no-recursive` | recursive | Scan subfolders |
| `--labels LABEL` | — | Allowed label. Repeat for multiple |
| `--strict` | off | Only use labels from `--labels`; discard others |
| `--model` | `claude-opus-4-5` | Claude model to use |
| `--limit N` | 0 (unlimited) | Stop after N photos |
| `--force` | off | Re-process already-labeled files |
| `--dry-run` | off | Estimate cost without calling APIs |

**Models and approximate cost per 1,000 photos:**

| Model | Cost |
|-------|------|
| `claude-haiku-4-5` | ~$2.50 |
| `claude-sonnet-4-6` | ~$9.00 |
| `claude-opus-4-5` | ~$45.00 |

### `dbo report`

Show a summary of all labeled photos.

```bash
# Table view (default)
dbo report

# Export to CSV
dbo report --format csv --output labels.csv

# JSON output
dbo report --format json
```

### `dbo remove-labels`

Remove specific labels from photos under a path.

```bash
# Preview what would change
dbo remove-labels --labels dog --labels cat --path "/Camera Uploads/2020" --dry-run

# Apply the removal
dbo remove-labels --labels dog --labels cat --path "/Camera Uploads/2020"
```

### `dbo backfill-ids`

Fetch Dropbox file IDs for existing database records. Only needed when migrating from an older version that used file paths as the primary key.

```bash
dbo backfill-ids --path "/Camera Uploads"
```

## Data storage

| File | Purpose |
|------|---------|
| `data/labels.db` | SQLite database; primary key is the Dropbox file ID |
| `data/.dropbox_token` | Dropbox OAuth refresh token (mode 600) |

The `data/` directory is `.gitignore`d. Back up `labels.db` to preserve your labeled results.

## Dropbox app setup

1. Create an app at [dropbox.com/developers](https://www.dropbox.com/developers/apps)
2. Choose **Scoped access** → **Full Dropbox**
3. Under **Permissions**, enable:
   - `files.metadata.read`
   - `files.content.read`
   - `file_properties.write`
   - `files.tags.write`
4. Copy the **App key** to your `.env`
