package main

import (
	"bytes"
	"encoding/json"
	"io/fs"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
)

// lockRun is a throwaway checkout with the lock tool's paths, an isolated HOME, and a shim directory.
type lockRun struct {
	root, shims, home string
}

func newLockRun(t *testing.T) lockRun {
	t.Helper()
	base := t.TempDir()
	lr := lockRun{
		root:  filepath.Join(base, "checkout"),
		shims: filepath.Join(base, "shims"),
		home:  filepath.Join(base, "home"),
	}
	for _, dir := range []string{"harness/skills", "harness/commands", ".claude/skills", "lib"} {
		if err := os.MkdirAll(filepath.Join(lr.root, dir), 0o755); err != nil {
			t.Fatal(err)
		}
	}
	for _, dir := range []string{lr.shims, lr.home} {
		if err := os.MkdirAll(dir, 0o755); err != nil {
			t.Fatal(err)
		}
	}
	writeMode(t, filepath.Join(lr.root, "harness", "POLICY.md"), "# policy\n", 0o644)
	writeMode(t, filepath.Join(lr.root, "skills-lock.json"), "{\n  \"version\": 1,\n  \"skills\": {}\n}\n", 0o644)
	return lr
}

// setNpx writes the shim at PATH: it records every call and, when install is set, performs what skills.sh would do for an add.
func (lr lockRun) setNpx(t *testing.T, install bool) {
	t.Helper()
	script := `#!/bin/sh
root="$PWD"
echo "npx $*" >> "$root/npx.log"
[ "$1" = "skills@1" ] || exit 0
[ "$2" = "add" ] || exit 0
[ "` + boolFlag(install) + `" = "yes" ] || exit 0
shift 2
name=""
while [ $# -gt 0 ]; do
  case "$1" in
    --skill) name="$2"; shift 2 ;;
    *) shift ;;
  esac
done
mkdir -p "$root/harness/skills/$name"
echo "# $name" > "$root/harness/skills/$name/SKILL.md"
python3 - "$root/skills-lock.json" "$name" <<'PY'
import json, sys
path, name = sys.argv[1], sys.argv[2]
data = json.load(open(path))
data["skills"][name] = {
    "source": "owner/repo",
    "sourceType": "github",
    "skillPath": "skills/%s/SKILL.md" % name,
    "computedHash": "0" * 64,
}
json.dump(data, open(path, "w"), indent=2)
open(path, "a").write("\n")
PY
`
	writeMode(t, filepath.Join(lr.shims, "npx"), script, 0o755)
}

func boolFlag(b bool) string {
	if b {
		return "yes"
	}
	return "no"
}

func (lr lockRun) harness(t *testing.T, args ...string) result {
	t.Helper()
	cmd := exec.Command(binary, args...)
	cmd.Dir = lr.root
	cmd.Env = []string{"HOME=" + lr.home, "PATH=" + lr.shims + ":/usr/bin:/bin", "SHELL=/bin/sh"}
	var stdout, stderr bytes.Buffer
	cmd.Stdout, cmd.Stderr = &stdout, &stderr
	err := cmd.Run()
	code := 0
	if exit, ok := err.(*exec.ExitError); ok {
		code = exit.ExitCode()
	} else if err != nil {
		t.Fatal(err)
	}
	return result{stdout.String(), stderr.String(), code}
}

func (lr lockRun) npxLog(t *testing.T) string {
	t.Helper()
	data, err := os.ReadFile(filepath.Join(lr.root, "npx.log"))
	if err != nil {
		return ""
	}
	return string(data)
}

func (lr lockRun) locked(t *testing.T) map[string]json.RawMessage {
	t.Helper()
	data, err := os.ReadFile(filepath.Join(lr.root, "skills-lock.json"))
	if err != nil {
		t.Fatal(err)
	}
	var lf struct {
		Skills map[string]json.RawMessage `json:"skills"`
	}
	if err := json.Unmarshal(data, &lf); err != nil {
		t.Fatal(err)
	}
	return lf.Skills
}

