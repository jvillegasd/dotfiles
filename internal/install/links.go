package install

import (
	"errors"
	"fmt"
	"io/fs"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"syscall"
	"time"
)

// exists is true for anything at a path, a dangling symlink included.
func exists(path string) bool {
	_, err := os.Lstat(path)
	return err == nil
}

func isLink(path string) bool {
	info, err := os.Lstat(path)
	return err == nil && info.Mode()&fs.ModeSymlink != 0
}

func isDir(path string) bool {
	info, err := os.Stat(path)
	return err == nil && info.IsDir()
}

func isFile(path string) bool {
	info, err := os.Stat(path)
	return err == nil && info.Mode().IsRegular()
}

func readlink(path string) string {
	target, _ := os.Readlink(path)
	return target
}

// entries lists a directory as full paths, sorted, hidden names skipped, and nothing for a missing directory.
func entries(dir string) []string {
	list, err := os.ReadDir(dir)
	if err != nil {
		return nil
	}
	var paths []string
	for _, entry := range list {
		if !strings.HasPrefix(entry.Name(), ".") {
			paths = append(paths, filepath.Join(dir, entry.Name()))
		}
	}
	return paths
}

func exitCode(err error) int {
	var exit *exec.ExitError
	if errors.As(err, &exit) {
		return exit.ExitCode()
	}
	if err != nil {
		return -1
	}
	return 0
}

func (in *installer) skillRoots() []string {
	return []string{filepath.Join(in.home, ".agents", "skills"), filepath.Join(in.home, ".claude", "skills"), filepath.Join(in.config, "opencode", "skills")}
}

func (in *installer) commandRoots() []string {
	return []string{filepath.Join(in.home, ".claude", "commands"), filepath.Join(in.config, "opencode", "command")}
}

// agentOut is this checkout's own untracked directory of rendered role agents. A client link's text pointing into it is what proves this checkout wrote the link.
func (in *installer) agentOut() string {
	return filepath.Join(in.harness, ".generated", "agents")
}

// agentRoots pairs each client with the directory its role agents are linked into.
func (in *installer) agentRoots() [][2]string {
	return [][2]string{{"claude", filepath.Join(in.home, ".claude", "agents")}, {"opencode", filepath.Join(in.config, "opencode", "agents")}}
}

// skillNames are the real directories under harness/skills; a symlink there is not a skill this harness ships.
func (in *installer) skillNames() []string {
	list, err := os.ReadDir(filepath.Join(in.harness, "skills"))
	must(err)
	var names []string
	for _, entry := range list {
		if entry.IsDir() {
			names = append(names, entry.Name())
		}
	}
	return names
}

func (in *installer) commands() []string {
	var paths []string
	for _, path := range entries(filepath.Join(in.harness, "commands")) {
		if strings.HasSuffix(path, ".md") {
			paths = append(paths, path)
		}
	}
	return paths
}

func (in *installer) ensureBackupRoot() {
	if in.backupRoot == "" {
		in.backupRoot = filepath.Join(in.home, ".dotfiles-backups", "harness", fmt.Sprintf("%s-%d", time.Now().Format("20060102-150405"), os.Getpid()))
		must(os.MkdirAll(in.backupRoot, 0o755))
	}
}

// backupExisting moves whatever is at path into this run's backup root, or deletes it under --no-backup. A directory symlink is parked under a suffixed name, because at the plain path a later backup expecting a directory would write through it into the link's target.
func (in *installer) backupExisting(path, suffix string) {
	if !exists(path) {
		return
	}
	if in.noBackup {
		must(os.RemoveAll(path))
		in.log("Removed %s", path)
		return
	}
	in.ensureBackupRoot()
	backup := filepath.Join(in.backupRoot, strings.TrimPrefix(path, in.home+"/")+suffix)
	must(os.MkdirAll(filepath.Dir(backup), 0o755))
	if err := os.Rename(path, backup); errors.Is(err, syscall.EXDEV) {
		// A rename cannot cross filesystems, and mv copies then deletes. mv would move path inside a backup that already exists, where a rename refuses, so it refuses too.
		if exists(backup) {
			die("Backup path already exists: %s", backup)
		}
		if out, err := exec.Command("mv", path, backup).CombinedOutput(); err != nil {
			die("mv %s %s: %v: %s", path, backup, err, out)
		}
	} else {
		must(err)
	}
	in.log("Backed up %s -> %s", path, backup)
}

// backupCopy archives a file about to be rewritten in place. The first copy in a run wins, so a second writer never archives the first one's output in place of the original.
func (in *installer) backupCopy(path string) {
	if !isFile(path) || in.noBackup {
		return
	}
	in.ensureBackupRoot()
	backup := filepath.Join(in.backupRoot, strings.TrimPrefix(path, in.home+"/")+".pre-reconcile")
	if isFile(backup) {
		return
	}
	info, err := os.Stat(path)
	must(err)
	data, err := os.ReadFile(path)
	must(err)
	must(os.MkdirAll(filepath.Dir(backup), 0o755))
	must(os.WriteFile(backup, data, info.Mode().Perm()))
	must(os.Chtimes(backup, info.ModTime(), info.ModTime()))
}

