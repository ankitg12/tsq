#!/usr/bin/env python3
"""tsq — a daily task queue in the Logseq journal, one task per line, in priority order.

The tasks are the first block of the journal page, so Logseq shows them first:

    - [[Tasks]]
        - LATER draft proposal           <- priority 1
        - NOW test an import
    - 11:15 other journal blocks ...

Reorder in Logseq with Alt+Shift+Up/Down (or drag), or here with `top`/`mv`.
Every day's tasks sit under a link to the [[Tasks]] page, so that page lists them all.
The journal file is the source of truth; no Logseq server or lsq executable is needed.

Usage (set TSQ_JOURNALS_DIR for a graph outside ~/Logseq/journals):
  tsq [--date YYYY-MM-DD]               list NOW, LATER, then DONE tasks
  tsq --status now|later|done           filter the list by status
  tsq N [--date YYYY-MM-DD]             show one task with its notes
  tsq add [-s now|later|done] "text"    append a task (default LATER)
  tsq N now|later|done ["note"]         change status, optionally with a note
  tsq N note "text"                     append a note (also: add note, comment)
  tsq N set text "text"                 edit the task title
  tsq N set status now                  set LATER, NOW, or DONE
  tsq N set note "text"                 append a note to the task
  tsq N set evidence "proof"            set optional completion evidence
  tsq N set due YYYY-MM-DD              set optional due date
  tsq N set blocked-on "reason"         set optional blocker
  tsq top N                             move task N to priority 1
  tsq mv N M                            move task N to position M
  tsq rm N                              remove task N
  tsq done N ["note"]                   mark DONE and optionally add a child note
  tsq undo N                            mark task N open again
  tsq carry [--from YYYY-MM-DD]         copy open tasks from the last day that
                                        had tasks (or --from) into today
  tsq history [N]                       tasks for the last N days (default 7)

Goals: `goals` (or `tsq --goals`) runs the same commands on a `- [[Goals]]` block,
which sits above Tasks. Goals are the day's few outcomes (a note warns above 3);
tasks are the steps. Old `goal:: a; b` page properties are read as goals.
Stdlib only: the layout is fixed and small, so no Logseq parser is needed.
"""

import argparse
import datetime
from dataclasses import dataclass
import os
import re
import sys
from pathlib import Path

JOURNALS_DIR = Path(
    os.environ.get("TSQ_JOURNALS_DIR", str(Path.home() / "Logseq" / "journals"))
).expanduser()
# Some older journals written on Windows are not valid UTF-8; surrogateescape
# round-trips their bytes unchanged instead of failing or corrupting them.
ENC = {"encoding": "utf-8", "errors": "surrogateescape"}


# Two blocks share this engine: [[Goals]] (the day's few outcomes, first on the
# page) and [[Tasks]] (the steps). Run as `goals` (or `tsq --goals`) for Goals.
@dataclass(frozen=True)
class Block:
    """One kind of daily list: which journal block it lives in and how it behaves.
    Every function that reads or writes a page takes a Block; there is no mode state."""

    name: str  # Logseq page the header links to, e.g. "Tasks"
    prog: str  # command name shown in help
    rank: int  # page order: lower ranks sit higher on the page
    soft_limit: int | None = None  # warn (never refuse) above this many open items
    legacy_prop: str | None = None  # old `prop:: a; b` page-property form

    @property
    def header(self) -> str:
        return f"- [[{self.name}]]"

    def matches(self, line: str) -> bool:
        return line.rstrip() in (self.header, f"- {self.name}")


GOALS = Block("Goals", "goals", rank=0, soft_limit=3, legacy_prop="goal")
TASKS = Block("Tasks", "tsq", rank=1)
KINDS = (GOALS, TASKS)


def block_of(line: str) -> Block | None:
    return next((b for b in KINDS if b.matches(line)), None)


ITEM_RE = re.compile(r"^(\t| {2})- (.*)$")
# Logseq task markers; goals are native tasks, so the checkbox works in Logseq too.
# New goals use Logseq's LATER task marker; other workflows remain readable.
MARKER_RE = re.compile(r"^(TODO|LATER|NOW|DOING|DONE|CANCELED|CANCELLED) ")
OPEN = "LATER"
SET_FIELDS = ("text", "status", "note", "evidence", "due", "blocked-on")
PROP_RE = re.compile(r"^([A-Za-z][\w-]*):: ?(.*)$")
# Closed markers are not carried to the next day.
CLOSED = ("DONE ", "CANCELED ", "CANCELLED ")
# A block id must stay unique in the graph, so a carried copy drops it.
ID_PROP_RE = re.compile(r"^\s*id:: ")
CARRY_LOOKBACK_DAYS = 30


