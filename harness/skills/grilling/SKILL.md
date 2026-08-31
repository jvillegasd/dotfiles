---
name: grilling
description: Attack the load-bearing assumptions in a plan before they get expensive, interactively or by self-grilling.
disable-model-invocation: true
metadata:
  opencode/autoinvoke: "false"
---

# Grilling

Cheap to change a plan, expensive to change a merged diff. This closes that gap by attacking the plan while it is still words. Grilling is not a checklist and not a summary; it is an attempt to break the thing.

Before asking anything, in either mode, find what the plan depends on being true and attack that, not the surface. A load-bearing assumption is one where being wrong changes the approach, the scope, or whether the work happens at all. Rank by consequence and start with the worst one.

## Mode: interactive

Human-driven, and the default when this skill is invoked directly.

Interview the user relentlessly until you reach a shared understanding. Map this as a **design tree**: every decision branches into the decisions that hang off it.

Work the tree in **rounds**. The **frontier** is every decision whose prerequisites are already settled: the questions you can ask _now_ without guessing at answers you haven't heard yet. Ask the whole frontier in one round: number each question and give your recommended answer. Then wait for the user's answers before the next round.

Format a round like so:

```
❓ **Q1** - **<question title>**: <question body, might be multiple paragraphs, including multiple choices>

➡️ <your recommended answer>

---

❓ **Q2** - **<question title>**: <question body, might be multiple paragraphs, including multiple choices>

➡️ <your recommended answer>
```

Each round the user answers reshapes the tree: settled decisions push the frontier outward and unblock questions that depended on them. Recompute the frontier and ask the next round. A question whose answer depends on another question still open in this round belongs to a _later_ round, not this one.

Finding _facts_ is your job, never the user's. When a frontier question needs a fact from the environment (filesystem, tools, etc.), dispatch a sub-agent to find it; don't ask the user for anything you could look up yourself. Don't block on it: a running exploration is an unsettled prerequisite, so only the questions downstream of it wait for the sub-agent to report; ask the rest of the frontier now. The _decisions_ are the user's: put each to them and wait.

The session is done when the frontier is empty: every branch of the design tree visited, nothing left silently assumed. Do not act on it until the user confirms you have reached a shared understanding.

Push where an answer cracks. When one is vague, hedged, or changes the subject, follow it instead of moving on: "it depends" means you found something. Search the repository rather than objecting in the abstract, because "does anything here already do this?" beats a logical argument. Never accept a restatement of the plan as an answer.

## Mode: self-grill

No human in the loop. Use this when a workflow needs its own approach pressure-tested and serial interactive grilling would be the bottleneck: `/yolo` on a load-bearing ambiguity that survives a repository search, and `/triage` before it escalates.

1. **List the assumptions** the approach depends on, ranked by consequence.
2. **Resolve what you can**, in this order: search the repository for precedent; check history for whether this was tried before; load and follow `evidence` for any claim about runtime behavior, impact, or frequency. Most open questions die here, because they were answerable and nobody looked.
3. **Kill the plan if it deserves it.** If evidence refutes the premise, say so and stop. That is a success, not a failure.
4. **Present only the survivors**, in one batch, each in the policy's question format: the decision, what you already checked and what it ruled out, the options with their consequences, your default, and the cost if the default is wrong. Where three or fewer read-only actions would settle a question, take them instead of asking it.

A self-grill that produces a long question list skipped step 2.
