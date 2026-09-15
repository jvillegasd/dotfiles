package install

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"io/fs"
	"os"
	"os/exec"
	"path/filepath"
	"reflect"
	"regexp"
	"slices"
	"strings"
	"unicode/utf16"
)

// object is a JSON object that keeps its key order, so rewriting a client config moves only what changed.
type object struct {
	keys []string
	vals map[string]json.RawMessage
}

func newObject() *object {
	return &object{vals: map[string]json.RawMessage{}}
}

// parseObject reads a JSON object in key order. A repeated key keeps its first position and its last value.
func parseObject(data []byte) (*object, error) {
	dec := json.NewDecoder(bytes.NewReader(data))
	tok, err := dec.Token()
	if err != nil {
		return nil, err
	}
	if tok != json.Delim('{') {
		return nil, errors.New("expected a JSON object")
	}
	o := newObject()
	for dec.More() {
		tok, err := dec.Token()
		if err != nil {
			return nil, err
		}
		var value json.RawMessage
		if err := dec.Decode(&value); err != nil {
			return nil, err
		}
		key, _ := tok.(string)
		o.set(key, value)
	}
	if _, err := dec.Token(); err != nil {
		return nil, err
	}
	if _, err := dec.Token(); err != io.EOF {
		return nil, errors.New("unexpected data after the JSON object")
	}
	return o, nil
}

func (o *object) get(key string) (json.RawMessage, bool) {
	value, ok := o.vals[key]
	return value, ok
}

func (o *object) set(key string, value json.RawMessage) {
	if _, ok := o.vals[key]; !ok {
		o.keys = append(o.keys, key)
	}
	o.vals[key] = value
}

func (o *object) del(key string) bool {
	if _, ok := o.vals[key]; !ok {
		return false
	}
	delete(o.vals, key)
	o.keys = slices.DeleteFunc(o.keys, func(k string) bool { return k == key })
	return true
}

func (o *object) MarshalJSON() ([]byte, error) {
	var b bytes.Buffer
	b.WriteByte('{')
	for i, key := range o.keys {
		if i > 0 {
			b.WriteByte(',')
		}
		b.Write(encode(key))
		b.WriteByte(':')
		b.Write(o.vals[key])
	}
	b.WriteByte('}')
	return b.Bytes(), nil
}

// encode marshals without HTML escaping, so <, >, and & stay as the user wrote them.
func encode(v any) json.RawMessage {
	var b bytes.Buffer
	enc := json.NewEncoder(&b)
	enc.SetEscapeHTML(false)
	must(enc.Encode(v))
	return bytes.TrimSuffix(b.Bytes(), []byte("\n"))
}

// render formats a document with two-space indents and non-ASCII escaped as \uXXXX, matching the configs earlier installs wrote, with one trailing newline.
func render(v any) []byte {
	var b bytes.Buffer
	must(json.Indent(&b, encode(v), "", "  "))
	var out strings.Builder
	for _, r := range b.String() {
		if r < 0x80 {
			out.WriteRune(r)
			continue
		}
		for _, unit := range utf16.Encode([]rune{r}) {
			fmt.Fprintf(&out, `\u%04x`, unit)
		}
	}
	out.WriteByte('\n')
	return []byte(out.String())
}

// same reports whether two JSON texts hold the same document, so a file that only differs in formatting is never rewritten.
func same(a, b []byte) bool {
	var x, y any
	return json.Unmarshal(a, &x) == nil && json.Unmarshal(b, &y) == nil && reflect.DeepEqual(x, y)
}

func decodeFile(path string) (map[string]any, bool) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, false
	}
	var doc map[string]any
	return doc, json.Unmarshal(data, &doc) == nil
}

func (in *installer) settingsPath() string {
	return filepath.Join(in.home, ".claude", "settings.json")
}

// readSettings parses the live settings and then clients/claude.json, naming whichever file is broken: the user's own, or the repository's.
func (in *installer) readSettings(path string) (live *object, before []byte, tracked *object) {
	before, err := os.ReadFile(path)
	if err == nil {
		live, err = parseObject(before)
	}
	if err != nil {
		die("%s is not a JSON object; fix it and re-run.", path)
	}
	trackedPath := filepath.Join(in.harness, "clients", "claude.json")
	data, err := os.ReadFile(trackedPath)
	if err == nil {
		tracked, err = parseObject(data)
	}
	if err != nil {
		die("%s is unreadable or not a JSON object.", trackedPath)
	}
	return live, before, tracked
}