def journal_path(date_str: str | None = None) -> Path:
    d = datetime.date.fromisoformat(date_str) if date_str else datetime.date.today()
    return JOURNALS_DIR / (d.strftime("%Y_%m_%d") + ".md")


class Page:
    """A journal page split into: page properties, goal items, other lines.
    Each goal item keeps its raw lines (Logseq may add `id::` or child lines)."""

    def __init__(self, content: str, kind: Block = TASKS):
        self.kind = kind
        lines = content.splitlines()
        i = 0
        self.props: list[str] = []
        while i < len(lines) and PROP_RE.match(lines[i]):
            self.props.append(lines[i])
            i += 1
        while i < len(lines) and not lines[i].strip():
            i += 1
        rest = lines[i:]
        self.items: list[list[str]] = []
        self.parent_extra: list[str] = []  # e.g. `collapsed:: true` on the header
        # 2026-09-25 page-property form: goal:: a; b (these are goals)
        for p in list(self.props):
            m = PROP_RE.match(p)
            if m and m.group(1) == kind.legacy_prop:
                self.items += [[f"\t- {g}"] for g in m.group(2).split("; ") if g]
                self.props.remove(p)
        start = next((n for n, l in enumerate(rest) if kind.matches(l)), None)
        if start is not None:
            n = start + 1
            while n < len(rest) and (
                rest[n].startswith(("\t", " ")) or not rest[n].strip()
            ):
                if ITEM_RE.match(rest[n]):
                    self.items.append([rest[n]])
                elif rest[n].strip():
                    (self.items[-1] if self.items else self.parent_extra).append(
                        rest[n]
                    )
                n += 1
            rest = rest[:start] + rest[n:]
        self.body = rest

    @property
    def goals(self) -> list[str]:
        return [MARKER_RE.sub("", self.raw(i)) for i in range(len(self.items))]

    def raw(self, i: int) -> str:
        return ITEM_RE.match(self.items[i][0]).group(2)

    def done(self, i: int) -> bool:
        return self.raw(i).startswith("DONE ")

    def set_marker(self, i: int, marker: str) -> None:
        text = MARKER_RE.sub("", self.raw(i))
        self.items[i][0] = f"\t- {marker} {text}"

    def render(self) -> str:
        out = list(self.props)
        if out:
            out.append("")
        body = list(self.body)
        # Blocks of a lower rank (Goals above Tasks) stay above this one.
        n = 0
        while (
            n < len(body)
            and (other := block_of(body[n]))
            and other.rank < self.kind.rank
        ):
            n += 1
            while n < len(body) and body[n].startswith(("\t", " ")):
                n += 1
        out += body[:n]
        if self.items:
            out += [self.kind.header] + self.parent_extra
            out += [l for it in self.items for l in it]
        out += body[n:]
        return "\n".join(out) + "\n"


def read_page(path: Path, kind: Block) -> Page:
    return Page(path.read_text(**ENC) if path.exists() else "", kind)


def save(path: Path, page: Page) -> None:
    # No reordering here: a task's number is its position, and it must not
    # change when the task's status changes. The list view groups by status.
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(page.render(), **ENC)


def carry_source(target: datetime.date, kind: Block) -> datetime.date | None:
    """The nearest day before target whose journal has at least one goal."""
    for back in range(1, CARRY_LOOKBACK_DAYS + 1):
        d = target - datetime.timedelta(days=back)
        path = journal_path(d.isoformat())
        if read_page(path, kind).items:
            return d
    return None


def carry(page: Page, source: Page) -> tuple[int, int]:
    """Append source's open goals (with notes, without block ids) to page.
    Goals whose title is already on the page are skipped, so carry is idempotent."""
    present = set(page.goals)
    carried = skipped = 0
    for i, item in enumerate(source.items):
        if source.raw(i).startswith(CLOSED):
            continue
        if source.goals[i] in present:
            skipped += 1
            continue
        page.items.append([item[0]] + [l for l in item[1:] if not ID_PROP_RE.match(l)])
        present.add(source.goals[i])
        carried += 1
    return carried, skipped


