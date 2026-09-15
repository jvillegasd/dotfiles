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

// repo creates a throwaway git repository on branch, isolated from the user's git config.
func repo(t *testing.T) string {
	t.Helper()
	dir := t.TempDir()
	git(t, dir, "init", "-q", "-b", branch)
	return dir
}

func env(t *testing.T) []string {
	home := t.TempDir()
	return []string{"HOME=" + home, "GIT_CONFIG_NOSYSTEM=1", "GIT_CONFIG_GLOBAL=" + filepath.Join(home, "gitconfig")}
}

func git(t *testing.T, dir string, args ...string) string {
	t.Helper()
	cmd := exec.Command("git", append([]string{"-c", "user.name=t", "-c", "user.email=t@t"}, args...)...)
	cmd.Dir = dir
	cmd.Env = append(os.Environ(), env(t)...)
	out, err := cmd.CombinedOutput()
	if err != nil {
		t.Fatalf("git %v: %v\n%s", args, err, out)
	}
	return string(bytes.TrimSpace(out))
}

type result struct {
	stdout, stderr string
	code           int
}

// harness runs the built binary in dir. wtOutput controls `wt` on PATH: "" means absent, anything else is what a fake `wt` prints.
func harness(t *testing.T, dir, wtOutput string, args ...string) result {
	t.Helper()
	shims := t.TempDir()
	if wtOutput != "" {
		script := "#!/bin/sh\ncat <<'EOF'\n" + wtOutput + "\nEOF\n"
		if err := os.WriteFile(filepath.Join(shims, "wt"), []byte(script), 0o755); err != nil {
			t.Fatal(err)
		}
	}
	gitPath, err := exec.LookPath("git")
	if err != nil {
		t.Fatal(err)
	}
	cmd := exec.Command(binary, args...)
	cmd.Dir = dir
	cmd.Env = append(env(t), "PATH="+shims+":"+filepath.Dir(gitPath)+":/bin:/usr/bin")
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

func getJSON(t *testing.T, dir, wtOutput string) map[string]any {
	t.Helper()
	r := harness(t, dir, wtOutput, "state", "get", "--json")
	if r.code != 0 {
		t.Fatalf("get --json exited %d: %s", r.code, r.stderr)
	}
	var got map[string]any
	if err := json.Unmarshal([]byte(r.stdout), &got); err != nil {
		t.Fatalf("get --json printed invalid JSON %q: %v", r.stdout, err)
	}
	return got
}

func TestLadderSetWithoutWorktrunkUsesHarnessKeys(t *testing.T) {
	dir := repo(t)
	if r := harness(t, dir, "", "state", "ladder", "set", "go test ./..."); r.code != 0 {
		t.Fatalf("ladder set exited %d: %s", r.code, r.stderr)
	}
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
	listing := func(b string) string {
		return `{"schema":2,"items":[{"branch":"` + b + `","worktree":{"path":"/tmp/x","main":false}}]}`
	}
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
			if r := harness(t, dir, c.wt, "state", "ladder", "set", "L"); r.code != 0 {
				t.Fatalf("ladder set exited %d: %s", r.code, r.stderr)
			}
			if got := git(t, dir, "config", c.key); got != "L" {
				t.Fatalf("%s = %q", c.key, got)
			}
			if got := getJSON(t, dir, c.wt); got["store"] != c.store {
				t.Fatalf("store = %v, want %s", got["store"], c.store)
			}
		})
	}
}

func TestIncrAttemptsCountsFromZero(t *testing.T) {
	dir := repo(t)
	for want := 1; want <= 2; want++ {
		r := harness(t, dir, "", "state", "incr", "attempts")
		if r.code != 0 {
			t.Fatalf("incr exited %d: %s", r.code, r.stderr)
		}
		if got := git(t, dir, "config", "harness."+branch+".attempts"); got != fmt.Sprint(want) {
			t.Fatalf("after incr %d the key holds %q", want, got)
		}
	}
	if got := getJSON(t, dir, ""); got["attempts"] != 2.0 {
		t.Fatalf("attempts = %v, want 2", got["attempts"])
	}
}

// Value shapes agents actually wrote into these keys before the typed contract.
var legacyShapes = map[string]string{
	"json object": `{"review_round":2,"repair_passes":1}`,
	"empty array": `[]`,
	"prose":       "round two raised new blocking findings; stopped before round three",
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
			r := harness(t, dir, "", "state", "incr", "attempts")
			if r.code != 0 || !strings.Contains(r.stderr, raw) {
				t.Fatalf("incr exited %d, stderr %q should name the replaced text", r.code, r.stderr)
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
		if r := harness(t, dir, "", "state", "escalate", "--reason", reason); r.code != 0 {
			t.Fatalf("escalate exited %d: %s", r.code, r.stderr)
		}
		if got := git(t, dir, "config", "harness."+branch+".escalations"); got != fmt.Sprint(i+1) {
			t.Fatalf("escalations = %q, want %d", got, i+1)
		}
	}
	if got := getJSON(t, dir, ""); got["escalations"] != 2.0 || got["reason"] != "loop cap tripped" {
		t.Fatalf("get --json = %v", got)
	}
}

func configHas(t *testing.T, dir, key string) bool {
	t.Helper()
	cmd := exec.Command("git", "config", "--get", key)
	cmd.Dir = dir
	cmd.Env = append(os.Environ(), env(t)...)
	return cmd.Run() == nil
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
	r := harness(t, dir, "", "state", "prune")
	if r.code != 0 {
		t.Fatalf("prune exited %d: %s", r.code, r.stderr)
	}
	if !strings.Contains(r.stdout, "gone/one") || !strings.Contains(r.stdout, "gone/two") || strings.Contains(r.stdout, "live") {
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

func TestHelpAndUnknownCommands(t *testing.T) {
	outside := t.TempDir()
	if r := harness(t, outside, "", "--help"); r.code != 0 || !strings.Contains(r.stdout, "state") {
		t.Fatalf("--help exited %d: %q", r.code, r.stdout)
	}
	r := harness(t, outside, "", "state", "--help")
	if r.code != 0 {
		t.Fatalf("state --help outside a repository exited %d: %s", r.code, r.stderr)
	}
	for _, op := range []string{"ladder set", "incr", "escalate", "get", "prune"} {
		if !strings.Contains(r.stdout, op) {
			t.Errorf("state --help does not list %q", op)
		}
	}
	for _, args := range [][]string{{"bogus"}, {"state", "bogus"}} {
		if r := harness(t, repo(t), "", args...); r.code == 0 || strings.Count(r.stderr, "\n") != 1 {
			t.Errorf("%v exited %d with stderr %q, want non-zero and one line", args, r.code, r.stderr)
		}
	}
}
