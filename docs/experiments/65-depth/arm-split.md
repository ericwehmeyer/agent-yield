METHOD. This paragraph is the only thing that differs between the two arms of
this experiment, and it is fixed.

You are the parent, and the parent does not read. You must NOT read, grep, glob
or otherwise open any file under `src/` or `tests/` yourself, and you must not
run the test commands yourself -- every byte of source and every test run must
be done by a dispatched agent. Dispatch agents with the `Agent` tool,
`subagent_type` `general-purpose`. Dispatch EXACTLY 23 AGENTS, one per slice,
and give each agent exactly one slice. Each agent does all three steps for its
one slice and returns the JSON fragment for that slice and nothing else; you
assemble the final object from what comes back. The packing is fixed by this
paragraph and is not your call.

Every agent you dispatch must be told, in its own prompt, that it may NOT
dispatch agents of its own. A packed agent that fans out is not a packed agent,
and a split agent that fans out is not one slice; either voids the run.
