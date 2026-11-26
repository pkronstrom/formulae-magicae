"""Run an optional ngspice check against the bounds of named measurements."""

import argparse
import math
import re
import shutil
import subprocess
import sys
from pathlib import Path

from forge import digest, encode, save


NAME = r"[A-Za-z_][A-Za-z0-9_]*"
NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
MEASUREMENT = re.compile(rf"^[ \t]*({NAME})[ \t]*=[ \t]*({NUMBER})(?=[ \t\r]*$|[ \t])", re.M)


def limits(entries):
    result = {}
    for label, minimum, maximum in entries:
        name = label.lower()
        lower, upper = float(minimum), float(maximum)
        if (not re.fullmatch(NAME, name) or name in result
                or not all(map(math.isfinite, (lower, upper))) or lower > upper):
            raise ValueError(f"Invalid or repeated measurement limit: {label} {minimum} {maximum}")
        result[name] = (lower, upper)
    return result


def evaluate(output, bounds):
    observed = {name: [] for name in bounds}
    for label, number in MEASUREMENT.findall(output):
        name, value = label.lower(), float(number)
        if name in observed and math.isfinite(value):
            observed[name].append(value)
    measurements = []
    for name, (lower, upper) in bounds.items():
        values = observed[name]
        value = values[0] if len(values) == 1 else None
        result = "unknown" if value is None else "pass" if lower <= value <= upper else "fail"
        measurements.append({"name": name, "min": lower, "max": upper, "value": value,
                             "occurrences": len(values), "result": result})
    return measurements


def run(args):
    netlist, report = args.netlist.resolve(), args.report.resolve()
    if not netlist.is_file() or report == netlist or not report.parent.is_dir():
        raise ValueError("Use an existing netlist and a separate report in an existing directory")
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        raise ValueError("Timeout must be a positive number of seconds")
    bounds = limits(args.expect)
    executable = shutil.which("ngspice")
    if not executable:
        raise ValueError("ngspice was not found on PATH; add it to run this optional check")
    command = [str(Path(executable).absolute()), "-n", "-b", str(netlist)]
    netlist_hash = digest(netlist.read_bytes())
    try:
        process = subprocess.run(command, cwd=netlist.parent, capture_output=True,
                                 text=True, errors="replace", timeout=args.timeout, check=False)
        output = process.stdout + "\n" + process.stderr
        error = f"ngspice returned {process.returncode}" if process.returncode else None
    except subprocess.TimeoutExpired:
        output, error = "", f"ngspice timed out after {args.timeout:g} seconds"
    if digest(netlist.read_bytes()) != netlist_hash:
        error = "Netlist changed during simulation"
    measurements = evaluate(output, bounds)
    results = {m["result"] for m in measurements}
    if error:
        result = "unknown"
    elif "fail" in results:
        result = "fail"
    elif "unknown" in results:
        result = "unknown"
        error = "A requested measurement was missing or ambiguous. Check .measure, .print and the log."
    else:
        result = "pass"
    save(report, encode({"plugin": "pcb-spice", "result": result, "command": command,
                         "netlist_sha256": netlist_hash, "measurements": measurements,
                         "error": error, "log": output}))
    print(f"{result}: {report}")
    return {"pass": 0, "fail": 1, "unknown": 2}[result]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("netlist", type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--expect", required=True, action="append", nargs=3,
                        metavar=("NAME", "MIN", "MAX"), help="Inclusive bounds for a .measure result")
    parser.add_argument("--timeout", type=float, default=30, metavar="SECONDS")
    try:
        return run(parser.parse_args())
    except (OSError, ValueError) as error:
        print(f"pcb-spice: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
