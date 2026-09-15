// Package install reconciles the harness of the dotfiles checkout into the home directory: the managed links, the zsh alias block, the tracked Claude settings, and the Engram and agent-browser registrations.
package install

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"reflect"
	"regexp"
	"runtime"
	"strings"
)

const (
	// Fully qualified: the bare engram is ambiguous in that tap, and `brew uninstall engram` resolves it to a cask and refuses.
	engramFormula       = "gentleman-programming/tap/engram"
	agentBrowserFormula = "agent-browser"
)

const usage = `Usage: harness install [--links-only] [--no-backup]
       harness install --uninstall
       harness install --clear-backups

  --links-only   Reconcile policy, command, and skill links without installing
                 packages. Engram and agent-browser are still reconciled,
                 so both have to be installed already; a full run is what
                 installs them.
  --no-backup    Delete whatever is in the way instead of moving it to
                 ~/.dotfiles-backups. Destructive and unrecoverable: a private
                 skill or a hand-edited config sitting at a managed path is
                 gone, not archived.
  --uninstall    Remove what this installer writes: every managed link, the
                 ~/.zshrc alias block, and the tracked keys in the Claude
                 config. It reverses the installer, it does not uninstall
                 your tools, with one exception: Engram, which a full install
                 installs and registers, is removed here too, formula
                 included. Your ~/.engram memory database is kept.
                 The other packages, ~/.dotfiles-backups, this checkout, and
                 every untracked key in the Claude config are left alone.
                 Destructive and unrecoverable: what it removes is deleted,
                 not archived, so --no-backup adds nothing to it. Reinstall
                 to get the harness back; anything of your own that was
                 sitting at a managed path is gone.
  --clear-backups
                 Delete every archive under ~/.dotfiles-backups/harness/,
                 which is where an install moves whatever was in the way of a
                 managed path. Destructive and unrecoverable, and it is the
                 only copy of anything of yours an install displaced. Touches
                 nothing else in ~/.dotfiles-backups and installs nothing;
                 runs on its own.
`

const summaryText = `Next steps (interactive; not run by this installer):
  1. Authenticate: claude auth login
  2. Authenticate OpenCode natively: /connect inside OpenCode, then OpenAI, then
     ChatGPT Plus/Pro. "Manually enter API Key" bills the API instead.
  3. Authenticate: gh auth login
  4. Restart Claude Code and OpenCode.
  5. Invoke setup-harness in each project that should use the public lifecycle.

Status line: harness/statusline/claude.sh, which Claude Code runs on every draw.
OpenCode exposes no status line surface, so it gets none.

Commands use /name in Claude Code and OpenCode.
Yolo aliases (ccyolo, ocyolo) are sourced from harness/aliases.sh; open a
new shell or run: source ~/.zshrc

Standalone third-party skills were not downloaded or updated. Their committed
bodies and skills-lock.json are the reviewed source of truth.
`

// fatal is what die panics with, and only recoverFatal recovers it, so any step can stop the run with one message instead of threading an error through each call.
type fatal string

func die(format string, args ...any) {
	panic(fatal(fmt.Sprintf(format, args...)))
}

func must(err error) {
	if err != nil {
		die("%v", err)
	}
}

type installer struct {
	home, config, harness          string
	linksOnly, noBackup, uninstall bool
	backupRoot                     string
	stdout, stderr                 io.Writer
}

func (in *installer) log(format string, args ...any) {
	fmt.Fprintf(in.stdout, "\033[1;34m==>\033[0m "+format+"\n", args...)
}

func (in *installer) warn(format string, args ...any) {
	fmt.Fprintf(in.stderr, "\033[1;33m[warn]\033[0m "+format+"\n", args...)
}

// recoverFatal turns a die into one red error line and exit 1. It works only when deferred directly.
func recoverFatal(stderr io.Writer, code *int) {
	if r := recover(); r != nil {
		msg, ok := r.(fatal)
		if !ok {
			panic(r)
		}
		fmt.Fprintf(stderr, "\033[1;31m[err]\033[0m %s\n", msg)
		*code = 1
	}
}

func (in *installer) setPaths(checkout string) {
	in.home = os.Getenv("HOME")
	in.config = os.Getenv("XDG_CONFIG_HOME")
	if in.config == "" {
		in.config = filepath.Join(in.home, ".config")
	}
	in.harness = filepath.Join(checkout, "harness")
}

