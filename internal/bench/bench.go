// Package bench reports whether a harness change moved cost and friction by
// comparing the real session population before and after its commit date,
// reading each client's own session store. Cost and friction only; quality
// stays a human read of the transcripts.
package bench

import (
	"database/sql"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"io/fs"
	"math"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"time"
	"unicode"

	_ "modernc.org/sqlite"
)

// metrics is the report's row order: three cost, then the two the harness
// claims to move, then three friction.
var metrics = []string{"turns", "tool_calls", "minutes", "commands", "delegation", "interrupts", "denials", "errors"}

const thin = 20

const claudeInterrupt = "[Request interrupted by user"

// claudeDenials are the two sentences Claude Code writes when a human refuses
// a call. `has been denied` is anchored on the sentence around it: unanchored,
// the phrase matched a grep of this very file quoted back in a tool result.
var claudeDenials = [][]string{
	{"The user doesn't want to proceed with this tool use"},
	{"Permission to use ", " has been denied"},
}

var claudeNonTurn = []string{claudeInterrupt, "<command-name>", "<command-message", "<local-command", "<system-reminder>", "<task-notification>"}

// opencodeQuery is a row per top-level session. OpenCode gives a subagent a
// session of its own carrying the parent's id, so the parents are the
// population and the children are that population's delegation.
const opencodeQuery = `
select s.time_created,
       s.time_updated,
       s.directory,
       (select count(*) from message m
         where m.session_id = s.id and json_extract(m.data, '$.role') = 'user'),
       (select count(*) from part p
         where p.session_id = s.id and json_extract(p.data, '$.type') = 'tool'),
       (select count(*) from message m join session c on c.id = m.session_id
         where c.parent_id = s.id)
from session s
where s.parent_id is null
`

const usage = `Usage: harness bench --split <date> [--since <date>] [--client <name>] [--home <dir>] [--rows]

Compare the session population before and after a harness change.

  --split   Commit date of the change under test, YYYY-MM-DD. Sessions before
            it are before, on or after it after. Required.
  --since   Ignore sessions older than this date.
  --client  Limit to claude or opencode; repeatable (default: both).
  --home    Session-store root (default: the current home).
  --rows    Print one JSON object per session instead of the report.

Run it from inside the checkout, where the work patterns live in
harness/bench/cohorts.json.
`

// Command runs `harness bench` and returns the process exit code.
func Command(args []string, stdout, stderr io.Writer) int {
	flags := flag.NewFlagSet("bench", flag.ContinueOnError)
	flags.SetOutput(stderr)
	flags.Usage = func() {}
	var split, since, home string
	var rows bool
	var clients clientList
	flags.StringVar(&split, "split", "", "commit date of the harness change under test")
	flags.StringVar(&since, "since", "", "ignore sessions older than this date")
	flags.StringVar(&home, "home", homeDir(), "session-store root")
	flags.BoolVar(&rows, "rows", false, "print one JSON object per session instead of the report")
	flags.Var(&clients, "client", "limit to one client; repeatable")
	if err := flags.Parse(args); err != nil {
		if errors.Is(err, flag.ErrHelp) {
			fmt.Fprint(stdout, usage)
			return 0
		}
		fmt.Fprint(stderr, usage)
		return 2
	}
	if split == "" {
		fmt.Fprintln(stderr, "harness bench: --split is required")
		return 2
	}
	splitDate, err := parseDate(split)
	if err != nil {
		fmt.Fprintf(stderr, "harness bench: --split: %v\n", err)
		return 2
	}
	var sinceDate *time.Time
	if since != "" {
		date, err := parseDate(since)
		if err != nil {
			fmt.Fprintf(stderr, "harness bench: --since: %v\n", err)
			return 2
		}
		sinceDate = &date
	}
	if len(clients) == 0 {
		clients = clientList{"claude", "opencode"}
	}
	root, err := findRoot()
	if err != nil {
		fmt.Fprintf(stderr, "harness bench: %v\n", err)
		return 1
	}
	sessions, err := collect(home, clients, patterns(root, stderr))
	if err != nil {
		fmt.Fprintf(stderr, "harness bench: %v\n", err)
		return 1
	}
	if rows {
		if sinceDate != nil {
			sessions = filterSince(sessions, *sinceDate)
		}
		fmt.Fprint(stdout, renderRows(sessions))
		return 0
	}
	fmt.Fprintln(stdout, renderReport(sessions, splitDate, sinceDate))
	return 0
}

