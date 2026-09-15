// Command reconcile-agent-lifecycle reconciles native GitHub issue
// dependencies and parent/sub-issue state.
//
// It is one standard-library file so `go run` works in a repository with no Go
// module. setup-harness copies it, and the harness copy and the deployed copy
// must stay byte-identical; reconcile_agent_lifecycle_test.go fails when they
// drift.
package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"sort"
	"strconv"
	"strings"
)

// issue is the subset of the GitHub issue payload the reconciler reads.
type issue struct {
	Number int       `json:"number"`
	State  string    `json:"state"`
	Labels labelList `json:"labels"`
}

// label is one entry of the API's label objects.
type label struct {
	Name string `json:"name"`
}

// labelList is an issue's labels. The REST API returns each as a label object;
// a label update carries bare names and never round-trips through this type.
type labelList []string

func (l *labelList) UnmarshalJSON(data []byte) error {
	var raw []label
	if err := json.Unmarshal(data, &raw); err != nil {
		return err
	}
	names := make(labelList, 0, len(raw))
	for _, item := range raw {
		names = append(names, item.Name)
	}
	*l = names
	return nil
}

// event is the subset of the issue timeline the parent enrollment check reads.
type event struct {
	Event string `json:"event"`
	Label label  `json:"label"`
}

// issueAPI is the reconciler's issue-API boundary. GitHubAPI backs it with gh
// in production and the tests back it with an in-memory fake.
type issueAPI interface {
	issue(number int) (issue, error)
	related(number int, relation string) ([]issue, error)
	events(number int) ([]event, error)
	blockerSatisfied(value issue) (bool, error)
	update(number int, changes map[string]any) error
}

// gitHubAPI backs issueAPI with the gh CLI, which supplies the runner's token.
type gitHubAPI struct {
	repository string
	binary     string
	merged     map[int]bool
}

func (g *gitHubAPI) gh(args ...string) ([]byte, error) {
	command := exec.Command(g.binary, args...)
	var stderr bytes.Buffer
	command.Stderr = &stderr
	out, err := command.Output()
	if err != nil {
		message := strings.TrimSpace(stderr.String())
		if message != "" {
			return nil, fmt.Errorf("gh %s: %w: %s", strings.Join(args, " "), err, message)
		}
		return nil, fmt.Errorf("gh %s: %w", strings.Join(args, " "), err)
	}
	return out, nil
}

func (g *gitHubAPI) get(path string, paginate bool) ([]byte, error) {
	args := []string{
		"api", "--method", "GET",
		"repos/" + g.repository + "/" + path,
		"-H", "X-GitHub-Api-Version: 2022-11-28",
	}
	if paginate {
		args = append(args, "--paginate", "--slurp", "-f", "per_page=100")
	}
	return g.gh(args...)
}

func (g *gitHubAPI) issue(number int) (issue, error) {
	out, err := g.get(fmt.Sprintf("issues/%d", number), false)
	if err != nil {
		return issue{}, err
	}
	var value issue
	if err := json.Unmarshal(out, &value); err != nil {
		return issue{}, err
	}
	return value, nil
}

func (g *gitHubAPI) related(number int, relation string) ([]issue, error) {
	if relation == "parent" {
		out, err := g.get(fmt.Sprintf("issues/%d/parent", number), false)
		if err != nil {
			if isNotFound(err) {
				return nil, nil
			}
			return nil, err
		}
		var value issue
		if err := json.Unmarshal(out, &value); err != nil {
			return nil, err
		}
		return []issue{value}, nil
	}
	paths := map[string]string{
		"blocked_by": fmt.Sprintf("issues/%d/dependencies/blocked_by", number),
		"blocking":   fmt.Sprintf("issues/%d/dependencies/blocking", number),
		"sub_issues": fmt.Sprintf("issues/%d/sub_issues", number),
	}
	return g.getIssues(paths[relation])
}

// getIssues flattens a paginated issue list; --slurp returns an array of pages.
func (g *gitHubAPI) getIssues(path string) ([]issue, error) {
	out, err := g.get(path, true)
	if err != nil {
		return nil, err
	}
	var pages [][]issue
	if err := json.Unmarshal(out, &pages); err != nil {
		return nil, err
	}
	var result []issue
	for _, page := range pages {
		result = append(result, page...)
	}
	return result, nil
}

func (g *gitHubAPI) events(number int) ([]event, error) {
	out, err := g.get(fmt.Sprintf("issues/%d/events", number), true)
	if err != nil {
		return nil, err
	}
	var pages [][]event
	if err := json.Unmarshal(out, &pages); err != nil {
		return nil, err
	}
	var result []event
	for _, page := range pages {
		result = append(result, page...)
	}
	return result, nil
}

