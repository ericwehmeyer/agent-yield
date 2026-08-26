METHOD. This paragraph is the only thing that differs between the two arms of
this experiment, and it is fixed.

You are the parent, and the parent does not read. You must NOT read, grep, glob
or otherwise open any file under `src/` yourself -- every byte of source must be
read by a dispatched agent, not by you. Dispatch agents with the `Agent` tool,
`subagent_type` `general-purpose`, and give each agent a subset of the module
list. Each agent reads its own modules and returns the JSON fragment for exactly
those modules and nothing else; you assemble the final object from what comes
back. How many agents you dispatch, and how you pack the modules across them, is
your call.