// clientList is the repeatable --client flag, restricted to the supported readers.
type clientList []string

func (c *clientList) String() string { return strings.Join(*c, ",") }

func (c *clientList) Set(value string) error {
	if value != "claude" && value != "opencode" {
		return fmt.Errorf("invalid client %q (want claude or opencode)", value)
	}
	*c = append(*c, value)
	return nil
}

func homeDir() string {
	if home, err := os.UserHomeDir(); err == nil {
		return home
	}
	return os.Getenv("HOME")
}

func parseDate(value string) (time.Time, error) {
	day, err := time.Parse("2006-01-02", value)
	if err != nil {
		return time.Time{}, err
	}
	return time.Date(day.Year(), day.Month(), day.Day(), 0, 0, 0, 0, time.UTC), nil
}

// findRoot walks up to the checkout holding harness/POLICY.md, so cohorts come
// from the working directory's checkout rather than a fixed path.
func findRoot() (string, error) {
	dir, err := os.Getwd()
	if err != nil {
		return "", err
	}
	for {
		if _, err := os.Stat(filepath.Join(dir, "harness", "POLICY.md")); err == nil {
			return dir, nil
		}
		parent := filepath.Dir(dir)
		if parent == dir {
			return "", errors.New("run harness bench from inside the dotfiles checkout")
		}
		dir = parent
	}
}

// patterns reads the project patterns that mark a session as work. The
// committed example names nobody, so an unconfigured checkout reports one
// population and never a misleading split.
func patterns(root string, stderr io.Writer) []string {
	for _, name := range []string{"cohorts.json", "cohorts.example.json"} {
		data, err := os.ReadFile(filepath.Join(root, "harness", "bench", name))
		if err != nil {
			if errors.Is(err, fs.ErrNotExist) {
				continue
			}
			fmt.Fprintf(stderr, "%s: %v\n", name, err)
			return nil
		}
		var doc struct {
			Work []string `json:"work"`
		}
		if err := json.Unmarshal(data, &doc); err != nil {
			fmt.Fprintf(stderr, "%s: %v\n", name, err)
			return nil
		}
		return doc.Work
	}
	return nil
}

// session is one parsed session. values holds the eight metrics, each an int
// for counts, a float64 for minutes, or nil when the client does not record it.
type session struct {
	client  string
	date    time.Time
	project *string
	values  map[string]any
	cohort  string
}

func newSession(client string, started time.Time, project *string, values map[string]any) *session {
	return &session{
		client:  client,
		date:    time.Date(started.Year(), started.Month(), started.Day(), 0, 0, 0, 0, time.UTC),
		project: project,
		values:  values,
	}
}

func (s *session) metric(name string) (float64, bool) {
	switch value := s.values[name].(type) {
	case int:
		return float64(value), true
	case float64:
		return value, true
	}
	return 0, false
}

func collect(home string, clients []string, work []string) ([]*session, error) {
	var sessions []*session
	for _, client := range clients {
		var found []*session
		var err error
		switch client {
		case "claude":
			found, err = claudeSessions(home)
		case "opencode":
			found, err = opencodeSessions(home)
		}
		if err != nil {
			return nil, err
		}
		sessions = append(sessions, found...)
	}
	for _, s := range sessions {
		s.cohort = cohort(s.project, work)
	}
	return sessions, nil
}

// --- Claude Code: ~/.claude/projects/<slug>/<session>.jsonl -------------------

func claudeSessions(home string) ([]*session, error) {
	root := filepath.Join(home, ".claude", "projects")
	if !isDir(root) {
		return nil, nil
	}
	// `<project>/<session>.jsonl` only. Recursing would sweep the subagent
	// sidecars in as sessions of their own.
	paths, _ := filepath.Glob(filepath.Join(root, "*", "*.jsonl"))
	sort.Strings(paths)
	var sessions []*session
	for _, path := range paths {
		s, err := readClaude(path)
		if err != nil {
			return nil, err
		}
		if s != nil {
			sessions = append(sessions, s)
		}
	}
	return sessions, nil
}

