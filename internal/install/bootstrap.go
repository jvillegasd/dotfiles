package install

import (
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"time"
)

const bootstrapUsage = `Usage: harness bootstrap [--no-backup]

Link the tracked configs, build harness into ~/.local/bin, and run a full harness install. The platform scripts run it through go run once their package step has installed Go.

  --no-backup  Delete configs that are in the way instead of renaming them to
               <path>.backup.<timestamp>, and apply the same choice to the
               harness install. Destructive and unrecoverable.
`

// Bootstrap runs `harness bootstrap` with its arguments and returns the exit code.
func Bootstrap(args []string, stdout, stderr io.Writer) (code int) {
	defer recoverFatal(stderr, &code)
	in := &installer{stdout: stdout, stderr: stderr}
	for _, arg := range args {
		switch arg {
		case "--no-backup":
			in.noBackup = true
		case "-h", "--help":
			fmt.Fprint(stdout, bootstrapUsage)
			return 0
		default:
			die("Unknown argument: %s", arg)
		}
	}
	checkout := findCheckout()
	in.setPaths(checkout)
	for _, link := range [][2]string{
		{filepath.Join(checkout, "nvim"), filepath.Join(in.config, "nvim")},
		{filepath.Join(checkout, "ghostty"), filepath.Join(in.config, "ghostty")},
		{filepath.Join(checkout, "git", "gitconfig"), filepath.Join(in.home, ".gitconfig")},
		{filepath.Join(checkout, "git", "ignore"), filepath.Join(in.config, "git", "ignore")},
		{filepath.Join(checkout, "worktrunk", "config.toml"), filepath.Join(in.config, "worktrunk", "config.toml")},
	} {
		in.linkConfig(link[0], link[1])
	}

	bin := filepath.Join(in.home, ".local", "bin", "harness")
	in.log("Building %s", bin)
	must(os.MkdirAll(filepath.Dir(bin), 0o755))
	build := exec.Command("go", "build", "-o", bin, "./cmd/harness")
	build.Dir, build.Stdout, build.Stderr = checkout, stdout, stderr
	if err := build.Run(); err != nil {
		die("Building harness failed: %v", err)
	}
	in.install()
	return 0
}

// linkConfig links one tracked config into place. A link already there is left alone and another link is replaced; anything else is renamed to <path>.backup.<timestamp> beside it, or deleted under --no-backup.
func (in *installer) linkConfig(source, dest string) {
	if _, err := os.Stat(source); err != nil {
		die("Missing config source: %s", source)
	}
	if isLink(dest) {
		current := readlink(dest)
		if current == source {
			in.log("Symlink already in place: %s -> %s", dest, source)
			return
		}
		in.log("Replacing existing symlink: %s (was -> %s)", dest, current)
		must(os.Remove(dest))
	} else if exists(dest) {
		if in.noBackup {
			in.log("Removing existing %s", dest)
			must(os.RemoveAll(dest))
		} else {
			backup := dest + ".backup." + time.Now().Format("20060102-150405")
			in.log("Backing up existing %s to %s", dest, backup)
			must(os.Rename(dest, backup))
		}
	}
	must(os.MkdirAll(filepath.Dir(dest), 0o755))
	in.log("Linking %s -> %s", source, dest)
	must(os.Symlink(source, dest))
}
