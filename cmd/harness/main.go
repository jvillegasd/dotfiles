// Command harness is the single entry point for operating the harness.
package main

import (
	"encoding/json"
	"fmt"
	"io"
	"os"
	"strings"

	"github.com/jvillegasd/dotfiles/internal/install"
	"github.com/jvillegasd/dotfiles/internal/state"
)

func main() {
	os.Exit(run(os.Args[1:], os.Stdout, os.Stderr))
}

const usage = `Usage: harness <command> [arguments]

Commands:
  bootstrap  Link the tracked configs, build harness into ~/.local/bin, and install the harness
  install    Install, reconcile, or remove the harness on this machine
  state      Read and write this branch's oracle ladder and rabbit-hole counters
`

const stateUsage = `Usage: harness state <operation>

Operations:
  ladder set <text>          Record the resolved oracle ladder
  incr attempts              Add one to attempts and print it
  escalate --reason <text>   Add one to escalations and record the trip's reason
  get [--json]               Print this branch's state
  prune                      Remove state for branches with no local ref

State lives in Worktrunk's per-branch vars when wt lists the branch, and in harness.<branch>.* git config keys otherwise.
`

func run(args []string, stdout, stderr io.Writer) int {
	if len(args) == 0 {
		fmt.Fprint(stderr, usage)
		return 2
	}
	switch args[0] {
	case "bootstrap":
		return install.Bootstrap(args[1:], stdout, stderr)
	case "install":
		return install.Command(args[1:], stdout, stderr)
	case "state":
		return runState(args[1:], stdout, stderr)
	case "-h", "--help", "help":
		fmt.Fprint(stdout, usage)
		return 0
	}
	fmt.Fprintf(stderr, "harness: unknown command %q; run harness --help\n", args[0])
	return 2
}

func runState(args []string, stdout, stderr io.Writer) int {
	fail := func(err error) int {
		fmt.Fprintf(stderr, "harness state: %v\n", err)
		return 1
	}
	misuse := func(msg string) int {
		fmt.Fprintf(stderr, "harness state: %s; run harness state --help\n", msg)
		return 2
	}
	if len(args) == 0 {
		fmt.Fprint(stderr, stateUsage)
		return 2
	}
	op, n := args[0], len(args)
	switch {
	case n == 1 && (op == "-h" || op == "--help" || op == "help"):
		fmt.Fprint(stdout, stateUsage)
		return 0
	case n == 1 && op == "prune":
		removed, err := state.Prune(".")
		for _, section := range removed {
			fmt.Fprintln(stdout, "removed", section)
		}
		if err != nil {
			return fail(err)
		}
		return 0
	case op == "escalate" && (n != 3 || args[1] != "--reason"):
		return misuse("escalate needs --reason <text>")
	case !(op == "ladder" && n >= 3 && args[1] == "set") &&
		!(op == "incr" && n == 2 && args[1] == "attempts") &&
		op != "escalate" &&
		!(op == "get" && (n == 1 || n == 2 && args[1] == "--json")):
		return misuse(fmt.Sprintf("unknown operation %q", strings.Join(args, " ")))
	}

	b, err := state.Open(".")
	if err != nil {
		return fail(err)
	}
	switch op {
	case "ladder":
		if err := b.SetLadder(strings.Join(args[2:], " ")); err != nil {
			return fail(err)
		}
	case "incr":
		next, replaced, err := b.Incr("attempts")
		return counted(next, "attempts", replaced, err, stdout, stderr, fail)
	case "escalate":
		next, replaced, err := b.Escalate(args[2])
		return counted(next, "escalations", replaced, err, stdout, stderr, fail)
	case "get":
		s, err := b.Get()
		if err != nil {
			return fail(err)
		}
		if n == 2 {
			out, _ := json.Marshal(s)
			fmt.Fprintln(stdout, string(out))
			break
		}
		fmt.Fprintf(stdout, "branch: %s (%s)\nladder: %s\nattempts: %s\nescalations: %s\nreason: %s\n",
			s.Branch, s.Store, s.Ladder, counter(s.Attempts, s.Legacy["attempts"]), counter(s.Escalations, s.Legacy["escalations"]), s.Reason)
	}
	return 0
}

// counted reports a counter write, naming any legacy text it replaced.
func counted(next int, name string, replaced *string, err error, stdout, stderr io.Writer, fail func(error) int) int {
	if err != nil {
		return fail(err)
	}
	if replaced != nil {
		fmt.Fprintf(stderr, "harness state: replaced legacy %s value: %s\n", name, *replaced)
	}
	fmt.Fprintln(stdout, next)
	return 0
}

func counter(n *int, legacy string) string {
	if n == nil {
		return "legacy: " + legacy
	}
	return fmt.Sprint(*n)
}