// writeIfChanged writes a reconciled document, after a backup, only when it differs from what the file held.
func (in *installer) writeIfChanged(path string, before, after []byte, message string) {
	if same(before, after) {
		return
	}
	in.backupCopy(path)
	must(os.WriteFile(path, after, 0o644))
	in.log(message, path)
}

// reconcileClaudeSettings merges clients/claude.json into the live settings and leaves every other key alone, because Orca, engram setup, and the client all write machine state there. A tracked key replaces the live value, so deleting one from the tracked file deletes it from the machine. permissions merges one level down, which keeps the allowlist engram setup writes while deny stays owned.
func (in *installer) reconcileClaudeSettings() {
	path := in.settingsPath()
	must(os.MkdirAll(filepath.Dir(path), 0o755))
	if _, err := os.Stat(path); errors.Is(err, fs.ErrNotExist) {
		must(os.WriteFile(path, []byte("{}\n"), 0o644))
	}
	live, before, tracked := in.readSettings(path)
	for _, key := range tracked.keys {
		value := tracked.vals[key]
		if current, ok := live.get(key); ok && key == "permissions" {
			if merged, err := parseObject(current); err == nil {
				add, err := parseObject(value)
				must(err)
				for _, name := range add.keys {
					merged.set(name, add.vals[name])
				}
				value = encode(merged)
			}
		}
		live.set(key, value)
	}
	in.writeIfChanged(path, before, render(live), "Reconciled the tracked Claude settings in %s")
}

// removeClaudeSettings deletes exactly what reconcileClaudeSettings writes: the tracked keys, and within permissions only the tracked classes. A permissions the harness emptied goes too.
func (in *installer) removeClaudeSettings() {
	path := in.settingsPath()
	if !isFile(path) {
		return
	}
	live, before, tracked := in.readSettings(path)
	for _, key := range tracked.keys {
		current, ok := live.get(key)
		owned, err := parseObject(current)
		if !ok || key != "permissions" || err != nil {
			live.del(key)
			continue
		}
		if classes, err := parseObject(tracked.vals[key]); err == nil {
			for _, name := range classes.keys {
				owned.del(name)
			}
		}
		if len(owned.keys) == 0 {
			live.del(key)
		} else {
			live.set(key, encode(owned))
		}
	}
	in.writeIfChanged(path, before, render(live), "Removed the tracked Claude settings from %s")
}

// trackedSettingsHold reports whether every tracked key reached the live settings, or with removed, whether every one is gone while the untracked keys beside them stay.
func (in *installer) trackedSettingsHold(removed bool) bool {
	live, liveOK := decodeFile(in.settingsPath())
	tracked, trackedOK := decodeFile(filepath.Join(in.harness, "clients", "claude.json"))
	if !liveOK || !trackedOK {
		return false
	}
	holds := func(have map[string]any, key string, want any) bool {
		value, present := have[key]
		if removed {
			return !present
		}
		return reflect.DeepEqual(value, want)
	}
	for key, want := range tracked {
		if key != "permissions" {
			if !holds(live, key, want) {
				return false
			}
			continue
		}
		owned, _ := live[key].(map[string]any)
		classes, _ := want.(map[string]any)
		for name, entry := range classes {
			if !holds(owned, name, entry) {
				return false
			}
		}
	}
	return true
}

const aliasMarker = "# portable-harness aliases"

var (
	aliasLine = regexp.MustCompile(`^\s*alias\s+([A-Za-z0-9_-]+)=`)
	lineBreak = regexp.MustCompile(`\r\n|\r|\n`)
)