func readClaude(path string) (*session, error) {
	lines, err := entries(path)
	if err != nil {
		return nil, err
	}
	var first, last time.Time
	seen := false
	turns, tools, commands, interrupts, denials, failures := 0, 0, 0, 0, 0, 0
	for _, entry := range lines {
		if stamp, ok := parseStamp(entry["timestamp"]); ok {
			if !seen {
				first = stamp
				seen = true
			}
			last = stamp
		}
		blocks := blocksOf(messageContent(entry))
		if entry["type"] == "assistant" {
			for _, block := range blocks {
				if block["type"] == "tool_use" {
					tools++
				}
			}
			continue
		}
		if entry["type"] != "user" {
			continue
		}
		// An entry is a turn when it carries at least one block a human typed.
		// Anything the client injected can ride along in the same entry, so this
		// is per block: a real prompt arrives with its system reminders attached.
		typed := false
		for _, block := range blocks {
			body := claudeText(block)
			if block["type"] == "tool_result" {
				// A tool result is the harness answering itself, never a turn.
				if isDenial(body) {
					denials++
				} else if truthy(block["is_error"]) {
					failures++
				}
				continue
			}
			commands += strings.Count(body, "<command-name>")
			interrupts += strings.Count(body, claudeInterrupt)
			typed = typed || (strings.TrimSpace(body) != "" && !hasNonTurnPrefix(strings.TrimLeftFunc(body, unicode.IsSpace)))
		}
		if typed && !truthy(entry["isMeta"]) {
			turns++
		}
	}
	if !seen {
		return nil, nil
	}
	delegation, err := claudeDelegation(path)
	if err != nil {
		return nil, err
	}
	project := filepath.Base(filepath.Dir(path))
	return newSession("claude", first, &project, map[string]any{
		"turns": turns, "tool_calls": tools, "minutes": round1(last.Sub(first).Seconds() / 60),
		"commands": commands, "delegation": delegation,
		"interrupts": interrupts, "denials": denials, "errors": failures,
	}), nil
}

// claudeDelegation counts the messages in this session's subagent sidecars.
func claudeDelegation(path string) (int, error) {
	stem := strings.TrimSuffix(filepath.Base(path), ".jsonl")
	sidecars, _ := filepath.Glob(filepath.Join(filepath.Dir(path), stem, "subagents", "*.jsonl"))
	sort.Strings(sidecars)
	total := 0
	for _, sidecar := range sidecars {
		lines, err := entries(sidecar)
		if err != nil {
			return 0, err
		}
		for _, entry := range lines {
			if entry["type"] == "user" || entry["type"] == "assistant" {
				total++
			}
		}
	}
	return total, nil
}

func messageContent(entry map[string]any) any {
	message, ok := entry["message"].(map[string]any)
	if !ok {
		return nil
	}
	return message["content"]
}

// blocksOf normalizes an entry's content to a list of blocks. A non-list
// content becomes one text block, so a plain string is treated like a block.
func blocksOf(content any) []map[string]any {
	if list, ok := content.([]any); ok {
		var blocks []map[string]any
		for _, item := range list {
			if block, ok := item.(map[string]any); ok {
				blocks = append(blocks, block)
			}
		}
		return blocks
	}
	return []map[string]any{{"text": content}}
}

func claudeText(block map[string]any) string {
	value := block["text"]
	if !truthy(value) {
		value = block["content"]
	}
	if !truthy(value) {
		return ""
	}
	if text, ok := value.(string); ok {
		return text
	}
	data, err := json.Marshal(value)
	if err != nil {
		return fmt.Sprint(value)
	}
	return string(data)
}

func hasNonTurnPrefix(body string) bool {
	for _, prefix := range claudeNonTurn {
		if strings.HasPrefix(body, prefix) {
			return true
		}
	}
	return false
}

func isDenial(body string) bool {
	for _, literal := range claudeDenials {
		matched := true
		for _, part := range literal {
			if !strings.Contains(body, part) {
				matched = false
				break
			}
		}
		if matched {
			return true
		}
	}
	return false
}

// truthy is Python's truthiness, which the ported counting rules rely on.
func truthy(value any) bool {
	switch v := value.(type) {
	case nil:
		return false
	case bool:
		return v
	case string:
		return v != ""
	case float64:
		return v != 0
	case int:
		return v != 0
	case []any:
		return len(v) > 0
	case map[string]any:
		return len(v) > 0
	}
	return true
}