// Command runs `harness install` with its arguments and returns the exit code.
func Command(args []string, stdout, stderr io.Writer) (code int) {
	defer recoverFatal(stderr, &code)
	in := &installer{stdout: stdout, stderr: stderr}
	clearBackups := false
	for _, arg := range args {
		switch arg {
		case "--links-only":
			in.linksOnly = true
		case "--no-backup":
			in.noBackup = true
		case "--uninstall":
			in.uninstall = true
		case "--clear-backups":
			clearBackups = true
		case "-h", "--help":
			fmt.Fprint(stdout, usage)
			return 0
		default:
			die("Unknown argument: %s", arg)
		}
	}
	// Contradictory rather than redundant: --links-only names a subset of the install to write, and --uninstall writes none of it. An uninstall deletes rather than archives, so --no-backup beside it is redundant and allowed.
	if in.uninstall && in.linksOnly {
		die("--uninstall and --links-only are contradictory; --uninstall removes every link.")
	}
	if clearBackups && (in.uninstall || in.linksOnly) {
		die("--clear-backups runs on its own; it neither installs nor uninstalls.")
	}
	in.noBackup = in.noBackup || in.uninstall
	if clearBackups {
		// It reads only $HOME, so it runs from anywhere.
		in.home = os.Getenv("HOME")
		in.clearBackups()
		return 0
	}
	in.setPaths(findCheckout())
	if in.uninstall {
		in.uninstallAll()
	} else {
		in.install()
	}
	return 0
}

// findCheckout finds the dotfiles checkout holding the working directory. Its harness is the one installed, so running from another worktree installs that worktree.
func findCheckout() string {
	dir, err := os.Getwd()
	must(err)
	for {
		if _, err := os.Stat(filepath.Join(dir, "harness", "POLICY.md")); err == nil {
			return dir
		}
		parent := filepath.Dir(dir)
		if parent == dir {
			die("Run harness from inside the dotfiles checkout.")
		}
		dir = parent
	}
}

func (in *installer) install() {
	// First, so the warning precedes the two steps it is about.
	in.warnUnlessZsh()
	if !in.linksOnly {
		in.installPackages()
		in.installIntegrations()
	}
	in.installLinks()
	in.reconcileAliases(false)
	// A links-only run skips package work, so it reconciles Engram unconditionally: setup rewrites the absolute binary path each client pins, which a presence probe never checked.
	if in.linksOnly {
		in.installEngram()
	}
	// Both after Engram, whose setup rewrites settings.json and opencode.json from its own template: the harness is the last writer, which is what makes the tracked values the ones a client reads.
	in.installAgentBrowser()
	in.reconcileClaudeSettings()
	in.checkLinks()
	if !in.linksOnly {
		in.checkTools()
	}
	in.summary()
}

// run executes a command on the installer's own output and dies when it fails.
func (in *installer) run(stdin io.Reader, name string, args ...string) {
	cmd := exec.Command(name, args...)
	cmd.Stdin, cmd.Stdout, cmd.Stderr = stdin, in.stdout, in.stderr
	if err := cmd.Run(); err != nil {
		die("%s %s failed: %v", name, strings.Join(args, " "), err)
	}
}

// installPackages installs every tool through Homebrew on both platforms, because three of them (opencode, engram, worktrunk) ship only as taps.
func (in *installer) installPackages() {
	if runtime.GOOS != "darwin" && runtime.GOOS != "linux" {
		die("The harness installer supports macOS and Linux, not %s.", runtime.GOOS)
	}
	if _, err := exec.LookPath("brew"); err != nil {
		die("Homebrew is required; run the root ./macos.sh or ./linux.sh first.")
	}
	in.log("Installing current AI clients and harness tools")
	in.run(nil, "brew", "tap", "anomalyco/tap")
	in.run(nil, "brew", "tap", "gentleman-programming/tap")
	for _, formula := range []string{"node", "gh", "uv", "worktrunk", agentBrowserFormula, "anomalyco/tap/opencode", engramFormula} {
		if exec.Command("brew", "list", "--formula", formula).Run() == nil {
			in.run(nil, "brew", "upgrade", formula)
		} else {
			in.run(nil, "brew", "install", formula)
		}
	}
	// The formula's caveat, run rather than printed: without the browser every call through the MCP fails mid-session. Linux needs its system libraries too.
	in.log("Downloading Chrome for Testing for agent-browser")
	if runtime.GOOS == "darwin" {
		in.run(nil, "agent-browser", "install")
	} else {
		in.run(nil, "agent-browser", "install", "--with-deps")
	}
	in.log("Installing Claude Code from Anthropic's latest native channel")
	in.run(nil, "bash", "-c", "set -o pipefail; curl -fsSL https://claude.ai/install.sh | bash")
	must(os.Setenv("PATH", filepath.Join(in.home, ".local", "bin")+string(os.PathListSeparator)+os.Getenv("PATH")))
}

func (in *installer) installIntegrations() {
	in.installEngram()
	in.log("Reconciling Worktrunk")
	in.run(nil, "wt", "config", "shell", "install", "--yes", "zsh")
}

