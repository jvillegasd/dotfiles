package main

// Regression checks for frontier promotion in reconcile-agent-lifecycle.
//
// Planning-only tickets carry no lifecycle label and must stay off the ready
// frontier until explicit promotion labels them. Each case mirrors a real
// reconcile path with an in-memory fake of the issue API.

import (
	"bytes"
	"encoding/json"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"testing"
)

func newIssue(number int, state string, labels ...string) *issue {
	return &issue{Number: number, State: state, Labels: labelList(labels)}
}

type fakeAPI struct {
	issues    map[int]*issue
	satisfied map[int]bool
	blockedBy map[int][]int
	blocking  map[int][]int
	parents   map[int][]int
	updates   []updateCall
	history   map[int][]event
}

type updateCall struct {
	Number int
	Labels []string
	State  string
}

func (u updateCall) String() string {
	parts := []string{strconv.Itoa(u.Number)}
	if u.State != "" {
		parts = append(parts, "state="+u.State)
	}
	if u.Labels != nil {
		parts = append(parts, "labels="+strings.Join(u.Labels, ","))
	}
	return strings.Join(parts, " ")
}

func newFake(issues map[int]*issue, satisfied []int, blockedBy, blocking, parents map[int][]int) *fakeAPI {
	f := &fakeAPI{
		issues:    issues,
		satisfied: map[int]bool{},
		blockedBy: blockedBy,
		blocking:  blocking,
		parents:   parents,
		history:   map[int][]event{},
	}
	for _, number := range satisfied {
		f.satisfied[number] = true
	}
	for number, value := range issues {
		for _, name := range value.Labels {
			f.history[number] = append(f.history[number], event{Event: "labeled", Label: label{Name: name}})
		}
	}
	return f
}

func (f *fakeAPI) issue(number int) (issue, error) {
	return *f.issues[number], nil
}

func (f *fakeAPI) related(number int, relation string) ([]issue, error) {
	switch relation {
	case "sub_issues":
		var children []issue
		for n, parents := range f.parents {
			for _, parent := range parents {
				if parent == number {
					children = append(children, *f.issues[n])
				}
			}
		}
		return children, nil
	case "blocked_by":
		return f.byIDs(f.blockedBy[number]), nil
	case "blocking":
		return f.byIDs(f.blocking[number]), nil
	case "parent":
		return f.byIDs(f.parents[number]), nil
	}
	return nil, nil
}

func (f *fakeAPI) byIDs(numbers []int) []issue {
	result := make([]issue, 0, len(numbers))
	for _, number := range numbers {
		result = append(result, *f.issues[number])
	}
	return result
}

func (f *fakeAPI) events(number int) ([]event, error) {
	return f.history[number], nil
}

func (f *fakeAPI) blockerSatisfied(blocker issue) (bool, error) {
	return blocker.State == "closed" && f.satisfied[blocker.Number], nil
}

func (f *fakeAPI) update(number int, changes map[string]any) error {
	call := updateCall{Number: number}
	if raw, ok := changes["labels"].([]string); ok {
		call.Labels = raw
	}
	if state, ok := changes["state"].(string); ok {
		call.State = state
	}
	f.updates = append(f.updates, call)

	value := f.issues[number]
	before := labelNames(*value)
	if raw, ok := changes["labels"].([]string); ok {
		value.Labels = labelList(raw)
	}
	if state, ok := changes["state"].(string); ok {
		value.State = state
	}
	after := labelNames(*value)
	for name := range after {
		if !before[name] {
			f.history[number] = append(f.history[number], event{Event: "labeled", Label: label{Name: name}})
		}
	}
	for name := range before {
		if !after[name] {
			f.history[number] = append(f.history[number], event{Event: "unlabeled", Label: label{Name: name}})
		}
	}
	return nil
}

func assertUpdates(t *testing.T, f *fakeAPI, want ...string) {
	t.Helper()
	if len(f.updates) != len(want) {
		t.Fatalf("updates = %v, want %v", f.updates, want)
	}
	for i, call := range f.updates {
		if got := call.String(); got != want[i] {
			t.Fatalf("update[%d] = %q, want %q (all: %v)", i, got, want[i], f.updates)
		}
	}
}