// reconcileAliases writes the one managed line that sources aliases.sh into ~/.zshrc, or with remove strips it, so the committed file stays the only definition. Hand-written copies of the managed aliases go either way, the retired oyolo included. A removal never creates a missing ~/.zshrc, and one that finds nothing writes nothing.
func (in *installer) reconcileAliases(remove bool) {
	rc := filepath.Join(in.home, ".zshrc")
	if !isFile(rc) {
		if remove {
			return
		}
		f, err := os.OpenFile(rc, os.O_CREATE|os.O_WRONLY, 0o644)
		must(err)
		must(f.Close())
	}
	data, err := os.ReadFile(rc)
	if err != nil {
		die("Could not reconcile aliases in %s.", rc)
	}
	current := string(data)
	source := filepath.Join(in.harness, "aliases.sh")
	// No empty entry after a final line break.
	lines := lineBreak.Split(current, -1)
	if lines[len(lines)-1] == "" {
		lines = lines[:len(lines)-1]
	}
	var kept []string
	dropped := false
	for _, line := range lines {
		alias := aliasLine.FindStringSubmatch(line)
		managed := alias != nil && (alias[1] == "ccyolo" || alias[1] == "oyolo" || alias[1] == "ocyolo")
		if managed || strings.Contains(line, aliasMarker) || strings.Contains(line, source) {
			dropped = true
			continue
		}
		kept = append(kept, line)
	}
	if remove && !dropped {
		return
	}
	for len(kept) > 0 && strings.TrimSpace(kept[len(kept)-1]) == "" {
		kept = kept[:len(kept)-1]
	}
	if !remove {
		kept = append(kept, aliasMarker, fmt.Sprintf(`[ -f "%s" ] && source "%s"`, source, source))
	}
	text := strings.Join(append(kept, ""), "\n")
	if text == current {
		return
	}
	in.backupCopy(rc)
	must(os.WriteFile(rc, []byte(strings.TrimRight(text, "\n")+"\n"), 0o644))
	if remove {
		in.log("Removed the harness aliases from %s", rc)
	} else {
		in.log("Reconciled harness aliases in %s", rc)
	}
}

// installEngram runs one `engram setup <agent>` per client, exactly as engram's docs/AGENT-SETUP.md documents. The claude-code setup is answered yes to allowlist engram's tools, because declining prompts on every memory call; the opencode setup gets a closed stdin, since a blind yes to a future question is not the same answer. Setup also rewrites the pinned absolute path of the engram binary.
func (in *installer) installEngram() {
	in.log("Reconciling Engram")
	if _, err := exec.LookPath("engram"); err != nil {
		die("Engram is missing; run without --links-only to install it.")
	}
	in.run(strings.NewReader("y\n"), "engram", "setup", "claude-code")
	in.run(nil, "engram", "setup", "opencode")
}

// installAgentBrowser registers agent-browser in both clients, since it ships no registrar of its own. Remove then add, so a re-run rewrites the pinned path; OpenCode takes a JSON edit because `opencode mcp add` is interactive.
func (in *installer) installAgentBrowser() {
	in.log("Reconciling agent-browser")
	binary, err := exec.LookPath("agent-browser")
	if err != nil {
		die("agent-browser is missing; run without --links-only to install it.")
	}
	if _, err := exec.LookPath("claude"); err != nil {
		die("Claude Code is missing; run without --links-only to install it.")
	}
	// OpenCode's config is read and validated before either client is touched, so a config this run refuses leaves both registrations as they were.
	path := filepath.Join(in.config, "opencode", "opencode.json")
	doc := newObject()
	if data, err := os.ReadFile(path); err == nil {
		if doc, err = parseObject(data); err != nil {
			die("%s: %v", path, err)
		}
	} else if !errors.Is(err, fs.ErrNotExist) {
		must(err)
	}
	servers := newObject()
	if current, ok := doc.get("mcp"); ok && string(current) != "null" {
		parsed, err := parseObject(current)
		if err != nil {
			die("%s: mcp is not a JSON object; fix it and re-run.", path)
		}
		servers = parsed
	}
	_ = exec.Command("claude", "mcp", "remove", "--scope", "user", "agent-browser").Run()
	add := exec.Command("claude", "mcp", "add", "--scope", "user", "agent-browser", "--", binary, "mcp")
	add.Stderr = in.stderr
	if err := add.Run(); err != nil {
		die("claude mcp add agent-browser failed: %v", err)
	}
	servers.set("agent-browser", encode(struct {
		Command []string `json:"command"`
		Enabled bool     `json:"enabled"`
		Type    string   `json:"type"`
	}{[]string{binary, "mcp"}, true, "local"}))
	doc.set("mcp", encode(servers))
	must(os.MkdirAll(filepath.Dir(path), 0o755))
	must(os.WriteFile(path, render(doc), 0o644))
}