func parseStamp(value any) (time.Time, bool) {
	text, ok := value.(string)
	if !ok {
		return time.Time{}, false
	}
	text = strings.ReplaceAll(text, "Z", "+00:00")
	// Python's datetime.fromisoformat accepts more shapes than RFC3339, and a
	// stamp it parses but this drops would remove the session from the run.
	for _, layout := range []string{time.RFC3339, "2006-01-02T15:04:05", "2006-01-02 15:04:05", "2006-01-02"} {
		if stamp, err := time.Parse(layout, text); err == nil {
			return stamp, true
		}
	}
	return time.Time{}, false
}

// entries yields the parsed dict lines of a JSONL transcript, skipping damage.
// A file that cannot be read is an error: the pre-port bench raised on it, and a
// silently dropped transcript would bias every median.
func entries(path string) ([]map[string]any, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var out []map[string]any
	for _, line := range strings.Split(string(data), "\n") {
		line = strings.TrimSpace(line)
		if line == "" {
			continue
		}
		var value any
		if json.Unmarshal([]byte(line), &value) != nil {
			continue
		}
		if entry, ok := value.(map[string]any); ok {
			out = append(out, entry)
		}
	}
	return out, nil
}

// --- OpenCode: ~/.local/share/opencode/opencode.db ---------------------------