// blockerSatisfied reports whether a merged pull request closed the issue;
// a hand-closed issue does not satisfy the frontier.
func (g *gitHubAPI) blockerSatisfied(value issue) (bool, error) {
	if value.State != "closed" {
		return false, nil
	}
	number := value.Number
	if g.merged == nil {
		g.merged = map[int]bool{}
	}
	if satisfied, ok := g.merged[number]; ok {
		return satisfied, nil
	}
	out, err := g.gh("issue", "view", strconv.Itoa(number), "--repo", g.repository, "--json", "closedByPullRequestsReferences")
	if err != nil {
		return false, err
	}
	var view struct {
		ClosedByPullRequestsReferences []struct {
			URL string `json:"url"`
		} `json:"closedByPullRequestsReferences"`
	}
	if err := json.Unmarshal(out, &view); err != nil {
		return false, err
	}
	g.merged[number] = false
	for _, reference := range view.ClosedByPullRequestsReferences {
		out, err := g.gh("pr", "view", reference.URL, "--json", "state,mergedAt")
		if err != nil {
			return false, err
		}
		var state struct {
			State    string  `json:"state"`
			MergedAt *string `json:"mergedAt"`
		}
		if err := json.Unmarshal(out, &state); err != nil {
			return false, err
		}
		if state.State == "MERGED" || state.MergedAt != nil {
			g.merged[number] = true
			break
		}
	}
	return g.merged[number], nil
}

func (g *gitHubAPI) update(number int, changes map[string]any) error {
	body, err := json.Marshal(changes)
	if err != nil {
		return err
	}
	command := exec.Command(
		g.binary,
		"api", "--method", "PATCH",
		fmt.Sprintf("repos/%s/issues/%d", g.repository, number),
		"-H", "X-GitHub-Api-Version: 2022-11-28",
		"--input", "-",
	)
	command.Stdin = bytes.NewReader(body)
	command.Stdout = os.Stdout
	command.Stderr = os.Stderr
	return command.Run()
}

func isNotFound(err error) bool {
	if err == nil {
		return false
	}
	message := err.Error()
	return strings.Contains(message, "HTTP 404") || strings.Contains(message, "Not Found")
}

// labelSet is a set of label names.
type labelSet map[string]bool

func labelNames(value issue) labelSet {
	names := labelSet{}
	for _, name := range value.Labels {
		names[name] = true
	}
	return names
}

func (s labelSet) sorted() []string {
	names := make([]string, 0, len(s))
	for name := range s {
		names = append(names, name)
	}
	sort.Strings(names)
	return names
}

func (s labelSet) minus(other labelSet) labelSet {
	result := labelSet{}
	for name := range s {
		if !other[name] {
			result[name] = true
		}
	}
	return result
}

func (s labelSet) intersects(other labelSet) bool {
	for name := range s {
		if other[name] {
			return true
		}
	}
	return false
}

func (s labelSet) equals(other labelSet) bool {
	if len(s) != len(other) {
		return false
	}
	for name := range s {
		if !other[name] {
			return false
		}
	}
	return true
}

func lifecycleSet(labels map[string]string) labelSet {
	set := labelSet{}
	for _, value := range labels {
		set[value] = true
	}
	return set
}

func defaultLabels() map[string]string {
	return map[string]string{
		"blocked":         "blocked",
		"ready_for_agent": "ready-for-agent",
		"in_progress":     "in-progress",
		"ready_for_human": "ready-for-human",
	}
}

func reconcileFrontier(api issueAPI, number int, labels map[string]string, resetActive bool) error {
	value, err := api.issue(number)
	if err != nil {
		return err
	}
	if value.State != "open" {
		return nil
	}

	current := labelNames(value)
	active := labelSet{labels["in_progress"]: true, labels["ready_for_human"]: true}
	released := labelSet{labels["blocked"]: true, labels["ready_for_agent"]: true}
	if !current.intersects(lifecycleSet(labels)) {
		return nil
	}
	desired := current.minus(released)
	blockers, err := api.related(number, "blocked_by")
	if err != nil {
		return err
	}
	unsatisfied := false
	for _, blocker := range blockers {
		satisfied, err := api.blockerSatisfied(blocker)
		if err != nil {
			return err
		}
		if !satisfied {
			unsatisfied = true
			break
		}
	}
	switch {
	case unsatisfied:
		desired = desired.minus(active)
		desired[labels["blocked"]] = true
	case resetActive || !current.intersects(active) || current.intersects(released):
		desired = desired.minus(active)
		desired[labels["ready_for_agent"]] = true
	}
	if !desired.equals(current) {
		return api.update(number, map[string]any{"labels": desired.sorted()})
	}
	return nil
}