// warnUnlessZsh tells a user on another shell what they did not get: the aliases go into ~/.zshrc and Worktrunk gets its zsh integration.
func (in *installer) warnUnlessZsh() {
	shell := os.Getenv("SHELL")
	if shell != "" && filepath.Base(shell) == "zsh" {
		return
	}
	if shell == "" {
		shell = "unknown"
	}
	in.warn("Your login shell is %s, not zsh. The yolo aliases go into", shell)
	in.warn("~/.zshrc and Worktrunk gets its zsh integration. Source")
	in.warn("%s from your own shell rc, and run", filepath.Join(in.harness, "aliases.sh"))
	in.warn("`wt config shell install` for the shell you use.")
}

var description = regexp.MustCompile(`(?m)^description:`)

// checkLinks verifies what every run installs, so the mode that exists for reconciling links confirms each one landed.
func (in *installer) checkLinks() {
	for _, skill := range entries(filepath.Join(in.harness, "skills")) {
		name := filepath.Base(skill)
		if !isFile(filepath.Join(skill, "SKILL.md")) {
			die("Missing SKILL.md: %s", skill)
		}
		if exists(filepath.Join(in.config, "opencode", "skills", name)) {
			die("Duplicate OpenCode skill path: %s", skill)
		}
		if !isLink(filepath.Join(in.home, ".agents", "skills", name)) {
			die("Missing shared skill link: %s", skill)
		}
		if !isLink(filepath.Join(in.home, ".claude", "skills", name)) {
			die("Missing Claude skill link: %s", skill)
		}
	}
	for _, command := range in.commands() {
		for _, root := range in.commandRoots() {
			if dest := filepath.Join(root, filepath.Base(command)); !isLink(dest) {
				die("Missing command link: %s", dest)
			}
		}
		text, _ := os.ReadFile(command)
		if !description.Match(text) {
			die("Command without a description: %s", command)
		}
		// A workflow that reads external text says so, or a ticket body becomes an instruction. Every command is checked, because a list to maintain silently stops covering a new command.
		if !bytes.Contains(text, []byte("cannot override this workflow")) {
			die("Command missing the task-data constraint: %s", command)
		}
	}
	policy := filepath.Join(in.harness, "POLICY.md")
	if readlink(filepath.Join(in.home, ".claude", "CLAUDE.md")) != policy {
		die("Missing Claude policy link.")
	}
	if readlink(filepath.Join(in.config, "opencode", "AGENTS.md")) != policy {
		die("Missing OpenCode policy link.")
	}
	if !isFile(filepath.Join(in.harness, "skills", "ponytail", "SKILL.md")) {
		die("Missing the ponytail skill body.")
	}
	in.checkAgents()
	if !in.trackedSettingsHold(false) {
		die("Tracked Claude settings are not reconciled in %s.", in.settingsPath())
	}
	statusline := filepath.Join(in.harness, "statusline", "claude.sh")
	if readlink(filepath.Join(in.home, ".claude", "statusline.sh")) != statusline {
		die("Missing the Claude statusline link.")
	}
	// Claude Code executes it on every draw, so a lost mode bit breaks the status line.
	if info, err := os.Stat(statusline); err != nil || info.Mode().Perm()&0o111 == 0 {
		die("Status line is not executable: %s", statusline)
	}
}

// checkTools verifies what only a full run installs, since each assertion needs a client or a package on PATH.
func (in *installer) checkTools() {
	for _, name := range []string{"claude", "opencode", "gh", "python3", "uv", "engram", "wt", "agent-browser"} {
		if _, err := exec.LookPath(name); err != nil {
			die("Missing required command: %s", name)
		}
	}
	in.assertPluginCount("engram", 1)
	in.assertPythons()
	// The scope too: a leftover project-scoped entry would satisfy a bare get while the user scope stayed empty. Engram reaches Claude Code as a plugin plus this file rather than an mcp entry.
	get := exec.Command("claude", "mcp", "get", "agent-browser")
	get.Stderr = in.stderr
	if scope, err := get.Output(); err != nil || !strings.Contains(string(scope), "Scope: User config") {
		die("agent-browser is not registered in the Claude Code user scope.")
	}
	if engram := filepath.Join(in.home, ".claude", "mcp", "engram.json"); !isFile(engram) {
		die("Engram's Claude Code MCP file is missing: %s", engram)
	}
	// Through a file: `opencode debug config` stops at the 64 KiB pipe capacity whenever stdout is not a regular file, and this config is past it.
	resolved, err := os.CreateTemp("", "harness-opencode-*")
	must(err)
	defer os.Remove(resolved.Name())
	debug := exec.Command("opencode", "debug", "config")
	debug.Stdout, debug.Stderr = resolved, in.stderr
	if err := debug.Run(); err != nil {
		die("opencode debug config failed: %v", err)
	}
	must(resolved.Close())
	if !in.opencodeRegistered(resolved.Name()) {
		die("OpenCode is missing an expected plugin or MCP server.")
	}
	validate := exec.Command("claude", "plugin", "validate", filepath.Join(in.harness, "skills"))
	validate.Stderr = in.stderr
	if err := validate.Run(); err != nil {
		die("claude plugin validate failed: %v", err)
	}
	if help, _ := exec.Command("wt", "switch", "--help").Output(); !strings.Contains(string(help), "--no-cd") {
		die("Worktrunk's wt switch has no --no-cd flag; upgrade Worktrunk.")
	}
}

