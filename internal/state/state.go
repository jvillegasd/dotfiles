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

// worktrunkLists reports whether `wt list` shows the branch. A missing `wt` or output that does not parse means Worktrunk does not manage it.
func worktrunkLists(dir, name string) bool {
	cmd := exec.Command("wt", "list", "--format=json")
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

func (b *Branch) key(name string) string {
	if b.Store == "worktrunk" {
		return "worktrunk.state." + b.Name + ".vars." + name
	}
	return "harness." + b.Name + "." + name
}

func (b *Branch) get(name string) (string, bool, error) {
	value, err := git(b.Dir, "config", "--get", b.key(name))
	var exit *exec.ExitError
	if errors.As(err, &exit) && exit.ExitCode() == 1 {
		return "", false, nil
	}
	return value, err == nil, err
}

func (b *Branch) Get() (State, error) {
	s := State{Branch: b.Name, Store: b.Store}
	var err error
	if s.Ladder, _, err = b.get("ladder"); err != nil {
		return s, err
	}
	if s.Reason, _, err = b.get("reason"); err != nil {
		return s, err
	}
	for name, field := range map[string]**int{"attempts": &s.Attempts, "escalations": &s.Escalations} {
		raw, found, err := b.get(name)
		if err != nil {
			return s, err
		}
		n, legacy := parseCounter(raw, found)
		if legacy {
			if s.Legacy == nil {
				s.Legacy = map[string]string{}
			}
			s.Legacy[name] = raw
			continue
		}
		*field = &n
	}
	return s, nil
}

// Incr adds one to a counter. A legacy value counts as zero, and replaced then carries the text it overwrote.
func (b *Branch) Incr(name string) (next int, replaced *string, err error) {
	if name != "attempts" && name != "escalations" {
		return 0, nil, fmt.Errorf("unknown counter %q; want attempts or escalations", name)
	}
	raw, found, err := b.get(name)
	if err != nil {
		return 0, nil, err
	}
	n, legacy := parseCounter(raw, found)
	if legacy {
		replaced = &raw
	}
	_, err = git(b.Dir, "config", b.key(name), strconv.Itoa(n+1))
	return n + 1, replaced, err
}

// Escalate records one rabbit-hole trip: it increments escalations and replaces reason with the latest trip's text.
func (b *Branch) Escalate(reason string) (next int, replaced *string, err error) {
	if strings.TrimSpace(reason) == "" {
		return 0, nil, errors.New("an escalation needs a non-empty reason")
	}
	if next, replaced, err = b.Incr("escalations"); err != nil {
		return next, replaced, err
	}
	_, err = git(b.Dir, "config", b.key("reason"), reason)
	return next, replaced, err
}

// Prune removes the state of every branch in dir's repository that no longer has a local ref, and returns the git config sections it removed.
func Prune(dir string) ([]string, error) {
	out, err := git(dir, "config", "-z", "--get-regexp", `^(worktrunk\.state|harness)\.`)
	var exit *exec.ExitError
	if errors.As(err, &exit) && exit.ExitCode() == 1 {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	var removed []string
	seen := map[string]bool{}
	for _, record := range strings.Split(out, "\x00") {
		key, _, _ := strings.Cut(record, "\n")
		branch, section := owner(key)
		if branch == "" || seen[section] {
			continue
		}
		seen[section] = true
		if _, err := git(dir, "show-ref", "--verify", "--quiet", "refs/heads/"+branch); err == nil {
			continue
		}
		if _, err := git(dir, "config", "--remove-section", section); err != nil {
			return removed, err
		}
		removed = append(removed, section)
	}
	return removed, nil
}

// owner maps a state key to its branch and the config section holding that branch's state. Unscoped legacy keys such as harness.attempts have no branch.
func owner(key string) (branch, section string) {
	if rest, ok := strings.CutPrefix(key, "worktrunk.state."); ok {
		if i := strings.LastIndex(rest, ".vars."); i > 0 {
			return rest[:i], "worktrunk.state." + rest[:i] + ".vars"
		}
		return "", ""
	}
	if rest, ok := strings.CutPrefix(key, "harness."); ok {
		if i := strings.LastIndex(rest, "."); i > 0 {
			return rest[:i], "harness." + rest[:i]
		}
	}
	return "", ""
}

func (b *Branch) SetLadder(text string) error {
	_, err := git(b.Dir, "config", b.key("ladder"), text)
	return err
}

// parseCounter reads a stored counter: absent is 0, a non-negative integer is itself, anything else is legacy.
func parseCounter(raw string, found bool) (int, bool) {
	if !found {
		return 0, false
	}
	n, err := strconv.Atoi(raw)
	if err != nil || n < 0 {
		return 0, true
	}
	return n, false
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
