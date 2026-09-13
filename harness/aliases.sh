# Harness AI shell aliases. Sourced from ~/.zshrc by harness/install.sh.
#
# Yolo mode: no approval prompts, for a client running inside a worktree or a
# container you are willing to lose. The policy's escalation contract is what
# keeps this honest; the client's prompt is not.

alias ccyolo='claude --dangerously-skip-permissions'

# OpenCode has no bypass flag. Permissions are configuration, and
# OPENCODE_PERMISSION overrides them for one run.
alias ocyolo='OPENCODE_PERMISSION='"'"'{"edit":"allow","bash":"allow","webfetch":"allow"}'"'"' opencode'