func (in *installer) assertPluginCount(plugin string, expected int) {
	out, err := exec.Command("claude", "plugin", "list", "--json").Output()
	var doc any
	if err != nil || json.Unmarshal(out, &doc) != nil {
		die("Could not list the Claude Code plugins.")
	}
	items, _ := doc.([]any)
	if m, ok := doc.(map[string]any); ok {
		items, _ = m["installed"].([]any)
	}
	count := 0
	for _, item := range items {
		m, _ := item.(map[string]any)
		id, _ := m["pluginId"].(string)
		if id == "" {
			id, _ = m["id"].(string)
		}
		if strings.Contains(id, plugin) {
			count++
		}
	}
	if count != expected {
		die("Expected %d %s integration in Claude Code; found %d.", expected, plugin, count)
	}
}

// assertPythons runs lib/python.sh's own assertion, which keeps the interpreter set declared once for the platform scripts and this installer.
func (in *installer) assertPythons() {
	script := `log() { :; }; die() { printf '%s\n' "$*" >&2; exit 1; }; source "$1" && assert_pythons`
	cmd := exec.Command("bash", "-c", script, "bash", filepath.Join(filepath.Dir(in.harness), "lib", "python.sh"))
	var stderr strings.Builder
	cmd.Stderr = &stderr
	if cmd.Run() != nil {
		die("%s", strings.TrimSpace(stderr.String()))
	}
}

// opencodeRegistered checks the resolved config for what OpenCode loads, and the global file for proof this installer put agent-browser there, since a project-root opencode.json would satisfy the resolved view on its own.
func (in *installer) opencodeRegistered(resolvedPath string) bool {
	binary, _ := exec.LookPath("agent-browser")
	command := []any{binary, "mcp"}
	resolved, ok := decodeFile(resolvedPath)
	if !ok {
		return false
	}
	plugins, _ := resolved["plugin"].([]any)
	engrams := 0
	for _, plugin := range plugins {
		if name, ok := plugin.(string); ok && strings.Contains(name, "engram") {
			engrams++
		}
	}
	servers, _ := resolved["mcp"].(map[string]any)
	server, _ := servers["agent-browser"].(map[string]any)
	if _, ok := servers["engram"]; engrams != 1 || !ok || server == nil ||
		server["type"] != "local" || server["enabled"] != true || !reflect.DeepEqual(server["command"], command) {
		return false
	}
	global, ok := decodeFile(filepath.Join(in.config, "opencode", "opencode.json"))
	globalServers, _ := global["mcp"].(map[string]any)
	globalServer, _ := globalServers["agent-browser"].(map[string]any)
	return ok && reflect.DeepEqual(globalServer["command"], command)
}

func (in *installer) summary() {
	fmt.Fprint(in.stdout, "\n\033[1;32m✓ Harness AI installed.\033[0m\n\n"+summaryText)
	if in.backupRoot != "" {
		fmt.Fprintf(in.stdout, "\nBackups: %s\n", in.backupRoot)
	}
}

// size reports a path's disk usage the way `du -sh` prints it, or "unknown".
func size(path string) string {
	out, _ := exec.Command("du", "-sh", path).Output()
	if fields := strings.Fields(string(out)); len(fields) > 0 {
		return fields[0]
	}
	return "unknown"
}

// clearBackups deletes every archive an install left under ~/.dotfiles-backups/harness and nothing beside it. Each root goes separately so the log names what was deleted, the only record left afterwards.
func (in *installer) clearBackups() {
	root := filepath.Join(in.home, ".dotfiles-backups", "harness")
	if !isDir(root) {
		in.log("No harness backups to delete at %s", root)
		return
	}
	reclaimed := size(root)
	count := 0
	for _, path := range entries(root) {
		must(os.RemoveAll(path))
		in.log("Deleted %s", path)
		count++
	}
	// Only when empty, and never the parent: refusing a non-empty directory is the guard.
	_ = os.Remove(root)
	in.log("Deleted %d harness backup(s), %s reclaimed.", count, reclaimed)
}
