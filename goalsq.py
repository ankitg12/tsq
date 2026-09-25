#!/usr/bin/env python3
"""Today's goals in the Logseq journal — one goal per line, ordered by priority.

The goals are the first block of the journal page, so Logseq shows them first:

    - [[Goals]]
        - LATER draft proposal           <- priority 1
        - NOW test an import
    - 11:15 other journal blocks ...

Reorder in Logseq with Alt+Shift+Up/Down (or drag), or here with `top`/`mv`.
Every day's goals link to the [[Goals]] page, so that page lists them all.
The journal file is the source of truth; no Logseq server or lsq executable is needed.

Usage (set GOALSQ_JOURNALS_DIR for a graph outside ~/Logseq/journals):
  goalsq [--date YYYY-MM-DD]                  list NOW, LATER, then DONE goals
  goalsq --status now|later|done              filter the list by status
  goalsq N [--date YYYY-MM-DD]                show one goal with its notes
  goalsq add [-s now|later|done] "text"       append a goal (default LATER)
  goalsq N set text "text"                    edit the goal title
  goalsq N set status now                     set LATER, NOW, or DONE
  goalsq N set note "text"                    append a note to the goal
  goalsq N set evidence "proof"               set optional completion evidence
  goalsq N set due YYYY-MM-DD                 set optional due date
  goalsq N set blocked-on "reason"            set optional blocker
  goalsq top N                                 move goal N to priority 1
  goalsq mv N M                                move goal N to position M
  goalsq rm N                                  remove goal N
  goalsq done N ["note"]                        mark DONE and optionally add a child note
  goalsq undo N                                 mark goal N open again
  goalsq history [N]                           goals for the last N days (default 7)

Also reads legacy `goal:: a; b` page properties and `- Goals` blocks;
any write converts them to the format above.
Stdlib only: the layout is fixed and small, so no Logseq parser is needed.
"""

import argparse
import datetime
import os
import re
import sys
from pathlib import Path

JOURNALS_DIR = Path(
    os.environ.get("GOALSQ_JOURNALS_DIR", str(Path.home() / "Logseq" / "journals"))
).expanduser()
# Some older journals written on Windows are not valid UTF-8; surrogateescape
# round-trips their bytes unchanged instead of failing or corrupting them.
ENC = {"encoding": "utf-8", "errors": "surrogateescape"}
HEADER = "- [[Goals]]"
HEADER_RE = re.compile(r"^- (\[\[Goals\]\]|Goals)\s*$")
ITEM_RE = re.compile(r"^(\t| {2})- (.*)$")
# Logseq task markers; goals are native tasks, so the checkbox works in Logseq too.
# New goals use Logseq's LATER task marker; other workflows remain readable.
MARKER_RE = re.compile(r"^(TODO|LATER|NOW|DOING|DONE|CANCELED|CANCELLED) ")
OPEN = "LATER"
SET_FIELDS = ("text", "status", "note", "evidence", "due", "blocked-on")
PROP_RE = re.compile(r"^([A-Za-z][\w-]*):: ?(.*)$")


def journal_path(date_str: str | None = None) -> Path:
    d = datetime.date.fromisoformat(date_str) if date_str else datetime.date.today()
    return JOURNALS_DIR / (d.strftime("%Y_%m_%d") + ".md")


class Page:
    """A journal page split into: page properties, goal items, other lines.
    Each goal item keeps its raw lines (Logseq may add `id::` or child lines)."""

    def __init__(self, content: str):
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
        # 2026-09-25 page-property form: goal:: a; b
        for p in list(self.props):
            m = PROP_RE.match(p)
            if m and m.group(1) == "goal":
                self.items += [[f"\t- {g}"] for g in m.group(2).split("; ") if g]
                self.props.remove(p)
        start = next((n for n, l in enumerate(rest) if HEADER_RE.match(l)), None)
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
        if self.items:
            out += [HEADER] + self.parent_extra + [l for it in self.items for l in it]
        out += self.body
        return "\n".join(out) + "\n"


def load(date_str: str | None) -> tuple[Path, Page]:
    path = journal_path(date_str)
    return path, Page(path.read_text(**ENC) if path.exists() else "")


