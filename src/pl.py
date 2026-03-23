#!/usr/bin/env python3

import asyncio
import io
import os
import shlex
import sys
from contextlib import suppress
from functools import wraps

from rich.console import Console, Group
from rich.live import Live
from rich.text import Text


class Command:
    MAX_LINES = 8

    def __init__(self, name, cwd, command):
        self.name = name
        self.command = shlex.split(command)
        self.cwd = cwd
        self.process = None
        self._buffer = []

    def append(self, line):
        # self._buffer = self._buffer[-self.MAX_LINES+1:]
        self._buffer.append(line)

    async def run(self, queue):
        self.process = await asyncio.create_subprocess_exec(
            *self.command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=self.cwd,
        )
        while chunk := await self.process.stdout.read(2 ** 18):
            await queue.put([self.name, chunk.decode().strip()])
        return self.process

def render(commands, live):
    render = []
    for name, command in commands.items():
        items = []
        title = ' '.join(command.command)
        bar = f"{title} {'-' * (100 - len(title))}"
        items.append(Text(f"{name} {bar}", style="orange3"))
        min_idx = max(len(command._buffer) - command.MAX_LINES, 1)
        sub_items = []
        for idx, line in enumerate(command._buffer[min_idx:], min_idx):
            sub_items.append(Text(f"{idx:03}  ", style="dim"))
            sub_items.append(Text(line + "\n", style="gray75"))
        if sub_items:
            items.append(Text.assemble(*sub_items))
        render.append(Group(*items))
    live.update(Group(*render))
    live.refresh()


async def render_loop(commands, queue, live):
    while True:
        item = None
        with suppress(TimeoutError):
            item = await asyncio.wait_for(queue.get(), timeout=0.2)
        if item:
            name, content = item
            for line in content.split("\n"):
                commands[name].append(line)
        render(commands, live)


def handle_non_interactive():
    if os.isatty(sys.stdin.fileno()):
        print("Interactive mode (for non-interactive, use a pipe)", file=sys.stderr)
        print("Enter commands to be executed in parallel, one per line.", file=sys.stderr)
        print("To execute, end with an empty line and press ^D", file=sys.stderr)


def async_wrapper(f):
    @wraps(f)
    def internal(*args, **kwargs):
        try:
            return asyncio.run(f(*args, **kwargs))
        except KeyboardInterrupt:
            print("Execution aborted", file=sys.stderr)
            sys.exit(0)
    return internal


@async_wrapper
async def run(*commands, repos=None, cwd=None, header=True, output=True):

    if isinstance(commands, str):
        commands = [commands]
    if repos:
        def make_commands(commands, repos):
            return [
                x.replace("{path}", str(repo.path))
                 .replace("{remote}", repo.remote)
                 .replace("{branch}", repo.branch)
                for x in commands
                for repo_name, repo in repos.items()
            ]
        commands = make_commands(commands, repos)

    cwd = cwd or os.path.abspath(os.path.curdir)
    if not commands:
        handle_non_interactive()
        commands = [
            stripped
            for line in sys.stdin.read().split("\n")
            if (stripped := line.rstrip())
        ]
    else:
        commands = list(commands)

    if header:
        for command in commands:
            print(f"$ {command}")
        print(80 * '-')

    commands = {
        name: Command(name=name, cwd=cwd, command=line)
        for idx, line in enumerate(commands, 1)
        if (name := str(idx))
    }

    Console()
    queue = asyncio.Queue()
    with Live(transient=True, screen=False) as live:
        render_task = asyncio.create_task(
            render_loop(commands, queue, live)
        )

        await asyncio.gather(
            *[cmd.run(queue) for name, cmd in commands.items()],
        )
        render(commands, live)
        render_task.cancel()

        live.update("")

    stream = sys.stdout if output else io.StringIO()
    for _idx, command in commands.items():
        for line in command._buffer:
            print(line, file=stream)
        print(file=stream)

    if not output:
        stream.seek(0)
        return stream.read()
    return None

if __name__ == "__main__":
    run()