func TestLocksAddDrivesNpxAndLinks(t *testing.T) {
	lr := newLockRun(t)
	lr.setNpx(t, true)
	r := ok(t, lr.harness(t, "locks", "add", "owner/repo", "myskill"), "locks add")
	if got := lr.npxLog(t); !strings.Contains(got, "npx skills@1 add owner/repo --skill myskill --agent universal -y") {
		t.Fatalf("npx log = %q", got)
	}
	if _, err := os.Stat(filepath.Join(lr.root, "harness/skills/myskill/SKILL.md")); err != nil {
		t.Fatalf("skill body not installed: %v", err)
	}
	target, err := os.Readlink(filepath.Join(lr.root, ".claude/skills/myskill"))
	if err != nil || target != "../../.agents/skills/myskill" {
		t.Fatalf("claude link = %q, %v", target, err)
	}
	if _, ok := lr.locked(t)["myskill"]; !ok {
		t.Fatal("myskill missing from the lock")
	}
	if !strings.Contains(r.stdout, "harness locks check") {
		t.Fatalf("add did not print the review hint: %q", r.stdout)
	}
}

func TestLocksAddRefusesBeforeNpx(t *testing.T) {
	cases := []struct {
		name string
		args []string
		seed func(t *testing.T, lr lockRun)
		want string
	}{
		{"source without slash", []string{"locks", "add", "owner", "myskill"}, nil, "source must be owner/repo"},
		{"invalid owner", []string{"locks", "add", "-bad/repo", "myskill"}, nil, "invalid GitHub owner"},
		{"invalid repo", []string{"locks", "add", "owner/..", "myskill"}, nil, "invalid GitHub repository"},
		{"invalid name", []string{"locks", "add", "owner/repo", "Bad_Name"}, nil, "invalid skill name"},
		{"wrong count", []string{"locks", "add", "owner/repo"}, nil, "add expects 2"},
		{"already locked", []string{"locks", "add", "owner/repo", "myskill"}, func(t *testing.T, lr lockRun) {
			writeMode(t, filepath.Join(lr.root, "skills-lock.json"), "{\n  \"version\": 1,\n  \"skills\": {\"myskill\": {}}\n}\n", 0o644)
		}, "already locked"},
		{"existing skill path", []string{"locks", "add", "owner/repo", "myskill"}, func(t *testing.T, lr lockRun) {
			os.MkdirAll(filepath.Join(lr.root, "harness/skills/myskill"), 0o755)
		}, "skill path already exists"},
		{"existing command", []string{"locks", "add", "owner/repo", "myskill"}, func(t *testing.T, lr lockRun) {
			writeMode(t, filepath.Join(lr.root, "harness/commands/myskill.md"), "x\n", 0o644)
		}, "command name already exists"},
		{"existing claude path", []string{"locks", "add", "owner/repo", "myskill"}, func(t *testing.T, lr lockRun) {
			writeMode(t, filepath.Join(lr.root, ".claude/skills/myskill"), "x\n", 0o644)
		}, "claude path already exists"},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			lr := newLockRun(t)
			if c.seed != nil {
				c.seed(t, lr)
			}
			r := lr.harness(t, c.args...)
			if r.code == 0 || !strings.Contains(r.stderr, c.want) {
				t.Fatalf("%v exited %d with stderr %q, want %q", c.args, r.code, r.stderr, c.want)
			}
			if log := lr.npxLog(t); log != "" {
				t.Fatalf("npx ran for a rejected input: %q", log)
			}
		})
	}
}

func TestLocksAddFailsWhenSkillsShDoesNotInstall(t *testing.T) {
	lr := newLockRun(t)
	lr.setNpx(t, false)
	r := lr.harness(t, "locks", "add", "owner/repo", "myskill")
	if r.code == 0 || !strings.Contains(r.stderr, "did not install") {
		t.Fatalf("exited %d with stderr %q", r.code, r.stderr)
	}
}

func TestLocksUpdateDrivesNpx(t *testing.T) {
	lr := newLockRun(t)
	lr.setNpx(t, false)
	if r := lr.harness(t, "locks", "update", "extra"); r.code == 0 {
		t.Fatal("update with an argument should fail")
	}
	ok(t, lr.harness(t, "locks", "update"), "locks update")
	if got := lr.npxLog(t); !strings.Contains(got, "npx skills@1 update --project --yes") {
		t.Fatalf("npx log = %q", got)
	}
}

