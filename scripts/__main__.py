# SPDX-License-Identifier: MPL-2.0

"""The one command line of the repository: `uv run --locked --no-dev -m scripts GROUP COMMAND`.

Each entry names the module that owns the command. Modules load on demand, so a command
imports only what it needs (the delta builder needs the `deltas` dependency group).
"""

import importlib
import sys

# A group maps either to one `module:function` or to a table of commands.
COMMANDS: dict[str, str | dict[str, str]] = {
    "lock": "scripts.lock.cli:main",
    "pins": "scripts.pins.cli:main",
    "build": "scripts.build:main",
    "validate-runtime": "scripts.validate_runtime:main",
    "monitor": "scripts.monitor:main",
    "frametime": "scripts.frametime:main",
    "release": {
        "combine": "scripts.release.combine:main",
        "deltas": "scripts.release.deltas:main",
        "assert-absent": "scripts.release.absent:main",
        "licenses": "scripts.release.licenses:main",
    },
}


def usage() -> str:
    lines = ["usage: python -m scripts GROUP [COMMAND] [ARGUMENTS]", "", "commands:"]
    for group, target in COMMANDS.items():
        if isinstance(target, dict):
            lines.extend(f"  {group} {name}" for name in target)
        else:
            lines.append(f"  {group} ...")
    return "\n".join(lines)


def resolve(arguments: list[str]) -> tuple[str, list[str]] | None:
    """Return the `module:function` target and the arguments left for it."""

    if not arguments or arguments[0] not in COMMANDS:
        return None
    target = COMMANDS[arguments[0]]
    if isinstance(target, str):
        return target, arguments[1:]
    if len(arguments) < 2 or arguments[1] not in target:
        return None
    return target[arguments[1]], arguments[2:]


def main(arguments: list[str]) -> int:
    resolved = resolve(arguments)
    if resolved is None:
        stream = sys.stdout if arguments[:1] in (["-h"], ["--help"]) else sys.stderr
        print(usage(), file=stream)
        return 0 if stream is sys.stdout else 2
    module_name, function_name = resolved[0].split(":")
    function = getattr(importlib.import_module(module_name), function_name)
    return function(resolved[1])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