func (in *installer) linkManaged(source, dest string) {
	if isLink(dest) && readlink(dest) == source {
		return
	}
	in.backupExisting(dest, "")
	must(os.MkdirAll(filepath.Dir(dest), 0o755))
	must(os.Symlink(source, dest))
	in.log("Linked %s -> %s", dest, source)
}

// unlinkManaged is the inverse of linkManaged and tests exactly what it writes: a symlink whose text is this source. Anything else at the path is not the uninstall's to remove.
func (in *installer) unlinkManaged(source, dest string) {
	if isLink(dest) && readlink(dest) == source {
		in.backupExisting(dest, "")
	}
}

// ensureManagedDir makes a managed root a real directory, so harness links and private entries sit side by side. A symlink standing in for one is moved aside, because linking into someone else's directory would write entries the orphan sweep never covers. Without create, a root the harness only sweeps is normalized but never created.
func (in *installer) ensureManagedDir(dest string, create bool) {
	if info, err := os.Lstat(dest); err == nil {
		if info.Mode()&fs.ModeSymlink != 0 {
			in.backupExisting(dest, ".previous-link")
		} else if !info.IsDir() {
			in.backupExisting(dest, "")
		}
	}
	if create {
		must(os.MkdirAll(dest, 0o755))
	}
}

// retireShadowedSkills moves aside a real directory shadowing a managed skill name. It survives the orphan sweep because it is not a symlink, and it stays live in the client whether or not the harness links that name.
func (in *installer) retireShadowedSkills() {
	for _, root := range in.skillRoots() {
		if !isDir(root) {
			continue
		}
		for _, name := range in.skillNames() {
			if path := filepath.Join(root, name); exists(path) && !isLink(path) {
				in.backupExisting(path, "")
			}
		}
	}
}

// reconcileOrphans removes every link this harness installed and no longer installs: a link resolving into the harness to something undesired, or under a name other than its target's. A dangling link is archived wherever it points, and left alone during an uninstall, which deletes instead.
//
// That dangling branch is a known defect, deliberately left alone: a dangling target resolves to nothing, so its owner cannot be tested. Two ownership predicates on the link text failed in opposite directions, so the fix is a different way of deciding ownership, tracked separately. Do not patch it in passing.
func (in *installer) reconcileOrphans(desired map[string]bool) {
	for _, root := range append(in.skillRoots(), in.commandRoots()...) {
		if !isDir(root) {
			continue
		}
		for _, entry := range entries(root) {
			if !isLink(entry) {
				continue
			}
			if _, err := os.Stat(entry); err != nil {
				if !in.uninstall {
					in.backupExisting(entry, "")
				}
				continue
			}
			target, err := filepath.EvalSymlinks(entry)
			must(err)
			if strings.HasPrefix(target, in.harness+"/") && (!desired[target] || filepath.Base(entry) != filepath.Base(target)) {
				in.backupExisting(entry, "")
			}
		}
	}
}

func (in *installer) installLinks() {
	in.ensureManagedDir(filepath.Join(in.home, ".agents", "skills"), true)
	in.ensureManagedDir(filepath.Join(in.home, ".claude", "skills"), true)
	// OpenCode reads ~/.agents/skills, so this root exists only to be swept.
	in.ensureManagedDir(filepath.Join(in.config, "opencode", "skills"), false)
	for _, root := range in.commandRoots() {
		in.ensureManagedDir(root, true)
	}
	in.retireShadowedSkills()

	desired := map[string]bool{}
	for _, skill := range in.skillNames() {
		desired[filepath.Join(in.harness, "skills", skill)] = true
	}
	for _, command := range in.commands() {
		desired[command] = true
	}
	in.reconcileOrphans(desired)

	for _, skill := range in.skillNames() {
		source := filepath.Join(in.harness, "skills", skill)
		// OpenCode reads ~/.agents/skills, so a second copy would double-list.
		in.backupExisting(filepath.Join(in.config, "opencode", "skills", skill), "")
		in.linkManaged(source, filepath.Join(in.home, ".agents", "skills", skill))
		in.linkManaged(source, filepath.Join(in.home, ".claude", "skills", skill))
	}
	for _, command := range in.commands() {
		for _, root := range in.commandRoots() {
			in.linkManaged(command, filepath.Join(root, filepath.Base(command)))
		}
	}
	in.linkManaged(filepath.Join(in.harness, "statusline", "claude.sh"), filepath.Join(in.home, ".claude", "statusline.sh"))
	in.linkManaged(filepath.Join(in.harness, "POLICY.md"), filepath.Join(in.home, ".claude", "CLAUDE.md"))
	in.linkManaged(filepath.Join(in.harness, "POLICY.md"), filepath.Join(in.config, "opencode", "AGENTS.md"))
	in.installAgents()
	// The SEO group is gone, and its launcher sits outside the swept roots.
	in.backupExisting(filepath.Join(in.home, ".local", "bin", "claude-seo"), "")
}

