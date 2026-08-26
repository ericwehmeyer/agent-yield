METHOD. This paragraph is the only thing that differs between the two arms of
this experiment, and it is fixed.

You are the parent, and the parent does not read. You must NOT read, grep, glob
or otherwise open any file under `src/` yourself -- every byte of source must be
read by a dispatched agent, not by you. Dispatch with the `Agent` tool,
`subagent_type` `general-purpose`.

Dispatch EXACTLY ONE agent, and that agent is an INTERMEDIARY, not a reader. It
must not read any file under `src/` either. Its whole job is to dispatch exactly
one worker agent -- `Agent` tool, `subagent_type` `general-purpose` -- give that
worker all 19 modules and the brief below, and relay back what the worker
returns. The intermediary must return the worker's JSON fragment VERBATIM,
unchanged and unsummarised, and nothing else. You assemble the final object from
what comes back. The packing is fixed by this paragraph and is not your call.

The brief the WORKER is given MUST carry the following instruction verbatim. It
is unchanged from `baton1v`, and it is not your call either:

    Do not stop at your first pass. When you have a mismatch list for all 19
    modules, go back over every module a second time: re-read its docstring
    sentence by sentence against the code you read, and ask of each sentence
    what would have to be true for it to hold. Add every mismatch the second
    pass finds. Report the list after the second pass, not the first.

---

NOT PART OF THE ARM -- why the relay is verbatim rather than distilling.

The intermediary an operator actually imagines DISTILLS: it holds the fleet's
context and hands the main session a thin answer. This arm deliberately does not
do that, and the reason is that a verbatim relay measures the FLOOR. It adds one
agent instantiation and one hop and changes nothing else, so whatever it costs is
the least an interposed layer can cost on this task. A distilling intermediary
does strictly more work than a relaying one -- it reads the worker's report and
writes a summary -- so it cannot come in cheaper than this floor. If the floor
is already above 1.0x, the distilling version is answered without running it.

Verbatim also holds QUALITY fixed. The worker's brief is `baton1v`'s, byte for
byte, so the mismatch list is produced by an identical instrument and the defect
score stays comparable. A distilling relay would change what the parent sees, and
a cheaper arm that found fewer defects would be VOID rather than a result -- the
standing rule from #18 Part E.
