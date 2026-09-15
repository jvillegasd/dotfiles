package bench

import "testing"

// TestParseStamp covers every layout the parser accepts, so the fallbacks that
// match Python's datetime.fromisoformat are exercised rather than assumed.
func TestParseStamp(t *testing.T) {
	cases := []struct {
		name  string
		value any
		ok    bool
	}{
		{"rfc3339 fractional", "2026-09-01T10:00:00.000Z", true},
		{"rfc3339 offset", "2026-09-01T10:00:00+00:00", true},
		{"rfc3339 no fraction", "2026-09-01T10:00:00Z", true},
		{"naive with seconds", "2026-09-01T10:00:00", true},
		{"space separator", "2026-09-01 10:00:00", true},
		{"date only", "2026-09-01", true},
		{"not a stamp", "yesterday", false},
		{"empty", "", false},
		{"not a string", 12345, false},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			stamp, ok := parseStamp(c.value)
			if ok != c.ok {
				t.Fatalf("parseStamp(%v) ok = %v, want %v", c.value, ok, c.ok)
			}
			if ok && stamp.Year() != 2026 {
				t.Fatalf("parseStamp(%v) year = %d, want 2026", c.value, stamp.Year())
			}
		})
	}
}