func assertLabels(t *testing.T, f *fakeAPI, number int, want ...string) {
	t.Helper()
	got := labelNames(*f.issues[number])
	expected := labelSet{}
	for _, name := range want {
		expected[name] = true
	}
	if !got.equals(expected) {
		t.Fatalf("issue %d labels = %v, want %v", number, got.sorted(), expected.sorted())
	}
}

func assertNoNewUpdates(t *testing.T, f *fakeAPI, run func() error) {
	t.Helper()
	before := len(f.updates)
	if err := run(); err != nil {
		t.Fatal(err)
	}
	if len(f.updates) != before {
		t.Fatalf("unexpected updates: %v", f.updates[before:])
	}
}

// writeScenarioArtifact feeds the lifecycle scenario its labels.json. It is a
// no-op outside the scenario runner.
func writeScenarioArtifact(t *testing.T, f *fakeAPI) {
	t.Helper()
	repo := os.Getenv("SCENARIO_REPO")
	if repo == "" {
		return
	}
	transitions := make([]map[string]any, 0, len(f.updates))
	for _, call := range f.updates {
		entry := map[string]any{"number": call.Number}
		if call.Labels != nil {
			entry["labels"] = call.Labels
		}
		if call.State != "" {
			entry["state"] = call.State
		}
		transitions = append(transitions, entry)
	}
	dir := filepath.Join(repo, "artifacts")
	if err := os.MkdirAll(dir, 0o755); err != nil {
		t.Fatal(err)
	}
	data, err := json.MarshalIndent(transitions, "", "  ")
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(dir, "labels.json"), append(data, '\n'), 0o644); err != nil {
		t.Fatal(err)
	}
}

func TestPlanningOnlyTicketNotPromoted(t *testing.T) {
	f := newFake(map[int]*issue{1: newIssue(1, "open")}, nil, nil, nil, nil)
	if err := reconcileFrontier(f, 1, defaultLabels(), false); err != nil {
		t.Fatal(err)
	}
	assertUpdates(t, f)
}

func TestPlanningOnlyTicketNotPromotedOnReopen(t *testing.T) {
	f := newFake(map[int]*issue{1: newIssue(1, "open")}, nil, nil, nil, nil)
	if err := reconcileFrontier(f, 1, defaultLabels(), true); err != nil {
		t.Fatal(err)
	}
	assertUpdates(t, f)
}

func TestPlanningOnlyDependentNotPromotedWhenBlockerCloses(t *testing.T) {
	f := newFake(
		map[int]*issue{1: newIssue(1, "closed"), 2: newIssue(2, "open")},
		[]int{1}, map[int][]int{2: {1}}, map[int][]int{1: {2}}, nil,
	)
	if err := reconcile(f, 1, defaultLabels(), ""); err != nil {
		t.Fatal(err)
	}
	assertUpdates(t, f)
}

func TestBlockedTicketBecomesReadyWhenBlockerCloses(t *testing.T) {
	labels := defaultLabels()
	f := newFake(
		map[int]*issue{
			1: newIssue(1, "closed"),
			2: newIssue(2, "open", labels["blocked"]),
		},
		[]int{1}, map[int][]int{2: {1}}, map[int][]int{1: {2}}, nil,
	)
	if err := reconcile(f, 1, labels, ""); err != nil {
		t.Fatal(err)
	}
	assertUpdates(t, f, "2 labels="+labels["ready_for_agent"])
	writeScenarioArtifact(t, f)
}

func TestReadyTicketBecomesBlockedWhileBlockerOpen(t *testing.T) {
	labels := defaultLabels()
	f := newFake(
		map[int]*issue{
			1: newIssue(1, "open", labels["ready_for_agent"]),
			2: newIssue(2, "open"),
		},
		nil, map[int][]int{1: {2}}, nil, nil,
	)
	if err := reconcileFrontier(f, 1, labels, false); err != nil {
		t.Fatal(err)
	}
	assertUpdates(t, f, "1 labels="+labels["blocked"])
}