def index(page: Page, n: int) -> int:
    if not 1 <= n <= len(page.items):
        print(f"NO_SUCH_TASK: {n} (have {len(page.items)})", file=sys.stderr)
        sys.exit(2)
    return n - 1


def shown(s: str) -> str:
    """Display form: undecodable bytes (kept intact in the file) print as U+FFFD."""
    return s.encode("utf-8", "surrogateescape").decode("utf-8", "replace")


def goal_status(page: Page, i: int) -> str:
    if page.done(i):
        return "DONE"
    return "NOW" if page.raw(i).startswith(("NOW ", "DOING ")) else "LATER"


def print_goals(page: Page, status: str | None = None) -> None:
    # Group the view, not the journal: printed numbers still address raw blocks.
    printed = False
    for marker in ("NOW", "LATER", "DONE"):
        if status is not None and marker != status:
            continue
        numbers = [
            n
            for n in range(1, len(page.items) + 1)
            if goal_status(page, n - 1) == marker
        ]
        if not numbers:
            continue
        if status is None:
            if printed:
                print()
            print(f"{marker}:")
        for n in numbers:
            print_goal(page, n, show_status=False)
        printed = True


def print_goal(page: Page, n: int, show_status: bool = True) -> None:
    g = page.goals[n - 1]
    active = " [NOW]" if show_status and page.raw(n - 1).startswith("NOW ") else ""
    print(f"{n}. [{'x' if page.done(n - 1) else ' '}] {shown(g)}{active}")
    for line in page.items[n - 1][1:]:
        if line.startswith("\t\t- "):
            print(f"   {shown(line[4:])}")
        elif line.startswith("\t\t"):
            prop = PROP_RE.match(line.strip())
            if prop and prop.group(1) in ("evidence", "due", "blocked-on"):
                print(f"   {prop.group(1)}: {shown(prop.group(2))}")


def split_opts(args: list[str]) -> tuple[list[str], list[str]]:
    """Separate free words from `--date X` so a trailing note can hold any words."""
    words: list[str] = []
    opts: list[str] = []
    i = 0
    while i < len(args):
        if args[i] == "--date" and i + 1 < len(args):
            opts += args[i : i + 2]
            i += 2
        else:
            words.append(args[i])
            i += 1
    return words, opts


def goals_main() -> int:
    return main(GOALS)


