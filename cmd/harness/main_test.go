package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
)

var binary string

// TestMain builds the real binary once, so every test drives the command boundary a caller sees.
func TestMain(m *testing.M) {
	dir, err := os.MkdirTemp("", "harness-bin")
	if err != nil {
		panic(err)
	}
	binary = filepath.Join(dir, "harness")
	if out, err := exec.Command("go", "build", "-o", binary, ".").CombinedOutput(); err != nil {
		panic(string(out))
	}
	code := m.Run()
	os.RemoveAll(dir)
	os.Exit(code)
}

const branch = "feat/1-x"

// repo creates a throwaway git repository on branch.
func repo(t *testing.T) string {
	t.Helper()
	dir := t.TempDir()
	git(t, dir, "init", "-q", "-b", branch)
	return dir
}

// env isolates git from the user's config; each directory gets its own HOME and global config file.
func env(dir string) []string {
	home := filepath.Join(dir, ".home")
	return []string{"HOME=" + home, "GIT_CONFIG_NOSYSTEM=1", "GIT_CONFIG_GLOBAL=" + filepath.Join(home, "gitconfig")}
}

func git(t *testing.T, dir string, args ...string) string {
	t.Helper()
	cmd := exec.Command("git", append([]string{"-c", "user.name=t", "-c", "user.email=t@t"}, args...)...)
	cmd.Dir = dir
	cmd.Env = append(os.Environ(), env(dir)...)
	out, err := cmd.CombinedOutput()
	if err != nil {
		t.Fatalf("git %v: %v\n%s", args, err, out)
	}
	return string(bytes.TrimSpace(out))
}

func configHas(t *testing.T, dir, key string) bool {
	t.Helper()
	cmd := exec.Command("git", "config", "--local", "--get", key)
	cmd.Dir = dir
	cmd.Env = append(os.Environ(), env(dir)...)
	return cmd.Run() == nil
}

type result struct {
	stdout, stderr string
	code           int
}

// schema1 is the shape `wt list --format=json` prints when a config pins json-schema 1, as the tracked Worktrunk config does.
const schema1 = `[{"branch":"` + branch + `","path":"/tmp/x","kind":"worktree"}]`

// harness runs the built binary in dir. wt "" means absent; otherwise a fake wt prints wt for schema 2 and schema1 otherwise.
func harness(t *testing.T, dir, wt string, args ...string) result {
	t.Helper()
	shims := t.TempDir()
	gitPath, err := exec.LookPath("git")
	if err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink(gitPath, filepath.Join(shims, "git")); err != nil {
		t.Fatal(err)
	}
	path := shims + ":/usr/bin:/bin"
	if wt == "" {
		for _, d := range []string{"/usr/bin", "/bin"} {
			if _, err := os.Stat(filepath.Join(d, "wt")); err == nil {
				t.Fatalf("a real wt in %s makes the absent mode impossible", d)
			}
		}
	} else {
		script := "#!/bin/sh\ncase \"$*\" in\n*list.json-schema=2*) cat <<'EOF'\n" + wt + "\nEOF\n;;\n*) cat <<'EOF'\n" + schema1 + "\nEOF\n;;\nesac\n"
		if err := os.WriteFile(filepath.Join(shims, "wt"), []byte(script), 0o755); err != nil {
			t.Fatal(err)
		}
	}
	cmd := exec.Command(binary, args...)
	cmd.Dir = dir
	cmd.Env = append(env(dir), "PATH="+path)
	var stdout, stderr bytes.Buffer
	cmd.Stdout, cmd.Stderr = &stdout, &stderr
	err = cmd.Run()
	code := 0
	if exit, ok := err.(*exec.ExitError); ok {
		code = exit.ExitCode()
	} else if err != nil {
		t.Fatal(err)
	}
	return result{stdout.String(), stderr.String(), code}
}

func ok(t *testing.T, r result, what string) result {
	t.Helper()
	if r.code != 0 {
		t.Fatalf("%s exited %d: %s", what, r.code, r.stderr)
	}
	return r
}

func getJSON(t *testing.T, dir, wt string) map[string]any {
	t.Helper()
	r := ok(t, harness(t, dir, wt, "state", "get", "--json"), "get --json")
	var got map[string]any
	if err := json.Unmarshal([]byte(r.stdout), &got); err != nil {
		t.Fatalf("get --json printed invalid JSON %q: %v", r.stdout, err)
	}
	return got
}

func listing(b string) string {
	return `{"schema":2,"items":[{"branch":"` + b + `","worktree":{"path":"/tmp/x","main":false}}]}`
}