func TestReopenedInProgressTicketResetsToReady(t *testing.T) {
	labels := defaultLabels()
	f := newFake(map[int]*issue{1: newIssue(1, "open", labels["in_progress"])}, nil, nil, nil, nil)
	if err := reconcileFrontier(f, 1, labels, true); err != nil {
		t.Fatal(err)
	}
	assertUpdates(t, f, "1 labels="+labels["ready_for_agent"])
}

func TestActiveTicketWithNoBlockersUntouched(t *testing.T) {
	labels := defaultLabels()
	f := newFake(map[int]*issue{1: newIssue(1, "open", labels["in_progress"])}, nil, nil, nil, nil)
	if err := reconcileFrontier(f, 1, labels, false); err != nil {
		t.Fatal(err)
	}
	assertUpdates(t, f)
}

func TestReleasedPairKeepsReadyOverReadyForHuman(t *testing.T) {
	labels := defaultLabels()
	f := newFake(
		map[int]*issue{1: newIssue(1, "open", labels["ready_for_agent"], labels["ready_for_human"])},
		nil, nil, nil, nil,
	)
	if err := reconcileFrontier(f, 1, labels, false); err != nil {
		t.Fatal(err)
	}
	assertUpdates(t, f, "1 labels="+labels["ready_for_agent"])
}

func TestReleasedPairKeepsReadyOverInProgress(t *testing.T) {
	labels := defaultLabels()
	f := newFake(
		map[int]*issue{1: newIssue(1, "open", labels["ready_for_agent"], labels["in_progress"])},
		nil, nil, nil, nil,
	)
	if err := reconcileFrontier(f, 1, labels, false); err != nil {
		t.Fatal(err)
	}
	assertUpdates(t, f, "1 labels="+labels["ready_for_agent"])
}

func TestReleasedPairKeepsBlockedOverReadyForHuman(t *testing.T) {
	labels := defaultLabels()
	f := newFake(
		map[int]*issue{
			1: newIssue(1, "open", labels["blocked"], labels["ready_for_human"]),
			2: newIssue(2, "open"),
		},
		nil, map[int][]int{1: {2}}, nil, nil,
	)
	if err := reconcileFrontier(f, 1, labels, false); err != nil {
		t.Fatal(err)
	}
	assertUpdates(t, f, "1 labels="+labels["blocked"])
}

func TestReleasedPairKeepsBlockedOverInProgress(t *testing.T) {
	labels := defaultLabels()
	f := newFake(
		map[int]*issue{
			1: newIssue(1, "open", labels["blocked"], labels["in_progress"]),
			2: newIssue(2, "open"),
		},
		nil, map[int][]int{1: {2}}, nil, nil,
	)
	if err := reconcileFrontier(f, 1, labels, false); err != nil {
		t.Fatal(err)
	}
	assertUpdates(t, f, "1 labels="+labels["blocked"])
}

func TestCompletedParentLosesLifecycleLabels(t *testing.T) {
	f := newFake(
		map[int]*issue{
			1: newIssue(1, "closed"),
			2: newIssue(2, "closed", "in-progress", "feature"),
		},
		[]int{1}, nil, nil, map[int][]int{1: {2}},
	)
	if err := reconcile(f, 1, defaultLabels(), "closed"); err != nil {
		t.Fatal(err)
	}
	if f.issues[2].State != "closed" {
		t.Fatalf("issue 2 state = %q, want closed", f.issues[2].State)
	}
	assertLabels(t, f, 2, "feature")
}

func TestAlreadyClosedParentRepairsLabelsOnce(t *testing.T) {
	labels := map[string]string{
		"blocked":         "waiting",
		"ready_for_agent": "queued",
		"in_progress":     "working",
		"ready_for_human": "review",
	}
	f := newFake(
		map[int]*issue{
			1: newIssue(1, "closed"),
			2: newIssue(2, "closed", "waiting", "queued", "working", "review", "feature"),
		},
		[]int{1}, nil, nil, map[int][]int{1: {2}},
	)
	if err := reconcile(f, 2, labels, "closed"); err != nil {
		t.Fatal(err)
	}
	if f.issues[2].State != "closed" {
		t.Fatalf("issue 2 state = %q, want closed", f.issues[2].State)
	}
	assertLabels(t, f, 2, "feature")
	assertNoNewUpdates(t, f, func() error { return reconcile(f, 2, labels, "closed") })
}