func reconcileParent(api issueAPI, number int, labels map[string]string) (bool, error) {
	parent, err := api.issue(number)
	if err != nil {
		return false, err
	}
	children, err := api.related(number, "sub_issues")
	if err != nil {
		return false, err
	}
	if len(children) == 0 {
		return false, nil
	}
	lifecycle := lifecycleSet(labels)
	current := labelNames(parent)
	// Label history preserves enrollment after completed parents shed status labels.
	if !current.intersects(lifecycle) {
		events, err := api.events(number)
		if err != nil {
			return false, err
		}
		enrolled := false
		for _, value := range events {
			if value.Event == "labeled" && lifecycle[value.Label.Name] {
				enrolled = true
				break
			}
		}
		if !enrolled {
			return false, nil
		}
	}

	target := "open"
	allSatisfied := true
	for _, child := range children {
		satisfied, err := api.blockerSatisfied(child)
		if err != nil {
			return false, err
		}
		if !satisfied {
			allSatisfied = false
			break
		}
	}
	if allSatisfied {
		target = "closed"
	}

	desired := current.minus(lifecycle)
	changes := map[string]any{}
	if parent.State != target {
		changes["state"] = target
	}
	if target == "open" {
		if len(changes) == 0 && current.intersects(lifecycle) {
			return false, nil
		}
		desired[labels["in_progress"]] = true
	}
	if !desired.equals(current) {
		changes["labels"] = desired.sorted()
	}
	if len(changes) == 0 {
		return false, nil
	}
	if err := api.update(number, changes); err != nil {
		return false, err
	}
	return true, nil
}

func reconcile(api issueAPI, eventNumber int, labels map[string]string, eventAction string) error {
	type item struct {
		number      int
		resetActive bool
	}
	queue := []item{{eventNumber, eventAction == "reopened"}}
	seen := map[int]bool{}
	for len(queue) > 0 {
		current := queue[0]
		queue = queue[1:]
		if seen[current.number] {
			continue
		}
		seen[current.number] = true

		if err := reconcileFrontier(api, current.number, labels, current.resetActive); err != nil {
			return err
		}
		dependents, err := api.related(current.number, "blocking")
		if err != nil {
			return err
		}
		for _, dependent := range dependents {
			if err := reconcileFrontier(api, dependent.Number, labels, false); err != nil {
				return err
			}
		}
		changed, err := reconcileParent(api, current.number, labels)
		if err != nil {
			return err
		}
		if changed {
			if err := reconcileFrontier(api, current.number, labels, false); err != nil {
				return err
			}
		}
		parents, err := api.related(current.number, "parent")
		if err != nil {
			return err
		}
		if len(parents) > 0 {
			changed, err := reconcileParent(api, parents[0].Number, labels)
			if err != nil {
				return err
			}
			if changed {
				queue = append(queue, item{parents[0].Number, false})
			}
		}
	}
	return nil
}

func configuredLabels(path string) (map[string]string, error) {
	labels := defaultLabels()
	raw, err := os.ReadFile(path)
	if err != nil {
		if os.IsNotExist(err) {
			return labels, nil
		}
		return nil, err
	}
	var config struct {
		Labels map[string]string `json:"labels"`
	}
	if err := json.Unmarshal(raw, &config); err != nil {
		return nil, err
	}
	for key, value := range config.Labels {
		labels[key] = value
	}
	return labels, nil
}

func run() error {
	raw, err := os.ReadFile(os.Getenv("GITHUB_EVENT_PATH"))
	if err != nil {
		return err
	}
	var payload struct {
		Issue struct {
			Number int `json:"number"`
		} `json:"issue"`
		Action string `json:"action"`
	}
	if err := json.Unmarshal(raw, &payload); err != nil {
		return err
	}
	labels, err := configuredLabels("docs/agents/harness.json")
	if err != nil {
		return err
	}
	repository := os.Getenv("GITHUB_REPOSITORY")
	if repository == "" {
		return fmt.Errorf("GITHUB_REPOSITORY is not set")
	}
	api := &gitHubAPI{repository: repository, binary: "gh"}
	return reconcile(api, payload.Issue.Number, labels, payload.Action)
}

func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, "reconcile-agent-lifecycle:", err)
		os.Exit(1)
	}
}