func TestLocksRemoveDeletesEntryBodyAndLink(t *testing.T) {
	lr := newLockRun(t)
	seedLockedSkill(t, lr, "myskill")
	ok(t, lr.harness(t, "locks", "remove", "myskill"), "locks remove")
	if _, err := os.Lstat(filepath.Join(lr.root, "harness/skills/myskill")); !os.IsNotExist(err) {
		t.Fatalf("body survived: %v", err)
	}
	if _, err := os.Lstat(filepath.Join(lr.root, ".claude/skills/myskill")); !os.IsNotExist(err) {
		t.Fatalf("link survived: %v", err)
	}
	if _, ok := lr.locked(t)["myskill"]; ok {
		t.Fatal("lock entry survived")
	}
}

func TestLocksRemovePreservesUnknownTopLevelKeys(t *testing.T) {
	lr := newLockRun(t)
	writeMode(t, filepath.Join(lr.root, "harness/skills/myskill/SKILL.md"), "# x\n", 0o644)
	writeMode(t, filepath.Join(lr.root, "skills-lock.json"), `{
  "version": 1,
  "future": {"keep": true},
  "skills": {
    "myskill": {"computedHash": "`+strings.Repeat("0", 64)+`"},
    "other": {"computedHash": "`+strings.Repeat("1", 64)+`"}
  }
}
`, 0o644)
	ok(t, lr.harness(t, "locks", "remove", "myskill"), "locks remove")
	data, err := os.ReadFile(filepath.Join(lr.root, "skills-lock.json"))
	if err != nil {
		t.Fatal(err)
	}
	for _, want := range []string{`"version"`, `"future"`, `"other"`} {
		if !strings.Contains(string(data), want) {
			t.Fatalf("remove dropped %s:\n%s", want, data)
		}
	}
	if strings.Contains(string(data), "myskill") {
		t.Fatalf("remove kept myskill:\n%s", data)
	}
}

func TestLocksRemoveKeepsEntryOrder(t *testing.T) {
	lr := newLockRun(t)
	writeMode(t, filepath.Join(lr.root, "harness/skills/aaa/SKILL.md"), "# x\n", 0o644)
	writeMode(t, filepath.Join(lr.root, "skills-lock.json"), `{
  "version": 1,
  "skills": {
    "zzz": {"computedHash": "`+strings.Repeat("0", 64)+`"},
    "aaa": {"computedHash": "`+strings.Repeat("0", 64)+`"},
    "mmm": {"computedHash": "`+strings.Repeat("0", 64)+`"}
  }
}
`, 0o644)
	ok(t, lr.harness(t, "locks", "remove", "aaa"), "locks remove")
	data, err := os.ReadFile(filepath.Join(lr.root, "skills-lock.json"))
	if err != nil {
		t.Fatal(err)
	}
	got := string(data)
	if strings.Contains(got, `"aaa"`) {
		t.Fatalf("remove kept aaa:\n%s", got)
	}
	if strings.Index(got, `"zzz"`) > strings.Index(got, `"mmm"`) {
		t.Fatalf("remove reordered the surviving entries:\n%s", got)
	}
}

func TestLocksRemoveRefusesUnsafeRemovals(t *testing.T) {
	cases := []struct {
		name string
		args []string
		seed func(t *testing.T, lr lockRun)
		want string
	}{
		{"not locked", []string{"locks", "remove", "myskill"}, nil, "not in skills-lock.json"},
		{"invalid name", []string{"locks", "remove", "Bad_Name"}, nil, "invalid skill name"},
		{"body is a file", []string{"locks", "remove", "myskill"}, func(t *testing.T, lr lockRun) {
			seedLockedSkill(t, lr, "myskill")
			os.RemoveAll(filepath.Join(lr.root, "harness/skills/myskill"))
			writeMode(t, filepath.Join(lr.root, "harness/skills/myskill"), "x\n", 0o644)
		}, "refusing to remove non-directory skill path"},
		{"body is a symlink", []string{"locks", "remove", "myskill"}, func(t *testing.T, lr lockRun) {
			seedLockedSkill(t, lr, "myskill")
			target := filepath.Join(lr.root, "harness/skills/myskill-real")
			os.MkdirAll(target, 0o755)
			os.RemoveAll(filepath.Join(lr.root, "harness/skills/myskill"))
			os.Symlink(target, filepath.Join(lr.root, "harness/skills/myskill"))
		}, "refusing to remove non-directory skill path"},
		{"link is a file", []string{"locks", "remove", "myskill"}, func(t *testing.T, lr lockRun) {
			seedLockedSkill(t, lr, "myskill")
			os.Remove(filepath.Join(lr.root, ".claude/skills/myskill"))
			writeMode(t, filepath.Join(lr.root, ".claude/skills/myskill"), "x\n", 0o644)
		}, "refusing to remove non-symlink Claude path"},
		{"link points elsewhere", []string{"locks", "remove", "myskill"}, func(t *testing.T, lr lockRun) {
			seedLockedSkill(t, lr, "myskill")
			os.Remove(filepath.Join(lr.root, ".claude/skills/myskill"))
			os.Symlink("../../.agents/skills/other", filepath.Join(lr.root, ".claude/skills/myskill"))
		}, "refusing to remove unexpected Claude link"},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			lr := newLockRun(t)
			if c.seed != nil {
				c.seed(t, lr)
			}
			r := lr.harness(t, c.args...)
			if r.code == 0 || !strings.Contains(r.stderr, c.want) {
				t.Fatalf("%v exited %d with stderr %q, want %q", c.args, r.code, r.stderr, c.want)
			}
		})
	}
}