func TestCleanedParentReopensWhenChildReopens(t *testing.T) {
	labels := []map[string]string{
		defaultLabels(),
		{
			"blocked":         "waiting",
			"ready_for_agent": "queued",
			"in_progress":     "working",
			"ready_for_human": "review",
		},
	}
	for _, label := range labels {
		f := newFake(
			map[int]*issue{
				1: newIssue(1, "closed", label["ready_for_human"]),
				2: newIssue(2, "open", label["in_progress"], "feature"),
			},
			[]int{1}, nil, nil, map[int][]int{1: {2}},
		)
		if err := reconcile(f, 1, label, "closed"); err != nil {
			t.Fatal(err)
		}
		assertLabels(t, f, 2, "feature")

		if err := f.update(1, map[string]any{"state": "open"}); err != nil {
			t.Fatal(err)
		}
		delete(f.satisfied, 1)
		if err := reconcile(f, 1, label, "reopened"); err != nil {
			t.Fatal(err)
		}
		if f.issues[2].State != "open" {
			t.Fatalf("issue 2 state = %q, want open", f.issues[2].State)
		}
		assertLabels(t, f, 2, label["in_progress"], "feature")
		assertNoNewUpdates(t, f, func() error { return reconcile(f, 1, label, "reopened") })
	}
}

func TestAlreadyReopenedParentRecoversLifecycleLabel(t *testing.T) {
	for _, eventNumber := range []int{1, 2} {
		f := newFake(
			map[int]*issue{
				1: newIssue(1, "closed", "ready-for-human"),
				2: newIssue(2, "open", "in-progress", "feature"),
			},
			[]int{1}, nil, nil, map[int][]int{1: {2}},
		)
		if err := reconcile(f, 1, defaultLabels(), "closed"); err != nil {
			t.Fatal(err)
		}
		if err := f.update(2, map[string]any{"state": "open"}); err != nil {
			t.Fatal(err)
		}
		if err := f.update(1, map[string]any{"state": "open"}); err != nil {
			t.Fatal(err)
		}
		if err := reconcile(f, eventNumber, defaultLabels(), "reopened"); err != nil {
			t.Fatal(err)
		}
		if f.issues[2].State != "open" {
			t.Fatalf("event %d: issue 2 state = %q, want open", eventNumber, f.issues[2].State)
		}
		assertLabels(t, f, 2, "in-progress", "feature")
		assertNoNewUpdates(t, f, func() error { return reconcile(f, 1, defaultLabels(), "") })
	}
}

func TestReopenedParentStillRespectsItsBlockers(t *testing.T) {
	f := newFake(
		map[int]*issue{
			1: newIssue(1, "closed"),
			2: newIssue(2, "open", "in-progress", "feature"),
			3: newIssue(3, "open"),
		},
		[]int{1}, map[int][]int{2: {3}}, nil, map[int][]int{1: {2}},
	)
	if err := reconcile(f, 1, defaultLabels(), "closed"); err != nil {
		t.Fatal(err)
	}
	if err := f.update(2, map[string]any{"state": "open"}); err != nil {
		t.Fatal(err)
	}
	if err := f.update(1, map[string]any{"state": "open"}); err != nil {
		t.Fatal(err)
	}
	if err := reconcile(f, 2, defaultLabels(), "reopened"); err != nil {
		t.Fatal(err)
	}
	if f.issues[2].State != "open" {
		t.Fatalf("issue 2 state = %q, want open", f.issues[2].State)
	}
	assertLabels(t, f, 2, "blocked", "feature")
}