func TestLadderSetWithoutWorktrunkUsesHarnessKeys(t *testing.T) {
	dir := repo(t)
	ok(t, harness(t, dir, "", "state", "ladder", "set", "go test ./..."), "ladder set")
	if got := git(t, dir, "config", "harness."+branch+".ladder"); got != "go test ./..." {
		t.Fatalf("harness ladder key = %q", got)
	}
	got := getJSON(t, dir, "")
	if got["branch"] != branch || got["store"] != "harness" || got["ladder"] != "go test ./..." {
		t.Fatalf("get --json = %v", got)
	}
	if got["attempts"] != 0.0 || got["escalations"] != 0.0 {
		t.Fatalf("unset counters should read 0, got %v", got)
	}
}

func TestStoreFollowsWorktrunkListing(t *testing.T) {
	cases := []struct {
		name, wt, store, key string
	}{
		{"listed", listing(branch), "worktrunk", "worktrunk.state." + branch + ".vars.ladder"},
		{"other branch listed", listing("main"), "harness", "harness." + branch + ".ladder"},
		{"malformed output", "not json", "harness", "harness." + branch + ".ladder"},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			dir := repo(t)
			ok(t, harness(t, dir, c.wt, "state", "ladder", "set", "L"), "ladder set")
			if got := git(t, dir, "config", c.key); got != "L" {
				t.Fatalf("%s = %q", c.key, got)
			}
			if got := getJSON(t, dir, c.wt); got["store"] != c.store {
				t.Fatalf("store = %v, want %s", got["store"], c.store)
			}
		})
	}
}

func TestIncrAttemptsCountsFromExistingInteger(t *testing.T) {
	dir := repo(t)
	for want := 1; want <= 2; want++ {
		ok(t, harness(t, dir, "", "state", "incr", "attempts"), "incr")
		if got := git(t, dir, "config", "harness."+branch+".attempts"); got != fmt.Sprint(want) {
			t.Fatalf("after incr %d the key holds %q", want, got)
		}
	}
	seeded := repo(t)
	git(t, seeded, "config", "harness."+branch+".attempts", "4")
	if got := getJSON(t, seeded, ""); got["attempts"] != 4.0 {
		t.Fatalf("a stored integer should read as itself, got %v", got)
	}
	if r := ok(t, harness(t, seeded, "", "state", "incr", "attempts"), "incr"); strings.TrimSpace(r.stdout) != "5" || r.stderr != "" {
		t.Fatalf("incr over 4 printed %q with stderr %q", r.stdout, r.stderr)
	}
}

// Value shapes that must read as legacy: what agents wrote before the typed contract, plus integers in a non-canonical spelling.
var legacyShapes = map[string]string{
	"json object":    `{"review_round":2,"repair_passes":1}`,
	"empty array":    `[]`,
	"prose":          "round two raised new blocking findings in round-one code.\nStopped before round three.",
	"signed integer": "+5",
	"padded integer": "007",
}

func TestLegacyCounterReadsRawAndIncrReplacesIt(t *testing.T) {
	for name, raw := range legacyShapes {
		t.Run(name, func(t *testing.T) {
			dir := repo(t)
			git(t, dir, "config", "harness."+branch+".attempts", raw)
			got := getJSON(t, dir, "")
			legacy, _ := got["legacy"].(map[string]any)
			if got["attempts"] != nil || legacy["attempts"] != raw {
				t.Fatalf("get --json = %v, want attempts null and legacy.attempts %q", got, raw)
			}
			if r := harness(t, dir, "", "state", "get"); !strings.Contains(r.stdout, "attempts: legacy: "+raw) {
				t.Fatalf("text get = %q", r.stdout)
			}
			if r := ok(t, harness(t, dir, "", "state", "incr", "attempts"), "incr"); !strings.Contains(r.stderr, raw) {
				t.Fatalf("incr stderr %q should name the replaced text", r.stderr)
			}
			if got := git(t, dir, "config", "harness."+branch+".attempts"); got != "1" {
				t.Fatalf("incr over legacy wrote %q, want 1", got)
			}
		})
	}
}

func TestEscalateRequiresReasonAndKeepsTheLatest(t *testing.T) {
	dir := repo(t)
	if r := harness(t, dir, "", "state", "escalate"); r.code == 0 || strings.Count(r.stderr, "\n") != 1 {
		t.Fatalf("escalate without --reason exited %d with stderr %q, want non-zero and one line", r.code, r.stderr)
	}
	for i, reason := range []string{"round two found a new bug", "loop cap tripped"} {
		ok(t, harness(t, dir, "", "state", "escalate", "--reason", reason), "escalate")
		if got := git(t, dir, "config", "harness."+branch+".escalations"); got != fmt.Sprint(i+1) {
			t.Fatalf("escalations = %q, want %d", got, i+1)
		}
	}
	if got := getJSON(t, dir, ""); got["escalations"] != 2.0 || got["reason"] != "loop cap tripped" {
		t.Fatalf("get --json = %v", got)
	}
}