func seedLockedSkill(t *testing.T, lr lockRun, name string) {
	t.Helper()
	writeMode(t, filepath.Join(lr.root, "harness/skills", name, "SKILL.md"), "# "+name+"\n", 0o644)
	writeMode(t, filepath.Join(lr.root, "skills-lock.json"), `{
  "version": 1,
  "skills": {
    "`+name+`": {
      "source": "owner/repo",
      "sourceType": "github",
      "skillPath": "skills/`+name+`/SKILL.md",
      "computedHash": "`+strings.Repeat("0", 64)+`"
    }
  }
}
`, 0o644)
	os.MkdirAll(filepath.Join(lr.root, ".claude/skills"), 0o755)
	if err := os.Symlink("../../.agents/skills/"+name, filepath.Join(lr.root, ".claude/skills", name)); err != nil {
		t.Fatal(err)
	}
}

// TestLocksVerifyMatchesThePinnedLock recomputes the real committed bodies against the lock skills.sh wrote, so a Go collation that diverged from localeCompare would show drift.
func TestLocksVerifyMatchesThePinnedLock(t *testing.T) {
	lr := locksVerifySandbox(t)
	r := ok(t, lr.harness(t, "locks", "verify"), "locks verify")
	if got := strings.Count(r.stdout, ": match"); got != 10 {
		t.Fatalf("verify matched %d skills, want 10:\n%s", got, r.stdout)
	}
}

func TestLocksVerifyReportsDriftForTheEditedBodyOnly(t *testing.T) {
	lr := locksVerifySandbox(t)
	body := filepath.Join(lr.root, "harness/skills/tdd/SKILL.md")
	data, err := os.ReadFile(body)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(body, append(data, '\n'), 0o644); err != nil {
		t.Fatal(err)
	}
	r := lr.harness(t, "locks", "verify")
	if r.code == 0 {
		t.Fatal("verify exited 0 with a drifted body")
	}
	if !strings.Contains(r.stdout, "tdd: drift") {
		t.Fatalf("verify did not report tdd drift:\n%s", r.stdout)
	}
	if got := strings.Count(r.stdout, ": drift"); got != 1 {
		t.Fatalf("verify reported %d drifts, want 1:\n%s", got, r.stdout)
	}
}

func TestLocksVerifyReportsUnverifiableNotDrift(t *testing.T) {
	lr := locksVerifySandbox(t)
	var lf map[string]any
	data, err := os.ReadFile(filepath.Join(lr.root, "skills-lock.json"))
	if err != nil {
		t.Fatal(err)
	}
	if err := json.Unmarshal(data, &lf); err != nil {
		t.Fatal(err)
	}
	skills := lf["skills"].(map[string]any)
	// A 40-hex git tree sha is a blob install's server snapshot, not a locally recomputed folder hash.
	skills["handoff"].(map[string]any)["computedHash"] = strings.Repeat("a", 40)
	// An entry whose body is gone cannot be recomputed either.
	skills["ponytail"].(map[string]any)["computedHash"] = strings.Repeat("b", 64)
	if err := os.RemoveAll(filepath.Join(lr.root, "harness/skills/ponytail")); err != nil {
		t.Fatal(err)
	}
	out, err := json.MarshalIndent(lf, "", "  ")
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(lr.root, "skills-lock.json"), append(out, '\n'), 0o644); err != nil {
		t.Fatal(err)
	}
	r := ok(t, lr.harness(t, "locks", "verify"), "locks verify")
	if got := strings.Count(r.stdout, ": unverifiable"); got != 2 {
		t.Fatalf("verify reported %d unverifiable, want 2:\n%s", got, r.stdout)
	}
	if strings.Contains(r.stdout, ": drift") {
		t.Fatalf("an unverifiable entry was called drift:\n%s", r.stdout)
	}
}