func TestPlanningOnlyParentStaysUnmanaged(t *testing.T) {
	for _, state := range []string{"open", "closed"} {
		f := newFake(
			map[int]*issue{
				1: newIssue(1, "closed", "ready-for-human"),
				2: newIssue(2, state, "feature"),
			},
			[]int{1}, nil, nil, map[int][]int{1: {2}},
		)
		if err := reconcile(f, 1, defaultLabels(), "closed"); err != nil {
			t.Fatal(err)
		}
		assertUpdates(t, f)

		if err := f.update(1, map[string]any{"state": "open"}); err != nil {
			t.Fatal(err)
		}
		assertNoNewUpdates(t, f, func() error { return reconcile(f, 1, defaultLabels(), "") })
		if f.issues[2].State != state {
			t.Fatalf("issue 2 state = %q, want %q", f.issues[2].State, state)
		}
		assertLabels(t, f, 2, "feature")
	}
}

func TestParentWaitsForEveryChildMerge(t *testing.T) {
	f := newFake(
		map[int]*issue{
			1: newIssue(1, "closed"),
			2: newIssue(2, "open", "in-progress", "feature"),
			3: newIssue(3, "closed"),
		},
		[]int{1}, nil, nil, map[int][]int{1: {2}, 3: {2}},
	)
	if err := reconcile(f, 1, defaultLabels(), "closed"); err != nil {
		t.Fatal(err)
	}
	assertUpdates(t, f)

	f.satisfied[3] = true
	if err := reconcile(f, 3, defaultLabels(), "closed"); err != nil {
		t.Fatal(err)
	}
	if f.issues[2].State != "closed" {
		t.Fatalf("issue 2 state = %q, want closed", f.issues[2].State)
	}
	assertLabels(t, f, 2, "feature")
}

func TestClosedStandaloneTicketKeepsLabels(t *testing.T) {
	f := newFake(
		map[int]*issue{1: newIssue(1, "closed", "ready-for-human", "feature")},
		nil, nil, nil, nil,
	)
	if err := reconcile(f, 1, defaultLabels(), "closed"); err != nil {
		t.Fatal(err)
	}
	assertUpdates(t, f)
}

func TestDeployedCopyMatchesHarnessCopy(t *testing.T) {
	harnessCopy, err := os.ReadFile("reconcile-agent-lifecycle.go")
	if err != nil {
		t.Fatal(err)
	}
	deployed := filepath.Join("..", "..", "..", "..", ".github", "scripts", "reconcile-agent-lifecycle.go")
	deployedCopy, err := os.ReadFile(deployed)
	if err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(harnessCopy, deployedCopy) {
		t.Fatalf("harness and deployed reconciler copies differ: %s", deployed)
	}
}

// TestGoRunWithoutModule proves the file is standard-library only: it compiles
// and runs through `go run` in a directory with no Go module.
func TestGoRunWithoutModule(t *testing.T) {
	source, err := os.ReadFile("reconcile-agent-lifecycle.go")
	if err != nil {
		t.Fatal(err)
	}
	dir := t.TempDir()
	if err := os.WriteFile(filepath.Join(dir, "reconcile-agent-lifecycle.go"), source, 0o644); err != nil {
		t.Fatal(err)
	}
	eventPath := filepath.Join(dir, "event.json")
	if err := os.WriteFile(eventPath, []byte(`{"issue":{"number":1},"action":"closed"}`), 0o644); err != nil {
		t.Fatal(err)
	}
	gh := filepath.Join(dir, "gh")
	script := "#!/bin/sh\ncase \"$*\" in\n  *sub_issues*|*blocking*|*blocked_by*|*events*) printf '[]\\n' ;;\n  *) printf '{}\\n' ;;\nesac\n"
	if err := os.WriteFile(gh, []byte(script), 0o755); err != nil {
		t.Fatal(err)
	}

	command := exec.Command("go", "run", "reconcile-agent-lifecycle.go")
	command.Dir = dir
	command.Env = append(os.Environ(),
		"GITHUB_REPOSITORY=owner/repo",
		"GITHUB_EVENT_PATH="+eventPath,
		"PATH="+dir+string(os.PathListSeparator)+os.Getenv("PATH"),
	)
	if out, err := command.CombinedOutput(); err != nil {
		t.Fatalf("go run failed with no module: %v\n%s", err, out)
	}
}