func TestEscalateOverLegacyNamesReplacedText(t *testing.T) {
	dir := repo(t)
	raw := legacyShapes["prose"]
	git(t, dir, "config", "harness."+branch+".escalations", raw)
	r := ok(t, harness(t, dir, "", "state", "escalate", "--reason", "cap"), "escalate")
	if !strings.Contains(r.stderr, raw) {
		t.Fatalf("escalate stderr %q should name the replaced text", r.stderr)
	}
	if got := getJSON(t, dir, ""); got["escalations"] != 1.0 || got["reason"] != "cap" {
		t.Fatalf("get --json = %v", got)
	}
}

func TestStateSurvivesStoreFlipsBothWays(t *testing.T) {
	dir := repo(t)
	listed := listing(branch)
	worktrunkKey, harnessKey := "worktrunk.state."+branch+".vars.attempts", "harness."+branch+".attempts"
	for want, wt := range []string{listed, listed, "", listed} {
		r := ok(t, harness(t, dir, wt, "state", "incr", "attempts"), "incr")
		if strings.TrimSpace(r.stdout) != fmt.Sprint(want+1) {
			t.Fatalf("incr %d printed %q, want %d", want+1, r.stdout, want+1)
		}
		if configHas(t, dir, worktrunkKey) == configHas(t, dir, harnessKey) {
			t.Fatalf("after incr %d exactly one store should hold attempts", want+1)
		}
	}
	for _, wt := range []string{listed, ""} {
		if got := getJSON(t, dir, wt); got["attempts"] != 4.0 {
			t.Fatalf("after flipping back, get with wt=%q reads %v, want 4", wt, got["attempts"])
		}
	}
}

func TestUnscopedCounterIsIgnored(t *testing.T) {
	dir := repo(t)
	git(t, dir, "config", "harness.attempts", "round two stopped")
	if got := getJSON(t, dir, ""); got["attempts"] != 0.0 || got["legacy"] != nil {
		t.Fatalf("an unscoped key belongs to no branch, got %v", got)
	}
}

func TestPruneRemovesOnlyGoneBranches(t *testing.T) {
	dir := repo(t)
	git(t, dir, "commit", "-q", "--allow-empty", "-m", "init")
	git(t, dir, "branch", "live")
	kept := []string{"worktrunk.state.live.vars.attempts", "harness.live.attempts", "harness.attempts"}
	gone := []string{"worktrunk.state.gone/one.vars.attempts", "worktrunk.state.gone/one.vars.ladder", "harness.gone/two.escalations"}
	for _, key := range append(append([]string{}, kept...), gone...) {
		git(t, dir, "config", key, "1")
	}
	if err := os.MkdirAll(filepath.Join(dir, ".home"), 0o755); err != nil {
		t.Fatal(err)
	}
	git(t, dir, "config", "--global", "worktrunk.state.gone/global.vars.attempts", "1")
	r := ok(t, harness(t, dir, "", "state", "prune"), "prune")
	if !strings.Contains(r.stdout, "gone/one") || !strings.Contains(r.stdout, "gone/two") || strings.Contains(r.stdout, "live") || strings.Contains(r.stdout, "global") {
		t.Fatalf("prune reported %q", r.stdout)
	}
	for _, key := range kept {
		if !configHas(t, dir, key) {
			t.Errorf("prune removed %s", key)
		}
	}
	for _, key := range gone {
		if configHas(t, dir, key) {
			t.Errorf("prune kept %s", key)
		}
	}
}

func TestHelpAndUsageErrors(t *testing.T) {
	outside := t.TempDir()
	if r := harness(t, outside, "", "--help"); r.code != 0 || !strings.Contains(r.stdout, "state") {
		t.Fatalf("--help exited %d: %q", r.code, r.stdout)
	}
	r := ok(t, harness(t, outside, "", "state", "--help"), "state --help outside a repository")
	for _, op := range []string{"ladder set", "incr attempts", "escalate", "get", "prune"} {
		if !strings.Contains(r.stdout, op) {
			t.Errorf("state --help does not list %q", op)
		}
	}
	for _, args := range [][]string{{"bogus"}, {"state", "bogus"}, {"state", "incr", "escalations"}, {"state", "get", "--jsn"}, {"state", "prune", "extra"}} {
		r := harness(t, outside, "", args...)
		if r.code == 0 || strings.Count(r.stderr, "\n") != 1 || strings.Contains(r.stderr, "not on a branch") {
			t.Errorf("%v exited %d with stderr %q, want a one-line usage error", args, r.code, r.stderr)
		}
	}
}
