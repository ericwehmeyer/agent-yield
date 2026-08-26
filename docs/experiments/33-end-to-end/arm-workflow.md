METHOD. This paragraph is the only thing that differs between the two arms of
this experiment, and it is fixed.

You are the parent, and the parent does not read. You must NOT read, grep, glob
or otherwise open any file under `src/` yourself -- every byte of source must be
read by a dispatched agent, not by you.

Dispatch with the `Workflow` tool, NOT the `Agent` tool. Run EXACTLY ONE
workflow. That workflow must spawn EXACTLY ONE agent and give it all 19 modules.
That agent reads all 19 and returns the JSON fragment for all 19 and nothing
else; you assemble the final object from what the workflow returns. The packing
is fixed by this paragraph and is not your call.

The brief the workflow's agent is given MUST carry the following instruction
verbatim. It is unchanged from `baton1v`, and it is not your call either:

    Do not stop at your first pass. When you have a mismatch list for all 19
    modules, go back over every module a second time: re-read its docstring
    sentence by sentence against the code you read, and ask of each sentence
    what would have to be true for it to hold. Add every mismatch the second
    pass finds. Report the list after the second pass, not the first.

---

NOT PART OF THE ARM -- what this arm varies, and what it must not.

This is comparison 2 of the skinny-parent plan, slice S5, and #39's actual
question: *who runs the loop*. Against `baton1v` the ONLY variable is the engine.
Same task, same tail, same one-agent packing, same worker brief byte for byte.
If the briefs or the slicing move too, the result is uninterpretable -- the
confound NEXT.md warns about.

THE FLAG, and why it does not break run.sh's identical-flags rule. This arm needs
`--allowedTools Workflow`: without it the launch is BLOCKED in a non-interactive
`claude -p` session -- "Review dynamic workflow before running" -- and no agent
spawns, so the arm would record a parent that dispatched nothing (#85, finding 1).
run.sh's rule exists because a flag difference "would change the tool schema and
so the token count". This one does not, and that is measured rather than assumed:
`claude -p "Reply with exactly: OK"` under COMMON, one flag apart, no work done in
either, bills 21,615 tokens of context BOTH WAYS -- identical to the token, with
only the cache write/read split moving because the second run hit the cache the
first warmed. `Workflow` is in the schema whether or not it is permitted; the
grant changes a permission decision and nothing that is billed.

THE MEASUREMENT DEPENDS ON #85. Before that fix `measure.py` read agent
transcripts only from `tasks/*.output`, and for a Workflow run that file is a
JSON summary rather than a transcript -- `load_records` returned zero calls
without error, so this arm would have reported `agent_tokens 0` and won on a
silence. Do not run this arm against a `measure.py` that predates a8cc42a.
