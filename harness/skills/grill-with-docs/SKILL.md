---
name: grill-with-docs
description: A grilling interview that writes the glossary and the ADRs as the decisions settle, so discovery leaves a durable record instead of dying with the conversation.
disable-model-invocation: true
metadata:
  opencode/autoinvoke: "false"
---

# Grill With Docs

Load and follow `grilling` and `domain-modeling` together. The interview decides; the domain model records what was decided, while the session that decided it is still live.

This is not a second interview protocol. The interview is `grilling`, unchanged, including its choice of interactive or self-grill mode. What this adds is the writing: a decision that survives the interview lands in `CONTEXT.md` or in an ADR before the next question, rather than at the end, because the end is where a long session runs out of context.

## When this instead of bare `grilling`

Use this when the conclusions have to outlive the conversation: a greenfield project with no `CONTEXT.md` yet, a design that will take more than one session to settle, or any thread whose decisions a later session will need and cannot reconstruct from the code.

Use bare `grilling` when the output is a decision you will act on immediately, or when the plan is small enough that the pull request is the whole record. Writing an ADR for a decision that will be visible in the diff an hour later is ceremony.

## What gets written

`domain-modeling` owns the formats and creates both files lazily, only once there is something to record: `CONTEXT.md` when the first term is resolved, `docs/adr/` when the first decision needs one. An interview that settles nothing writes nothing, which is the correct outcome rather than a failure.

Record the decision and its reason. The rejected alternatives belong in an ADR only when they are worth remembering.