func TestLocksCheckSyntaxAndWhitespace(t *testing.T) {
	valid := map[string]string{
		"macos.sh":      "#!/bin/sh\necho macos\n",
		"linux.sh":      "#!/bin/sh\necho linux\n",
		"lib/common.sh": "#!/bin/sh\ncommon() { :; }\n",
		"lib/python.sh": "#!/bin/sh\necho python\n",
	}
	for _, c := range []struct {
		name    string
		noRepo  bool
		mutate  func(t *testing.T, lr lockRun)
		wantErr bool
		want    string
	}{
		{name: "clean", wantErr: false},
		{name: "not a work tree", noRepo: true, wantErr: true, want: "git diff --check"},
		{name: "missing entry point", mutate: func(t *testing.T, lr lockRun) {
			os.Remove(filepath.Join(lr.root, "lib/python.sh"))
		}, wantErr: true, want: "shell entry point missing"},
		{name: "syntax error", mutate: func(t *testing.T, lr lockRun) {
			writeMode(t, filepath.Join(lr.root, "macos.sh"), "#!/bin/sh\nif true; then\n", 0o755)
		}, wantErr: true, want: "bash -n macos.sh"},
		{name: "whitespace", mutate: func(t *testing.T, lr lockRun) {
			writeMode(t, filepath.Join(lr.root, "tracked.txt"), "clean\n", 0o644)
			git(t, lr.root, "add", "tracked.txt")
			git(t, lr.root, "commit", "-q", "-m", "init")
			writeMode(t, filepath.Join(lr.root, "tracked.txt"), "dirty   \n", 0o644)
		}, wantErr: true, want: "git diff --check"},
	} {
		t.Run(c.name, func(t *testing.T) {
			lr := newLockRun(t)
			for rel, text := range valid {
				writeMode(t, filepath.Join(lr.root, rel), text, 0o755)
			}
			if !c.noRepo {
				git(t, lr.root, "init", "-q", "-b", "main")
			}
			if c.mutate != nil {
				c.mutate(t, lr)
			}
			r := lr.harness(t, "locks", "check")
			if c.wantErr {
				if r.code == 0 || !strings.Contains(r.stderr, c.want) {
					t.Fatalf("check exited %d with stderr %q, want %q", r.code, r.stderr, c.want)
				}
				return
			}
			if r.code != 0 {
				t.Fatalf("check exited %d: %s", r.code, r.stderr)
			}
		})
	}
}

func locksVerifySandbox(t *testing.T) lockRun {
	t.Helper()
	lr := newLockRun(t)
	repo := filepath.Join("..", "..")
	if err := copyTree(t, filepath.Join(repo, "harness", "skills"), filepath.Join(lr.root, "harness", "skills")); err != nil {
		t.Fatal(err)
	}
	data, err := os.ReadFile(filepath.Join(repo, "skills-lock.json"))
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(lr.root, "skills-lock.json"), data, 0o644); err != nil {
		t.Fatal(err)
	}
	return lr
}

func copyTree(t *testing.T, src, dst string) error {
	t.Helper()
	return filepath.WalkDir(src, func(path string, d fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		rel, err := filepath.Rel(src, path)
		if err != nil {
			return err
		}
		target := filepath.Join(dst, rel)
		if d.IsDir() {
			return os.MkdirAll(target, 0o755)
		}
		if !d.Type().IsRegular() {
			return nil
		}
		data, err := os.ReadFile(path)
		if err != nil {
			return err
		}
		if err := os.MkdirAll(filepath.Dir(target), 0o755); err != nil {
			return err
		}
		return os.WriteFile(target, data, 0o644)
	})
}