func opencodeSessions(home string) ([]*session, error) {
	path := filepath.Join(home, ".local", "share", "opencode", "opencode.db")
	if !isFile(path) {
		return nil, nil
	}
	// Read-only: the database may belong to a running client.
	db, err := sql.Open("sqlite", "file:"+path+"?mode=ro&immutable=1")
	if err != nil {
		return nil, err
	}
	defer db.Close()
	rows, err := db.Query(opencodeQuery)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var sessions []*session
	for rows.Next() {
		var created, updated int64
		var directory sql.NullString
		var turns, tools, delegation int
		if err := rows.Scan(&created, &updated, &directory, &turns, &tools, &delegation); err != nil {
			return nil, err
		}
		var project *string
		if directory.Valid {
			project = &directory.String
		}
		started := time.UnixMilli(created).UTC()
		changed := time.UnixMilli(updated).UTC()
		// OpenCode records no interrupt, no declined call, no failed result, and
		// no slash command durably.
		sessions = append(sessions, newSession("opencode", started, project, map[string]any{
			"turns": turns, "tool_calls": tools,
			"minutes":    round1(changed.Sub(started).Seconds() / 60),
			"delegation": delegation,
		}))
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	return sessions, nil
}

// --- cohorts ------------------------------------------------------------------

func canon(value string) string {
	var b strings.Builder
	dash := false
	for _, r := range strings.ToLower(value) {
		if r == '-' || r == '/' {
			if !dash {
				b.WriteByte('/')
			}
			dash = true
			continue
		}
		dash = false
		b.WriteRune(r)
	}
	return b.String()
}

func cohort(project *string, work []string) string {
	if project == nil {
		return "personal"
	}
	folded := canon(*project)
	for _, pattern := range work {
		if strings.Contains(folded, canon(pattern)) {
			return "work"
		}
	}
	return "personal"
}

// --- report -------------------------------------------------------------------

func filterSince(sessions []*session, since time.Time) []*session {
	var out []*session
	for _, s := range sessions {
		if !s.date.Before(since) {
			out = append(out, s)
		}
	}
	return out
}

func median(sessions []*session, metric string) *float64 {
	var values []float64
	for _, s := range sessions {
		if value, ok := s.metric(metric); ok {
			values = append(values, value)
		}
	}
	if len(values) == 0 {
		return nil
	}
	sort.Float64s(values)
	n := len(values)
	if n%2 == 1 {
		middle := values[n/2]
		return &middle
	}
	middle := (values[n/2-1] + values[n/2]) / 2
	return &middle
}

func cell(value *float64) string {
	if value == nil {
		return fmt.Sprintf("%10s", "-")
	}
	return fmt.Sprintf("%10.1f", *value)
}

func deltaCell(before, after *float64) string {
	if before == nil || after == nil {
		return fmt.Sprintf("%10s", "-")
	}
	return fmt.Sprintf("%+10.1f", *after-*before)
}

func block(label string, cohort []*session, split time.Time) []string {
	var before, after []*session
	for _, s := range cohort {
		if s.date.Before(split) {
			before = append(before, s)
		} else {
			after = append(after, s)
		}
	}
	lines := []string{
		"",
		label,
		fmt.Sprintf("  %-12s%10s%10s%10s", "metric", "before", "after", "delta"),
		fmt.Sprintf("  %-12s%10d%10d%10s", "sessions", len(before), len(after), ""),
	}
	for _, metric := range metrics {
		b, a := median(before, metric), median(after, metric)
		lines = append(lines, fmt.Sprintf("  %-12s%s%s%s", metric, cell(b), cell(a), deltaCell(b, a)))
	}
	if len(before) < thin || len(after) < thin {
		lines = append(lines, fmt.Sprintf("  warning: a cohort has fewer than %d sessions; noise, not a result.", thin))
	}
	return lines
}

func renderReport(sessions []*session, split time.Time, since *time.Time) string {
	if since != nil {
		sessions = filterSince(sessions, *since)
	}
	header := fmt.Sprintf("split %s", split.Format("2006-01-02"))
	if since != nil {
		header += fmt.Sprintf("  since %s", since.Format("2006-01-02"))
	}
	lines := []string{header}
	// Split by cohort only once one is configured. Unconfigured, every session
	// is personal, and a "personal" heading would draw a distinction nobody made.
	groups := []string{""}
	for _, s := range sessions {
		if s.cohort == "work" {
			groups = []string{"work", "personal"}
			break
		}
	}
	for _, client := range []string{"claude", "opencode"} {
		for _, group := range groups {
			var selected []*session
			for _, s := range sessions {
				if s.client == client && (group == "" || s.cohort == group) {
					selected = append(selected, s)
				}
			}
			if len(selected) == 0 {
				continue
			}
			label := client
			if group != "" {
				label = client + "  " + group
			}
			lines = append(lines, block(label, selected, split)...)
		}
	}
	if len(lines) == 1 {
		lines = append(lines, "no sessions found")
	}
	return strings.Join(lines, "\n")
}

func renderRows(sessions []*session) string {
	sort.SliceStable(sessions, func(i, j int) bool {
		if !sessions[i].date.Equal(sessions[j].date) {
			return sessions[i].date.Before(sessions[j].date)
		}
		return sessions[i].client < sessions[j].client
	})
	var b strings.Builder
	for _, s := range sessions {
		b.WriteString(rowJSON(s))
		b.WriteByte('\n')
	}
	return b.String()
}

func rowJSON(s *session) string {
	parts := []string{
		jsonField("client", quote(s.client)),
		jsonField("date", quote(s.date.Format("2006-01-02"))),
		jsonField("project", nullableString(s.project)),
	}
	for _, metric := range metrics {
		parts = append(parts, jsonField(metric, valueJSON(s.values[metric])))
	}
	parts = append(parts, jsonField("cohort", quote(s.cohort)))
	return "{" + strings.Join(parts, ", ") + "}"
}

func jsonField(key, value string) string { return quote(key) + ": " + value }

func quote(value string) string {
	data, err := json.Marshal(value)
	if err != nil {
		return strconv.Quote(value)
	}
	return string(data)
}

func nullableString(value *string) string {
	if value == nil {
		return "null"
	}
	return quote(*value)
}

func valueJSON(value any) string {
	switch v := value.(type) {
	case nil:
		return "null"
	case int:
		return strconv.Itoa(v)
	case float64:
		return floatJSON(v)
	}
	return "null"
}

// floatJSON matches Python's json.dumps, which keeps a decimal point on an
// integer-valued float (9.0, not 9).
func floatJSON(value float64) string {
	text := strconv.FormatFloat(value, 'g', -1, 64)
	if !strings.ContainsAny(text, ".eE") {
		text += ".0"
	}
	return text
}

// --- numbers ------------------------------------------------------------------

// round1 matches Python's round(value, 1), which rounds half to even on the
// exact binary value; strconv.FormatFloat is the same correct rounding.
func round1(value float64) float64 {
	if math.IsNaN(value) || math.IsInf(value, 0) {
		return value
	}
	rounded, err := strconv.ParseFloat(strconv.FormatFloat(value, 'f', 1, 64), 64)
	if err != nil {
		return value
	}
	return rounded
}

func isDir(path string) bool {
	info, err := os.Stat(path)
	return err == nil && info.IsDir()
}

func isFile(path string) bool {
	info, err := os.Stat(path)
	return err == nil && info.Mode().IsRegular()
}