// uninstallLinks removes everything installLinks wrote: the orphan sweep told nothing is desired, whose ownership test is already the harness's, then the three named links outside the swept roots.
func (in *installer) uninstallLinks() {
	in.reconcileOrphans(nil)
	in.unlinkManaged(filepath.Join(in.harness, "POLICY.md"), filepath.Join(in.home, ".claude", "CLAUDE.md"))
	in.unlinkManaged(filepath.Join(in.harness, "POLICY.md"), filepath.Join(in.config, "opencode", "AGENTS.md"))
	in.unlinkManaged(filepath.Join(in.harness, "statusline", "claude.sh"), filepath.Join(in.home, ".claude", "statusline.sh"))
	in.removeAgents()
}

// sweepAgentLinks removes this checkout's agent links, all of them during an uninstall and otherwise those whose definition was retired. A link is this checkout's only when its text points into agentOut, so a private agent and another checkout's link are never touched.
func (in *installer) sweepAgentLinks() {
	for _, pair := range in.agentRoots() {
		root := pair[1]
		if !isDir(root) || isLink(root) {
			continue
		}
		for _, entry := range entries(root) {
			target, err := os.Readlink(entry)
			if err != nil || !strings.HasPrefix(target, in.agentOut()+"/") {
				continue
			}
			if _, err := os.Stat(target); in.uninstall || err != nil {
				in.backupExisting(entry, "")
			}
		}
	}
}

// installAgents renders the role agents and links them into each client, refusing an unowned root or collision before linking anything. The renderer prints every enforcement gap, so what a client cannot restrict is never reported as enforced.
func (in *installer) installAgents() {
	render := exec.Command(filepath.Join(in.harness, "clients", "agents.py"), filepath.Join(in.harness, "clients", "assignments.json"), in.agentOut())
	render.Stdout, render.Stderr = in.stdout, in.stderr
	if code := exitCode(render.Run()); code != 0 && code != 3 {
		die("Generating the role agents failed with status %d.", code)
	}
	for _, pair := range in.agentRoots() {
		client, root := pair[0], pair[1]
		if info, err := os.Lstat(root); err == nil && (info.Mode()&fs.ModeSymlink != 0 || !info.IsDir()) {
			die("Unowned role agent root: %s", root)
		}
		for _, entry := range entries(filepath.Join(in.agentOut(), client)) {
			if dest := filepath.Join(root, filepath.Base(entry)); exists(dest) && (!isLink(dest) || readlink(dest) != entry) {
				die("Unowned role agent collision: %s", dest)
			}
		}
	}
	for _, pair := range in.agentRoots() {
		in.ensureManagedDir(pair[1], true)
	}
	in.sweepAgentLinks()
	for _, pair := range in.agentRoots() {
		for _, entry := range entries(filepath.Join(in.agentOut(), pair[0])) {
			in.linkManaged(entry, filepath.Join(pair[1], filepath.Base(entry)))
		}
	}
}

func (in *installer) checkAgents() {
	check := exec.Command(filepath.Join(in.harness, "clients", "agents.py"), "--check", filepath.Join(in.harness, "clients", "assignments.json"), in.agentOut())
	check.Stdout, check.Stderr = in.stdout, in.stderr
	if check.Run() != nil {
		die("Role agents in %s are missing, drifted, or widened.", in.agentOut())
	}
	for _, pair := range in.agentRoots() {
		for _, entry := range entries(filepath.Join(in.agentOut(), pair[0])) {
			if dest := filepath.Join(pair[1], filepath.Base(entry)); readlink(dest) != entry {
				die("Missing role agent link: %s", dest)
			}
		}
	}
}

func (in *installer) removeAgents() {
	in.sweepAgentLinks()
	must(os.RemoveAll(in.agentOut()))
	_ = os.Remove(filepath.Join(in.harness, ".generated"))
}

// checkAgentsRemoved follows a symlinked root on purpose: the sweep never writes through a directory this checkout does not own, so a link it left inside one fails here by name.
func (in *installer) checkAgentsRemoved() {
	for _, pair := range in.agentRoots() {
		if !isDir(pair[1]) {
			continue
		}
		for _, entry := range entries(pair[1]) {
			if isLink(entry) && strings.HasPrefix(readlink(entry), in.agentOut()+"/") {
				die("Role agent link survived the uninstall: %s", entry)
			}
		}
	}
	if _, err := os.Stat(in.agentOut()); err == nil {
		die("Generated role agents survived the uninstall: %s", in.agentOut())
	}
}
