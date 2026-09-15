package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// benchDir returns a throwaway checkout whose cohorts decide the split, so the
// fixture's report does not depend on this machine's gitignored cohorts.json.
func benchDir(t *testing.T) string {
	t.Helper()
	dir := t.TempDir()
	if err := os.MkdirAll(filepath.Join(dir, "harness", "bench"), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(dir, "harness", "POLICY.md"), []byte("x\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	cohorts, err := os.ReadFile(filepath.Join("testdata", "bench", "cohorts.json"))
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(dir, "harness", "bench", "cohorts.json"), cohorts, 0o644); err != nil {
		t.Fatal(err)
	}
	return dir
}

func benchHome(t *testing.T) string {
	t.Helper()
	home, err := filepath.Abs(filepath.Join("testdata", "bench", "home"))
	if err != nil {
		t.Fatal(err)
	}
	return home
}

// sameReport compares line by line, ignoring the trailing pad the fixed-width
// sessions row leaves behind, which the repository's whitespace rule strips.
func sameReport(got, want string) bool {
	a := strings.Split(strings.TrimRight(got, "\n"), "\n")
	b := strings.Split(strings.TrimRight(want, "\n"), "\n")
	if len(a) != len(b) {
		return false
	}
	for i := range a {
		if strings.TrimRight(a[i], " \t") != strings.TrimRight(b[i], " \t") {
			return false
		}
	}
	return true
}

func readGolden(t *testing.T, name string) string {
	t.Helper()
	golden, err := os.ReadFile(filepath.Join("testdata", "bench", name))
	if err != nil {
		t.Fatal(err)
	}
	return string(golden)
}

// TestBenchMatchesRecordedReport holds the port to the numbers the pre-port
// bench printed on the same fixture, recorded before it was deleted.
func TestBenchMatchesRecordedReport(t *testing.T) {
	r := ok(t, harness(t, benchDir(t), "", "bench", "--split", "2026-09-05", "--since", "2026-09-01", "--home", benchHome(t)), "bench")
	if want := readGolden(t, "report.golden"); !sameReport(r.stdout, want) {
		t.Fatalf("report differs from the recorded baseline:\n--- want\n%s\n--- got\n%s", want, r.stdout)
	}
}

func TestBenchRowsMatchRecordedRows(t *testing.T) {
	r := ok(t, harness(t, benchDir(t), "", "bench", "--split", "2026-09-05", "--since", "2026-09-01", "--home", benchHome(t), "--rows"), "bench --rows")
	if want := readGolden(t, "rows.golden"); r.stdout != want {
		t.Fatalf("rows differ from the recorded baseline:\n--- want\n%s\n--- got\n%s", want, r.stdout)
	}
}

func TestBenchEmptyHomeReportsNoSessions(t *testing.T) {
	r := ok(t, harness(t, benchDir(t), "", "bench", "--split", "2026-01-01", "--since", "2026-01-01", "--home", t.TempDir()), "bench on an empty home")
	if !strings.Contains(r.stdout, "no sessions found") {
		t.Fatalf("bench on an empty home printed %q", r.stdout)
	}
}

func TestBenchHelpExitsZero(t *testing.T) {
	if r := harness(t, benchDir(t), "", "bench", "--help"); r.code != 0 || !strings.Contains(r.stdout, "--split") {
		t.Fatalf("bench --help exited %d with stdout %q", r.code, r.stdout)
	}
}

func TestBenchReportsUnreadableTranscript(t *testing.T) {
	home := t.TempDir()
	project := filepath.Join(home, ".claude", "projects", "-tmp-x")
	if err := os.MkdirAll(project, 0o755); err != nil {
		t.Fatal(err)
	}
	// A directory named like a transcript stands in for an unreadable file.
	if err := os.Mkdir(filepath.Join(project, "broken.jsonl"), 0o755); err != nil {
		t.Fatal(err)
	}
	r := harness(t, benchDir(t), "", "bench", "--split", "2026-09-05", "--home", home)
	if r.code == 0 || r.stderr == "" {
		t.Fatalf("an unreadable transcript exited %d with stderr %q, want a reported failure", r.code, r.stderr)
	}
}

func TestBenchRefusesOutsideCheckout(t *testing.T) {
	r := harness(t, t.TempDir(), "", "bench", "--split", "2026-09-05", "--home", benchHome(t))
	if r.code == 0 || r.stderr == "" {
		t.Fatalf("outside a checkout exited %d with stderr %q, want a reported failure", r.code, r.stderr)
	}
}

func TestBenchUsageErrors(t *testing.T) {
	dir := benchDir(t)
	cases := [][]string{
		{"bench"},
		{"bench", "--home", benchHome(t)},
		{"bench", "--split", "not-a-date", "--home", benchHome(t)},
		{"bench", "--split", "2026-09-05", "--client", "codex", "--home", benchHome(t)},
		{"bench", "--split", "2026-09-05", "--bogus"},
	}
	for _, args := range cases {
		if r := harness(t, dir, "", args...); r.code == 0 {
			t.Errorf("%v exited 0, want a nonzero usage error", args)
		}
	}
}
