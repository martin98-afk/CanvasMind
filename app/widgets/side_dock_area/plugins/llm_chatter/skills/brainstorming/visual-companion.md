# Visual Companion Guide
Browser-based visual brainstorming companion for showing mockups, diagrams, and options.
## When to Use
Decide per-question, not per-session. The test: **would the user understand this better by seeing it than reading it?**
**Use the browser** when the content itself is visual:
- **UI mockups** — wireframes, layouts, navigation structures, component designs
- **Architecture diagrams** — system components, data flow, relationship maps
- **Side-by-side visual comparisons** — comparing two layouts, two color schemes, two design directions
- **Design polish** — when the question is about look and feel, spacing, visual hierarchy
- **Spatial relationships** — state machines, flowcharts, entity relationships rendered as diagrams
**Use the terminal** when the content is text or tabular:
- **Requirements and scope questions** — "what does X mean?", "which features are in scope?"
- **Conceptual A/B/C choices** — picking between approaches described in words
- **Tradeoff lists** — pros/cons, comparison tables
- **Technical decisions** — API design, data modeling, architectural approach selection
- **Clarifying questions** — anything where the answer is words, not a visual preference
A question *about* a UI topic is not automatically a visual question. "What kind of wizard do you want?" is conceptual — use the terminal. "Which of these wizard layouts feels right?" is visual — use the browser.
## How It Works
The server watches a directory for HTML files and serves the newest one to the browser. You write HTML content to `screen_dir`, the user sees it in their browser and can click to select options. Selections are recorded to `state_dir/events` that you read on your next turn.
**Content fragments vs full documents:** If your HTML file starts with `
/.superpowers/brainstorm/` for the session directory.
**Note:** Pass the project root as `--project-dir` so mockups persist in `.superpowers/brainstorm/` and survive server restarts. Without it, files go to `/tmp` and get cleaned up. Remind the user to add `.superpowers/` to `.gitignore` if it's not already there.
**Launching the server by platform:**
**Claude Code (macOS / Linux):**
```bash
# Default mode works — the script backgrounds the server itself
scripts/start-server.sh --project-dir /path/to/project
```
**Claude Code (Windows):**
```bash
# Windows auto-detects and uses foreground mode, which blocks the tool call.
# Use run_in_background: true on the Bash tool call so the server survives
# across conversation turns.
scripts/start-server.sh --project-dir /path/to/project
```
When calling this via the Bash tool, set `run_in_background: true`. Then read `$STATE_DIR/server-info` on the next turn to get the URL and port.
**Codex:**
```bash
# Codex reaps background processes. The script auto-detects CODEX_CI and
# switches to foreground mode. Run it normally — no extra flags needed.
scripts/start-server.sh --project-dir /path/to/project
```
**Gemini CLI:**
```bash
# Use --foreground and set is_background: true on your shell tool call
# so the process survives across turns
scripts/start-server.sh --project-dir /path/to/project --foreground
```
**Other environments:** The server must keep running in the background across conversation turns. If your environment reaps detached processes, use `--foreground` and launch the command with your platform's background execution mechanism.
If the URL is unreachable from your browser (common in remote/containerized setups), bind a non-loopback host:
```bash
scripts/start-server.sh \
  --project-dir /path/to/project \
  --host 0.0.0.0 \
  --url-host localhost
```
Use `--url-host` to control what hostname is printed in the returned URL JSON.
## The Loop
1. **Check server is alive**, then **write HTML** to a new file in `screen_dir`:
   - Before each write, check that `$STATE_DIR/server-info` exists. If it doesn't (or `$STATE_DIR/server-stopped` exists), the server has shut down — restart it with `start-server.sh` before continuing. The server auto-exits after 30 minutes of inactivity.
   - Use semantic filenames: `platform.html`, `visual-style.html`, `layout.html`
   - **Never reuse filenames** — each screen gets a fresh file
   - Use Write tool — **never use cat/heredoc** (dumps noise into terminal)
   - Server automatically serves the newest file
2. **Tell user what to expect and end your turn:**
   - Remind them of the URL (every step, not just first)
   - Give a brief text summary of what's on screen (e.g., "Showing 3 layout options for the homepage")
   - Ask them to respond in the terminal: "Take a look and let me know what you think. Click to select an option if you'd like."
3. **On your next turn** — after the user responds in the terminal:
   - Read `$STATE_DIR/events` if it exists — this contains the user's browser interactions (clicks, selections) as JSON lines
   - Merge with the user's terminal text to get the full picture
   - The terminal message is the primary feedback; `state_dir/events` provides structured interaction data
4. **Iterate or advance** — if feedback changes current screen, write a new file (e.g., `layout-v2.html`). Only move to the next question when the current step is validated.
5. **Unload when returning to terminal** — when the next step doesn't need the browser (e.g., a clarifying question, a tradeoff discussion), push a waiting screen to clear the stale content:
   ```html
   
Continuing in terminal...
   ```
   This prevents the user from staring at a resolved choice while the conversation has moved on. When the next visual question comes up, push a new content file as usual.
6. Repeat until done.
## Writing Content Fragments
Write just the content that goes inside the page. The server wraps it in the frame template automatically (header, theme CSS, selection indicator, and all interactive infrastructure).
**Minimal example:**
```html
Which layout works better?
Consider readability and visual hierarchy
A
Single Column
Clean, focused reading experience
B
Two Column
Sidebar navigation with main content
```
That's it. No `
`, no CSS, no `</body>`, no nothing. Just the content.
**Cards example (for richer options):**
```html
Which platform should we target first?
Web
Full access to browser APIs, largest audience
iOS
Native mobile experience, App Store distribution
Android
Native mobile experience, Google Play distribution
CLI
For developers and power users
```
**Sectioned content:**
```html
Layout Options
A
Single Column
Clean, focused reading experience
B
Two Column
Sidebar navigation with main content
Color Scheme
C
Light Mode
Bright, traditional appearance
D
Dark Mode
Easy on the eyes, modern feel
```
Sections render with headers and stack vertically. Each section is independent — users can pick from each independently.
## Design Guidelines
- **One question per screen** — don't ask multiple independent questions
- **2-4 options max** — more options means decision paralysis
- **Brief labels** — a few words, not paragraphs
- **Meaningful detail** — option descriptions should explain the *difference*, not restate the label
- **Neutral ordering** — don't always put your preferred option first
- **Accessible** — use semantic HTML so screen readers work
- **No dead UI** — only include elements that do something
- **No interactivity beyond selection** — no tabs, accordions, modals, carousels, tooltips, etc.
## Server Scripts
The brainstorm server lives in `scripts/`. You'll call these in the Bash tool:
- `scripts/start-server.sh [--project-dir 
] [--host 
] [--url-host 
] [--foreground]`
- `scripts/stop-server.sh 
`
