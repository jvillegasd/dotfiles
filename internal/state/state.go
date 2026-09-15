// Package state reads and writes the per-branch oracle ladder and rabbit-hole counters the harness policy persists in git config.
package state

import (
	"encoding/json"
	"errors"
	"fmt"
	"os/exec"
	"strconv"
	"strings"
)

// State is one branch's record. A counter is nil when its stored value is legacy free-form text, which Legacy then carries verbatim.
type State struct {
	Branch      string            `json:"branch"`
	Store       string            `json:"store"`
	Ladder      string            `json:"ladder"`
	Attempts    *int              `json:"attempts"`
	Escalations *int              `json:"escalations"`
	Reason      string            `json:"reason"`
	Legacy      map[string]string `json:"legacy,omitempty"`
}

// Branch addresses the state of the branch checked out in a repository directory.
type Branch struct {
	Dir, Name, Store string
}

func Open(dir string) (*Branch, error) {
	name, err := git(dir, "symbolic-ref", "--short", "HEAD")
	if err != nil {
		return nil, fmt.Errorf("not on a branch: %w", err)
	}
	store := "harness"
	if worktrunkLists(dir, name) {
		store = "worktrunk"
	}
	return &Branch{Dir: dir, Name: name, Store: store}, nil
}

// worktrunkLists reports whether `wt list` shows the branch. The schema is pinned on the call because a user config may pin another one. A missing `wt` or output that does not parse means Worktrunk does not manage it.
func worktrunkLists(dir, name string) bool {
	cmd := exec.Command("wt", "list", "--format=json", "--config-set", "list.json-schema=2")
	cmd.Dir = dir
	out, err := cmd.Output()
	if err != nil {
		return false
	}
	var listing struct {
		Items []struct {
			Branch string `json:"branch"`
		} `json:"items"`
	}
	if json.Unmarshal(out, &listing) != nil {
		return false
	}
	for _, item := range listing.Items {
		if item.Branch == name {
			return true
		}
	}
	return false
}

func key(store, branch, name string) string {
	if store == "worktrunk" {
		return "worktrunk.state." + branch + ".vars." + name
	}
	return "harness." + branch + "." + name
}

func (b *Branch) other() string {
	if b.Store == "worktrunk" {
		return "harness"
	}
	return "worktrunk"
}

// read finds a key in this branch's store, then in the other one, so state written before `wt` detection flipped is still found. Every write removes the other store's copy, so at most one exists.
func (b *Branch) read(name string) (raw string, found bool, err error) {
	for _, store := range []string{b.Store, b.other()} {
		if raw, found, err = get(b.Dir, key(store, b.Name, name)); err != nil || found {
			return raw, found, err
		}
	}
	return "", false, nil
}

// write stores a key in this branch's store and removes the other store's copy.
func (b *Branch) write(name, value string) error {
	if _, err := git(b.Dir, "config", "--local", key(b.Store, b.Name, name), value); err != nil {
		return err
	}
	// git config exits 5 when there is no such key to unset.
	if _, err := git(b.Dir, "config", "--local", "--unset", key(b.other(), b.Name, name)); err != nil && exitCode(err) != 5 {
		return err
	}
	return nil
}

// counter reads a counter: absent is 0, a canonical non-negative integer is itself, and anything else is legacy.
func (b *Branch) counter(name string) (n int, legacy *string, err error) {
	raw, found, err := b.read(name)
	if err != nil || !found {
		return 0, nil, err
	}
	n, convErr := strconv.Atoi(raw)
	if convErr != nil || n < 0 || strconv.Itoa(n) != raw {
		return 0, &raw, nil
	}
	return n, nil, nil
}

