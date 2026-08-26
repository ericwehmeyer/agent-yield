METHOD. This paragraph is the only thing that differs between the two arms of
this experiment, and it is fixed.

You are the parent, and the parent does not read. You must NOT read, grep, glob
or otherwise open any file under `src/` yourself -- every byte of source must be
read by a dispatched agent, not by you. Dispatch agents with the `Agent` tool,
`subagent_type` `general-purpose`. Dispatch EXACTLY ONE agent and give it all 19
modules. That agent reads all 19 and returns the JSON fragment for all 19 and
nothing else; you assemble the final object from what comes back. The packing is
fixed by this paragraph and is not your call.

The brief you give that agent MUST carry the following instruction verbatim. It
is the ONLY thing this arm changes against `baton1`, and it is not your call
either:

    Do not stop at your first pass. When you have a mismatch list for all 19
    modules, go back over every module a second time: re-read its docstring
    sentence by sentence against the code you read, and ask of each sentence
    what would have to be true for it to hold. Add every mismatch the second
    pass finds. Report the list after the second pass, not the first.
