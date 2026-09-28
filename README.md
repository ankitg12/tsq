# tsq

A small CLI for **daily priorities in Logseq Markdown journals**. It reads and writes the first `- [[Goals]]` block of each dated journal file. The journal is the only task store: edits made in Logseq appear in `tsq`, and edits made with `tsq` appear in Logseq.

`tsq` complements [lsq](https://github.com/jrswab/lsq), the journal capture CLI. It does **not** call `lsq` or require the Logseq desktop app or HTTP API. It is not a long-term goal or project tracker.

## Install

Requires Python 3.10 or later. Install from GitHub with [uv](https://docs.astral.sh/uv/concepts/tools/):

```sh
uv tool install --python 3.12 git+https://github.com/ankitg12/tsq.git
```

Or, from a checkout, run `uv tool install .`. Both install the `tsq` command. The package has no runtime dependencies. To try it without installation, run `python3 tsq.py --help` from the checkout.

## Choose a journal directory

The default directory is `~/Logseq/journals`. For another Logseq graph, set the path to **its `journals` directory**:

```sh
export TSQ_JOURNALS_DIR="$HOME/notes/my-graph/journals"
```

Set it in your shell configuration if you use `tsq` often. Only Markdown journals named `YYYY_MM_DD.md` are supported. The CLI creates that directory and today's journal on the first write if they do not exist; check your path before adding an item. It does not read the `lsq` configuration.

## Use

```sh
tsq add -s now "Draft the review"
tsq add "Check the test results"      # defaults to LATER
tsq                                   # NOW, LATER, DONE in separate groups
tsq -s now                            # show only NOW; numbers stay stable
tsq 2                                 # inspect goal 2 and its child notes
tsq 2 set note "Case log saved"       # append a child note
tsq 2 now                           # mark active (also later or done)
tsq 2 set status done               # longer form still works
tsq done 1 "Review sent"              # mark done with a note
tsq top 2                              # move goal 2 to the top
tsq history 7                          # inspect the last seven days
tsq carry                              # copy open items from the last day that had any
```

`tsq carry` copies each open (not `DONE` or `CANCELED`) item, with its child notes, from the nearest earlier journal that has a `[[Goals]]` block (up to 30 days back), or from `--from YYYY-MM-DD`. It drops `id::` properties so that Logseq block ids stay unique, skips items whose title is already present, and leaves the source day unchanged. It is safe to run more than once.

`tsq --help` lists `mv`, `rm`, `undo`, and optional `due`, `blocked-on`, and `evidence` fields. Use `--date YYYY-MM-DD` to work on a different day. Item numbers refer to their positions in the journal, even when a status filter changes the display order.

A journal entry looks like this (tabs indent child blocks):

```markdown
- [[Goals]]
	- NOW Draft the review
		- Case log saved
	- LATER Check the test results
- 15:00 Notes from the meeting
```

On a write, `tsq` places completed entries after open ones and keeps other journal blocks. Keep your graph backed up, as with any tool that edits notes. The parser recognizes the first `- [[Goals]]` block and task items indented with a tab or two spaces; other layouts and Org-mode graphs are not supported.

## Develop

```sh
uv run --no-project --python 3.12 --with pytest pytest -q tests/test_tsq.py
```

MIT licensed; see [LICENSE](LICENSE).