def main(kind: Block | None = None) -> int:
    argv = sys.argv[1:]
    if kind is None:
        # `goals` may be a symlink to this file; `tsq --goals` is the same.
        goals = Path(sys.argv[0]).name.startswith("goals") or "--goals" in argv
        kind = GOALS if goals else TASKS
    argv = [a for a in argv if a != "--goals"]
    p = argparse.ArgumentParser(
        prog=kind.prog,
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--date", metavar="YYYY-MM-DD", help="Journal date (default: today)")
    p.add_argument(
        "-s",
        "--status",
        type=str.upper,
        choices=("NOW", "LATER", "DONE"),
        help="Show only tasks in this status (list only)",
    )
    dp = argparse.ArgumentParser(add_help=False)  # --date also after the subcommand
    dp.add_argument("--date", metavar="YYYY-MM-DD", default=argparse.SUPPRESS)
    sub = p.add_subparsers(dest="cmd")
    g = sub.add_parser("get", parents=[dp], help="Show one task with its notes")
    g.add_argument("n", type=int, help="Task number")
    a = sub.add_parser("add", parents=[dp], help="Append a task")
    a.add_argument(
        "-s",
        "--status",
        dest="add_status",
        type=str.upper,
        choices=("NOW", "LATER", "DONE"),
        default=OPEN,
        help="Initial status (default: LATER)",
    )
    a.add_argument("text", nargs="+")
    s = sub.add_parser("set", parents=[dp], help="Set a task field or append a note")
    s.add_argument("n", type=int)
    s.add_argument("field", choices=SET_FIELDS)
    s.add_argument("value", nargs="+")
    t = sub.add_parser("top", parents=[dp], help="Move task N to priority 1")
    t.add_argument("n", type=int)
    m = sub.add_parser("mv", parents=[dp], help="Move task N to position M")
    m.add_argument("n", type=int)
    m.add_argument("to", type=int)
    r = sub.add_parser("rm", parents=[dp], help="Remove task N")
    r.add_argument("n", type=int)
    for name, hlp in (("done", "Mark task N DONE"), ("undo", "Mark task N open again")):
        s = sub.add_parser(name, parents=[dp], help=hlp)
        s.add_argument("n", type=int)
        if name == "done":
            s.add_argument("note", nargs="*", help="Optional completion note")
    c = sub.add_parser(
        "carry",
        parents=[dp],
        help="Copy open tasks from the last day that had tasks into this day",
    )
    c.add_argument(
        "--from",
        dest="source",
        metavar="YYYY-MM-DD",
        help=f"Source day (default: nearest earlier day with tasks, "
        f"up to {CARRY_LOOKBACK_DAYS} days back)",
    )
    h = sub.add_parser("history", help="Tasks for the last N days")
    h.add_argument("days", nargs="?", type=int, default=7)
    p.add_argument(
        "--goals",
        action="store_true",
        help="Use the [[Goals]] block (same as running `goals`)",
    )
    argv = ["-h" if a == "-?" else a for a in argv]
    offset = 2 if len(argv) >= 2 and argv[0] == "--date" else 0
    # A note given with a status change: `tsq N now "why"`.
    status_note: str | None = None
    if len(argv) > offset and re.fullmatch(r"[0-9]+", argv[offset]):
        n, rest = argv[offset], argv[offset + 1 :]
        if rest and rest[0] in ("--help", "-h"):
            help_parser = argparse.ArgumentParser(
                prog=f"tsq {n}",
                description="Show this task or change one of its fields.",
                epilog=(
                    f"tsq {n} now|later|done  change status directly\n"
                    f"tsq {n} set FIELD VALUE  change a field (note appends)\n"
                    f"FIELD: {', '.join(SET_FIELDS)}\n"
                    "status values: LATER, NOW, DONE (case-insensitive)"
                ),
                formatter_class=argparse.RawDescriptionHelpFormatter,
            )
            help_parser.add_argument(
                "--date", metavar="YYYY-MM-DD", help="Journal date"
            )
            help_parser.print_help()
            return 0
        if not rest or rest[0] == "--date":
            argv = argv[:offset] + ["get", n] + rest
        elif rest[0].upper() in ("NOW", "LATER", "DONE"):
            words, opts = split_opts(rest[1:])
            if rest[0].upper() == "DONE":
                argv = argv[:offset] + ["done", n] + words + opts
            else:
                argv = argv[:offset] + ["set", n, "status", rest[0]] + opts
                status_note = " ".join(words).strip() or None
        elif rest[0] in ("note", "add", "comment"):
            # `tsq N note x`, `tsq N add note x`, `tsq N comment x`
            body = rest[1:]
            if rest[0] == "add" and body and body[0] in ("note", "comment"):
                body = body[1:]
            argv = argv[:offset] + ["set", n, "note"] + body
        elif rest[0] == "set":
            if len(rest) > 1 and rest[1] in ("--help", "-h"):
                set_help = argparse.ArgumentParser(
                    prog=f"tsq {n} set",
                    description="Change a task field; note appends a child note.",
                    epilog="status values: LATER, NOW, DONE (case-insensitive)",
                )
                set_help.add_argument("field", choices=SET_FIELDS)
                set_help.add_argument("value", nargs="+")
                set_help.add_argument(
                    "--date", metavar="YYYY-MM-DD", help="Journal date"
                )
                set_help.print_help()
                return 0
            argv = argv[:offset] + ["set", n] + rest[1:]
    args = p.parse_args(argv)
    if args.status is not None and args.cmd is not None:
        p.error("--status filters only the task list")

    if args.cmd == "history":
        today = datetime.date.today()
        for i in range(args.days - 1, -1, -1):
            d = today - datetime.timedelta(days=i)
            path = journal_path(d.isoformat())
            pg = read_page(path, kind)
            marked = [("✓ " if pg.done(k) else "") + g for k, g in enumerate(pg.goals)]
            score = (
                f"{sum(map(pg.done, range(len(marked))))}/{len(marked)}  "
                if marked
                else ""
            )
            print(
                f"{d.isoformat()} {d.strftime('%a')}  {score}{shown(' | '.join(marked)) or '—'}"
            )
        return 0

    if args.cmd in (None, "get"):
        path = journal_path(args.date)
        if not path.exists():
            print("FILE_NOT_FOUND")
            return 1
        page = read_page(path, kind)
        if not page.items:
            print(f"NO_{kind.name.upper()}")
            return 1
        if args.cmd == "get":
            print_goal(page, index(page, args.n) + 1)
        else:
            print_goals(page, args.status)
        return 0

    path = journal_path(args.date)
    page = read_page(path, kind)
    if args.cmd == "carry":
        target = (
            datetime.date.fromisoformat(args.date)
            if args.date
            else datetime.date.today()
        )
        source = (
            datetime.date.fromisoformat(args.source)
            if args.source
            else carry_source(target, kind)
        )
        if source is None:
            print(
                f"NO_SOURCE: no tasks in the {CARRY_LOOKBACK_DAYS} days before {target}"
            )
            return 1
        if source == target:
            print("BAD_SOURCE: source and target are the same day.", file=sys.stderr)
            return 2
        src_path = journal_path(source.isoformat())
        src = read_page(src_path, kind)
        carried, skipped = carry(page, src)
        note = f", {skipped} already present" if skipped else ""
        print(f"CARRIED {carried} from {source}{note}")
        if not carried:
            return 0
        save(path, page)
        print_goals(page)
        return 0
    if args.cmd == "add":
        text = " ".join(args.text).strip()
        if not text or "\n" in text:
            print("BAD_TASK: one non-empty line.", file=sys.stderr)
            return 2
        page.items.append([f"\t- {args.add_status} {text}"])
        open_n = sum(not page.done(i) for i in range(len(page.items)))
        if kind.soft_limit and open_n > kind.soft_limit:
            print(
                f"NOTE: {open_n} open goals; a day holds about {kind.soft_limit}. "
                "Is one of them a task (`tsq add`)?",
                file=sys.stderr,
            )
    elif args.cmd == "top":
        page.items.insert(0, page.items.pop(index(page, args.n)))
    elif args.cmd == "mv":
        item = page.items.pop(index(page, args.n))
        page.items.insert(max(0, min(args.to - 1, len(page.items))), item)
    elif args.cmd == "rm":
        page.items.pop(index(page, args.n))
    elif args.cmd == "set":
        value = " ".join(args.value).strip()
        if not value or "\n" in value or "\r" in value:
            print("BAD_VALUE: one non-empty line.", file=sys.stderr)
            return 2
        i = index(page, args.n)
        if args.field == "due":
            try:
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                    raise ValueError(value)
                datetime.date.fromisoformat(value)
            except ValueError:
                print("BAD_DUE: use YYYY-MM-DD.", file=sys.stderr)
                return 2
        if args.field == "status":
            value = value.upper()
            if value not in ("LATER", "NOW", "DONE"):
                print("BAD_STATUS: use LATER, NOW, or DONE.", file=sys.stderr)
                return 2
            page.set_marker(i, value)
            if status_note:
                if "\n" in status_note or "\r" in status_note:
                    print("BAD_NOTE: one line only.", file=sys.stderr)
                    return 2
                page.items[i].append(f"\t\t- {status_note}")
        elif args.field == "note":
            page.items[i].append(f"\t\t- {value}")
        elif args.field == "text":
            marker = MARKER_RE.match(page.raw(i))
            page.items[i][0] = f"\t- {marker.group(0) if marker else ''}{value}"
        else:
            prefix = f"\t\t{args.field}::"
            line = f"{prefix} {value}"
            existing = next(
                (
                    j
                    for j, raw in enumerate(page.items[i])
                    if raw.startswith(prefix + " ")
                ),
                None,
            )
            if existing is None:
                page.items[i].append(line)
            else:
                page.items[i][existing] = line
    elif args.cmd == "done":
        note = " ".join(args.note).strip()
        if args.note and (not note or "\n" in note or "\r" in note):
            print("BAD_NOTE: one non-empty line.", file=sys.stderr)
            return 2
        i = index(page, args.n)
        page.set_marker(i, "DONE")
        if note:
            page.items[i].append(f"\t\t- {note}")
        # Keep the block in place: the view groups by status, and task
        # numbers must not change when a task is closed.
    elif args.cmd == "undo":
        page.set_marker(index(page, args.n), OPEN)
    save(path, page)
    print_goals(page)
    return 0


if __name__ == "__main__":
    sys.exit(main())