def save(path: Path, page: Page) -> None:
    # Keep the journal's priority order within each status group.
    page.items.sort(
        key=lambda item: ITEM_RE.match(item[0]).group(2).startswith("DONE ")
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(page.render(), **ENC)


def index(page: Page, n: int) -> int:
    if not 1 <= n <= len(page.items):
        print(f"NO_SUCH_GOAL: {n} (have {len(page.items)})", file=sys.stderr)
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


def main() -> int:
    p = argparse.ArgumentParser(
        prog="goalsq",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--date", metavar="YYYY-MM-DD", help="Journal date (default: today)")
    p.add_argument(
        "-s",
        "--status",
        type=str.upper,
        choices=("NOW", "LATER", "DONE"),
        help="Show only goals in this status (list only)",
    )
    dp = argparse.ArgumentParser(add_help=False)  # --date also after the subcommand
    dp.add_argument("--date", metavar="YYYY-MM-DD", default=argparse.SUPPRESS)
    sub = p.add_subparsers(dest="cmd")
    g = sub.add_parser("get", parents=[dp], help="Show one goal with its notes")
    g.add_argument("n", type=int, help="Goal number")
    a = sub.add_parser("add", parents=[dp], help="Append a goal")
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
    s = sub.add_parser("set", parents=[dp], help="Set a goal field or append a note")
    s.add_argument("n", type=int)
    s.add_argument("field", choices=SET_FIELDS)
    s.add_argument("value", nargs="+")
    t = sub.add_parser("top", parents=[dp], help="Move goal N to priority 1")
    t.add_argument("n", type=int)
    m = sub.add_parser("mv", parents=[dp], help="Move goal N to position M")
    m.add_argument("n", type=int)
    m.add_argument("to", type=int)
    r = sub.add_parser("rm", parents=[dp], help="Remove goal N")
    r.add_argument("n", type=int)
    for name, hlp in (("done", "Mark goal N DONE"), ("undo", "Mark goal N open again")):
        s = sub.add_parser(name, parents=[dp], help=hlp)
        s.add_argument("n", type=int)
        if name == "done":
            s.add_argument("note", nargs="*", help="Optional completion note")
    h = sub.add_parser("history", help="Goals for the last N days")
    h.add_argument("days", nargs="?", type=int, default=7)
    argv = sys.argv[1:]
    offset = 2 if len(argv) >= 2 and argv[0] == "--date" else 0
    if len(argv) > offset and re.fullmatch(r"[0-9]+", argv[offset]):
        n, rest = argv[offset], argv[offset + 1 :]
        if rest and rest[0] in ("--help", "-h"):
            help_parser = argparse.ArgumentParser(
                prog=f"goalsq {n}",
                description="Show this goal or change one of its fields.",
                epilog=(
                    f"goalsq {n} now|later|done  change status directly\n"
                    f"goalsq {n} set FIELD VALUE  change a field (note appends)\n"
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
            argv = argv[:offset] + ["set", n, "status", rest[0]] + rest[1:]
        elif rest[0] == "set":
            if len(rest) > 1 and rest[1] in ("--help", "-h"):
                set_help = argparse.ArgumentParser(
                    prog=f"goalsq {n} set",
                    description="Change a goal field; note appends a child note.",
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
        p.error("--status filters only the goals list")

    if args.cmd == "history":
        today = datetime.date.today()
        for i in range(args.days - 1, -1, -1):
            d = today - datetime.timedelta(days=i)
            path = journal_path(d.isoformat())
            pg = Page(path.read_text(**ENC) if path.exists() else "")
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
        page = Page(path.read_text(**ENC))
        if not page.items:
            print("NO_GOAL_DECLARED")
            return 1
        if args.cmd == "get":
            print_goal(page, index(page, args.n) + 1)
        else:
            print_goals(page, args.status)
        return 0

    path, page = load(args.date)
    if args.cmd == "add":
        text = " ".join(args.text).strip()
        if not text or "\n" in text:
            print("BAD_GOAL: one non-empty line.", file=sys.stderr)
            return 2
        page.items.append([f"\t- {args.add_status} {text}"])
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
            if value == "DONE":
                page.items.append(page.items.pop(i))
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
        page.items.append(page.items.pop(i))
    elif args.cmd == "undo":
        page.set_marker(index(page, args.n), OPEN)
    save(path, page)
    print_goals(page)
    return 0


if __name__ == "__main__":
    sys.exit(main())