func (b *Branch) Get() (State, error) {
	s := State{Branch: b.Name, Store: b.Store}
	var err error
	if s.Ladder, _, err = b.read("ladder"); err != nil {
		return s, err
	}
	if s.Reason, _, err = b.read("reason"); err != nil {
		return s, err
	}
	for _, c := range []struct {
		name  string
		field **int
	}{{"attempts", &s.Attempts}, {"escalations", &s.Escalations}} {
		n, legacy, err := b.counter(c.name)
		if err != nil {
			return s, err
		}
		if legacy != nil {
			if s.Legacy == nil {
				s.Legacy = map[string]string{}
			}
			s.Legacy[c.name] = *legacy
			continue
		}
		*c.field = &n
	}
	return s, nil
}

// Incr adds one to the attempts or escalations counter. A legacy value counts as zero, and replaced then carries the text it overwrote.
func (b *Branch) Incr(name string) (next int, replaced *string, err error) {
	// ponytail: read-then-write without a lock assumes one writer per branch; add a lock file under .git if parallel roles ever share a branch's counters.
	n, replaced, err := b.counter(name)
	if err != nil {
		return 0, nil, err
	}
	return n + 1, replaced, b.write(name, strconv.Itoa(n+1))
}

// Escalate records one rabbit-hole trip. The reason is written first, so a failed write never leaves a counted trip that a retry would count again.
func (b *Branch) Escalate(reason string) (next int, replaced *string, err error) {
	if strings.TrimSpace(reason) == "" {
		return 0, nil, errors.New("an escalation needs a non-empty reason")
	}
	if err = b.write("reason", reason); err != nil {
		return 0, nil, err
	}
	return b.Incr("escalations")
}

func (b *Branch) SetLadder(text string) error {
	return b.write("ladder", text)
}

// Prune removes the state of every branch in dir's repository that no longer has a local ref, and returns the git config sections it removed.
func Prune(dir string) ([]string, error) {
	out, err := git(dir, "config", "--local", "-z", "--get-regexp", `^(worktrunk\.state|harness)\.`)
	if exitCode(err) == 1 {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	var removed []string
	seen := map[string]bool{}
	for _, record := range strings.Split(out, "\x00") {
		k, _, _ := strings.Cut(record, "\n")
		branch, section := owner(k)
		if branch == "" || seen[section] {
			continue
		}
		seen[section] = true
		_, err := git(dir, "show-ref", "--verify", "--quiet", "refs/heads/"+branch)
		if err == nil {
			continue
		}
		if exitCode(err) != 1 {
			return removed, err
		}
		if _, err := git(dir, "config", "--local", "--remove-section", section); err != nil {
			return removed, err
		}
		removed = append(removed, section)
	}
	return removed, nil
}

// owner maps a state key to its branch and the config section holding that branch's state. Unscoped keys such as harness.attempts have no branch.
func owner(k string) (branch, section string) {
	if rest, ok := strings.CutPrefix(k, "worktrunk.state."); ok {
		if i := strings.LastIndex(rest, ".vars."); i > 0 {
			return rest[:i], "worktrunk.state." + rest[:i] + ".vars"
		}
		return "", ""
	}
	if rest, ok := strings.CutPrefix(k, "harness."); ok {
		if i := strings.LastIndex(rest, "."); i > 0 {
			return rest[:i], "harness." + rest[:i]
		}
	}
	return "", ""
}

// get reads one repository-local config key; a missing key is not an error.
func get(dir, k string) (string, bool, error) {
	value, err := git(dir, "config", "--local", "--get", k)
	if exitCode(err) == 1 {
		return "", false, nil
	}
	return value, err == nil, err
}

func exitCode(err error) int {
	var exit *exec.ExitError
	if errors.As(err, &exit) {
		return exit.ExitCode()
	}
	return -1
}

func git(dir string, args ...string) (string, error) {
	cmd := exec.Command("git", args...)
	cmd.Dir = dir
	var stderr strings.Builder
	cmd.Stderr = &stderr
	out, err := cmd.Output()
	if err != nil {
		if msg := strings.TrimSpace(stderr.String()); msg != "" {
			return "", fmt.Errorf("git %s: %s: %w", args[0], msg, err)
		}
		return "", err
	}
	return strings.TrimSuffix(string(out), "\n"), nil
}
