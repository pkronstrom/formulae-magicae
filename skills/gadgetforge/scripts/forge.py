"""Persist and evaluate Gadgetforge project evidence with Python 3.10 and Git."""
import argparse
import base64
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

ASSETS = Path(__file__).resolve().parents[1] / "assets"
VISUALS = {".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg",
           ".jpeg": "image/jpeg", ".webp": "image/webp"}
DATA_BLOCK = re.compile(r'(<script id="app-data" type="application/json">)(.*?)(</script>)', re.S)


def encode(value):
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def digest(value):
    return hashlib.sha256(value).hexdigest()


def identity(value):
    return digest(json.dumps(value, sort_keys=True, ensure_ascii=False).encode())


def save(path, data):
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as fp:
        temp = Path(fp.name)
        try:
            fp.write(data.encode())
            fp.close()
            temp.replace(path)
        finally:
            temp.unlink(missing_ok=True)


def read_json(path):
    return json.loads(path.read_text())


class Project:
    def __init__(self, root):
        self.root = root
        self.state_path = root / ".gadgetforge/project.json"
        self.workflow = self.state_path.with_name("workflow.json")
        self.state = read_json(self.state_path)
        raw = self.workflow.read_bytes()
        if self.state["version"] != 1 or digest(raw) != self.state["workflow"]:
            raise ValueError("Unknown state version or changed pinned workflow")
        self.phases = {p["id"]: p for p in json.loads(raw)["phases"]}

    def write(self):
        save(self.state_path, encode(self.state))

    def file(self, relative, required=True):
        candidate = Path(relative)
        path = (self.root / candidate).resolve()
        if candidate.is_absolute() or not path.is_relative_to(self.root):
            raise ValueError(f"Expected a project-relative file: {relative}")
        if required and not path.is_file():
            raise ValueError(f"Missing file: {relative}")
        return path

    def stamp(self, relative):
        path = self.file(relative, required=False)
        return digest(path.read_bytes()) if path.is_file() else None

    def active(self, phase):
        firmware = self.state["firmware"]
        pricing = self.state.get("pricing")
        return {
            None: True,
            "pricing": self.state["target"] == "delivery" if pricing is None else pricing,
            "enclosure": self.state["enclosure"],
            "programmable": firmware != "none",
            "build": firmware == "build",
            "release": self.state["target"] != "design",
            "physical": self.state["physical"],
        }[phase.get("when")]

    def reviews(self, phase):
        return phase["review"] if "review" in phase else False

    def status(self):
        statuses = {}
        for key, phase in self.phases.items():
            current = self.state["current"].get(key)
            entry = {"id": key, "title": phase["title"], "guide": phase["guide"],
                     "status": "ready", "reasons": [], "review": None,
                     "snapshot": current, "needs": {}, "outputs": {}, "verified": [],
                     "requiredOutputs": phase["outputs"], "requiredChecks": phase["checks"],
                     "hasReview": self.reviews(phase)}
            needs = list(phase["needs"])
            for setting, extra in phase.get("needsWhen", {}).items():
                if self.state.get(setting, False):
                    needs.extend(extra)
            for need in needs:
                dependency = statuses[need]
                if dependency["status"] != "not applicable":
                    entry["needs"][need] = dependency["basis"]
                    if dependency["status"] != "accepted":
                        entry["reasons"].append(f"Requires current {dependency['title']}")
            if not self.active(phase):
                entry.update(status="not applicable", reasons=["Outside the selected project scope"])
            elif current:
                self.evaluate(phase, current, entry)
            elif entry["reasons"]:
                entry["status"] = "blocked"
            # Include actual file and upstream state so old feedback is detectable
            # before an edited candidate has even been captured again.
            entry["basis"] = identity(entry)
            statuses[key] = entry
        return statuses

    def evaluate(self, phase, current, entry):
        candidate = self.state["snapshots"][phase["id"]][current]
        actual = {name: self.stamp(path) for name, path in candidate["files"].items()}
        entry["outputs"] = actual
        if entry["reasons"] or actual != candidate["hashes"] or entry["needs"] != candidate["needs"]:
            entry["status"] = "stale"
            entry["reasons"].append("Input or output revision changed. Capture current files and recheck.")
            return
        receipts = candidate["evidence"]
        entry["evidence"] = identity(receipts)
        for check in phase["checks"]:
            receipt = receipts.get(check)
            if receipt is None or receipt["result"] != "pass":
                entry["reasons"].append(f"{check}: {receipt['result'] if receipt else 'missing'}")
            elif receipt.get("report") and self.stamp(receipt["report"]) != receipt["hash"]:
                entry["reasons"].append(f"{check}: report changed")
            else:
                entry["verified"].append(check)
        if entry["reasons"]:
            entry["status"] = "needs checks"
        elif self.reviews(phase):
            checks = {check: receipts[check] for check in phase["checks"]}
            token = identity({"snapshot": current, "evidence": checks})
            entry["review"] = token
            decision = receipts.get("review")
            if decision and decision.get("basis") == token:
                report = decision.get("report")
                agreed = (decision["result"] == "pass" and
                          (not report or self.stamp(report) == decision["hash"]))
            else:
                legacy = self.state["approvals"].get(token, {})
                agreed = legacy.get("phase") == phase["id"]
            entry["status"] = "accepted" if agreed else "awaiting review"
        else:
            entry["status"] = "accepted"

    def capture(self, args):
        entry = self.status()[args.phase]
        phase = self.phases[args.phase]
        if not self.active(phase):
            raise ValueError("This phase is not applicable")
        if any(reason.startswith("Requires current ") for reason in entry["reasons"]):
            raise ValueError("; ".join(entry["reasons"]))
        outputs = {}
        for pair in args.output:
            name, has_eq, path = pair.partition("=")
            if not has_eq or name in outputs or name not in phase["outputs"]:
                raise ValueError(f"Unexpected or repeated output: {pair}")
            outputs[name] = path
        missing = set(phase["outputs"]) - outputs.keys()
        if missing:
            raise ValueError(f"Missing outputs: {', '.join(sorted(missing))}")
        visual = self.file(outputs["visual"])
        if visual.suffix.lower() not in VISUALS:
            raise ValueError("Visual must be SVG, PNG, JPEG or WebP")
        self.record_candidate(args, entry, outputs, visual)

    def record_candidate(self, args, entry, outputs, visual):
        files = {f"output:{name}": path for name, path in outputs.items()}
        files.update({f"input:{path}": path for path in sorted(set(args.uses))})
        for path in files.values():
            self.file(path)
        candidate = {"files": files, "hashes": {key: self.stamp(path) for key, path in files.items()},
                     "needs": entry["needs"]}
        if args.phase == "brief":
            candidate["scopeRevision"] = self.state.get("scopeRevision", 0)
        snapshot = identity({"phase": args.phase, **candidate})
        history = self.state["snapshots"].setdefault(args.phase, {})
        if snapshot not in history:
            preview = self.state_path.parent / "previews" / (snapshot + visual.suffix.lower())
            preview.parent.mkdir(exist_ok=True)
            preview.write_bytes(visual.read_bytes())
            history[snapshot] = {**candidate, "evidence": {}, "preview": str(preview.relative_to(self.root))}
        self.state["current"][args.phase] = snapshot
        self.write()
        print(snapshot)

    def evidence(self, args):
        entry = self.status()[args.phase]
        if entry["status"] in {"ready", "blocked", "stale", "not applicable"}:
            raise ValueError("Capture a current candidate before recording evidence")
        if not args.note.strip():
            raise ValueError("Include the basis of the evidence in the note")
        receipt = {"result": args.result, "note": args.note, "report": args.report}
        if args.check == "review":
            if not entry["review"]:
                raise ValueError("Record a milestone decision after the current candidate passes its phase checks")
            receipt["basis"] = entry["review"]
        elif args.check not in entry["requiredChecks"]:
            raise ValueError("Use a defined phase check")
        if args.report:
            self.file(args.report)
            receipt["hash"] = self.stamp(args.report)
        candidate = self.state["snapshots"][args.phase][entry["snapshot"]]
        candidate["evidence"][args.check] = receipt
        self.write()

    def firmware_demo(self):
        path = self.file(".gadgetforge/firmware-demo.json", required=False)
        if not path.exists():
            return None
        demo = read_json(path)
        if not isinstance(demo, dict) or any(not isinstance(demo.get(key), str) or not demo[key].strip()
                                             for key in ("target", "hardware", "binary", "sha256")):
            raise ValueError("Firmware demo requires target, hardware, binary and sha256")
        if digest(self.file(demo["binary"]).read_bytes()) != demo["sha256"]:
            raise ValueError("Firmware demo binary changed. Recheck the scenario and refresh its captures.")
        if not isinstance(demo.get("frames"), list) or not demo["frames"]:
            raise ValueError("Firmware demo requires captioned frames")
        frames = []
        for frame in demo["frames"]:
            if not isinstance(frame, dict) or not isinstance(frame.get("caption"), str) or not frame["caption"].strip():
                raise ValueError("Each firmware demo frame needs a caption")
            image = self.file(frame["file"])
            if image.suffix.lower() != ".png":
                raise ValueError("Firmware demo frames must be PNG files")
            raw = image.read_bytes()
            if digest(raw) != frame["sha256"]:
                raise ValueError(f"Firmware demo frame changed: {frame['file']}")
            frames.append({"caption": frame["caption"], "src": "data:image/png;base64," +
                           base64.b64encode(raw).decode()})
        return {"target": demo["target"], "hardware": demo["hardware"], "sha256": demo["sha256"], "frames": frames}

    def board(self, args):
        phases = []
        for key, status in self.status().items():
            history = self.state["snapshots"].get(key, {})
            active = status["snapshot"]
            ordered = [s for s in history if s != active] + ([active] if active else [])
            views = []
            for snapshot in reversed(ordered[-2:]):
                candidate = history[snapshot]
                preview = self.file(candidate["preview"])
                data = base64.b64encode(preview.read_bytes()).decode()
                views.append({"id": snapshot, "caption": candidate["files"]["output:visual"],
                              "src": f"data:{VISUALS[preview.suffix]};base64,{data}"})
            checks = history[active]["evidence"] if active else {}
            if key == "firmware":
                status["demo"] = self.firmware_demo()
            phases.append({**status, "previews": views, "checks": checks,
                           "artifacts": {k.removeprefix("output:"): v for k, v in
                                         (history[active]["files"] if active else {}).items()
                                         if k.startswith("output:")}})
        data = {"v": 1, "title": self.state["title"], "projectId": self.state["id"],
                "mode": self.state["mode"], "scope": self.state["target"],
                "phases": phases, "feedback": [], "inbox": self.feedback_items()}
        markup = (ASSETS / "board.html").read_text()
        content = encode(data).replace("<", r"\u003c")
        markup, count = DATA_BLOCK.subn(lambda m: m[1] + "\n" + content + m[3], markup)
        if count != 1:
            raise ValueError("Unexpected board template")
        limit = args.max_bytes
        if len(markup.encode()) > limit:
            raise ValueError(f"Board exceeds {limit} bytes. Use smaller previews or agree a larger limit.")
        path = self.file(args.output, required=False)
        if path.exists():
            existing = self.feedback_data(path)
            if any(item["id"] not in self.state["feedback"] for item in existing["feedback"]):
                raise ValueError("Import saved feedback before replacing this board")
        save(path, markup)
        print(path)

    def feedback_items(self):
        statuses = self.status()
        return [item if item["status"] == "resolved" else feedback_record(item, statuses)
                for item in self.state["feedback"].values()]

    def feedback_data(self, path):
        raw = path.read_text()
        if path.suffix.lower() == ".html":
            match = DATA_BLOCK.search(raw)
            if not match:
                raise ValueError("No board data block found")
            raw = match[2]
        data = json.loads(raw)
        if not isinstance(data, dict) or data.get("v") != 1 or data.get("projectId") != self.state["id"]:
            raise ValueError("Unknown feedback format or different project")
        if not isinstance(data.get("feedback"), list):
            raise ValueError("Invalid feedback list")
        return data

    def import_feedback(self, path):
        data = self.feedback_data(Path(path))
        statuses = self.status()
        inbox = self.state["feedback"]
        added = 0
        for item in data["feedback"]:
            entry = feedback_record(item, statuses)
            existing = inbox.get(entry["id"])
            if existing:
                if any(existing.get(key) != value for key, value in entry.items() if key != "status"):
                    raise ValueError(f"Feedback identifier collision: {entry['id']}")
                continue
            inbox[entry["id"]] = entry
            added += 1
        self.write()
        print(f"Imported {added} feedback item(s)")

    def configure(self, args):
        choices = {key: getattr(args, key) for key in (
            "target", "firmware", "mode", "enclosure", "physical", "factory_programming", "pricing")
                   if getattr(args, key) is not None}
        next_state = {**self.state, **choices}
        if choices.get("pricing") and "pricing" not in self.phases:
            raise ValueError("This pinned workflow predates pricing. Use the pricing guide alongside architecture.")
        factory_programming = next_state.get("factory_programming", False)
        check_scope(next_state["target"], next_state["firmware"], next_state["physical"],
                    factory_programming)
        if factory_programming and "factory_programming" not in self.phases["release"].get("needsWhen", {}):
            raise ValueError("Factory programming requires a project workflow with conditional release dependencies")
        if any(key in {"target", "enclosure"} and value != self.state[key]
               for key, value in choices.items()):
            # Scope is part of the product brief. Ask for fresh evidence and approval
            # even if its files have not been updated yet.
            self.state["current"].pop("brief", None)
            self.state["scopeRevision"] = self.state.get("scopeRevision", 0) + 1
        self.state.update(choices)
        self.write()


def feedback_record(item, statuses):
    if not isinstance(item, dict):
        raise ValueError("Malformed feedback item")
    keys = ("id", "phase", "basis", "kind", "text")
    if any(not isinstance(item.get(k), str) or not item[k].strip() for k in keys):
        raise ValueError("Feedback requires an ID, phase, basis, kind and text")
    entry = {key: item[key] for key in keys}
    if entry["kind"] not in {"change", "answer", "direction", "review"}:
        raise ValueError("Unknown feedback kind")
    phase = statuses.get(entry["phase"])
    if phase is None:
        raise ValueError("Unknown feedback phase")
    image = item.get("image")
    if image is not None:
        if (not isinstance(image, dict) or not isinstance(image.get("id"), str)
                or any(type(image.get(k)) not in (int, float) or not 0 <= image[k] <= 1 for k in ("x", "y"))):
            raise ValueError("Invalid image annotation")
        entry["image"] = {k: image[k] for k in ("id", "x", "y")}
    current_image = image is None or image["id"] == phase["snapshot"]
    entry["status"] = "pending" if current_image and entry["basis"] == phase["basis"] else "conflict"
    return entry


def check_scope(target, firmware, physical, factory_programming):
    if physical and target == "design":
        raise ValueError("Physical validation needs a package or delivery scope")
    if factory_programming and (target == "design" or firmware != "build"):
        raise ValueError("Factory programming needs a package or delivery scope and a firmware build")


def initialize(root, args):
    check_scope(args.target, args.firmware, args.physical, args.factory_programming)
    root.mkdir(parents=True, exist_ok=True)
    marker = root / ".gadgetforge"
    if marker.exists():
        raise ValueError("Project already has Gadgetforge records. Use status to resume.")
    if not (root / ".git").exists():
        if not args.adopt and any(root.iterdir()):
            raise ValueError("Existing directory. Use --adopt to preserve and assess its files.")
        subprocess.run(["git", "init", "-q", str(root)], check=True)
    marker.mkdir()
    raw = (ASSETS / "workflow.json").read_bytes()
    (marker / "workflow.json").write_bytes(raw)
    save(marker / "project.json", encode({
        "version": 1, "id": str(uuid.uuid4()), "title": args.title or root.name,
        "mode": args.mode, "target": args.target, "firmware": args.firmware,
        "enclosure": not args.no_enclosure, "physical": args.physical,
        "factory_programming": args.factory_programming,
        "pricing": args.pricing,
        "workflow": digest(raw), "current": {}, "snapshots": {}, "approvals": {}, "feedback": {},
    }))
    print(f"Project at {root}")


def cli():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default=".")
    commands = parser.add_subparsers(dest="action", required=True)
    init = commands.add_parser("init")
    init.add_argument("--title")
    init.add_argument("--mode", choices=("hobbyist", "professional"), default="hobbyist")
    init.add_argument("--target", choices=("design", "package", "delivery"), default="design")
    init.add_argument("--firmware", choices=("none", "handoff", "build"), required=True)
    init.add_argument("--factory-programming", action="store_true",
                      help="Require accepted firmware in the release for factory loading")
    init.add_argument("--no-enclosure", action="store_true")
    init.add_argument("--physical", action="store_true")
    init.add_argument("--adopt", action="store_true")
    init.add_argument("--pricing", action=argparse.BooleanOptionalAction, default=None,
                      help="Estimate costs across manufacturers (on by default for delivery)")
    config = commands.add_parser("configure")
    config.add_argument("--mode", choices=("hobbyist", "professional"))
    config.add_argument("--target", choices=("design", "package", "delivery"))
    config.add_argument("--firmware", choices=("none", "handoff", "build"))
    config.add_argument("--factory-programming", action=argparse.BooleanOptionalAction,
                        default=None, help="Set whether the release includes factory loading")
    for feature in ("physical", "enclosure", "pricing"):
        config.add_argument("--" + feature, action=argparse.BooleanOptionalAction, default=None)
    for action in ("status", "feedback"):
        commands.add_parser(action).add_argument("--json", action="store_true")
    capture = commands.add_parser("capture")
    capture.add_argument("phase")
    capture.add_argument("--output", action="append", default=[])
    capture.add_argument("--uses", action="append", default=[])
    evidence = commands.add_parser("evidence")
    evidence.add_argument("phase")
    evidence.add_argument("check")
    evidence.add_argument("--result", choices=("pass", "fail", "unknown"), required=True)
    evidence.add_argument("--note", required=True)
    evidence.add_argument("--report")
    board = commands.add_parser("board")
    board.add_argument("--output", default="board.html")
    board.add_argument("--max-bytes", type=int, default=5_000_000)
    commands.add_parser("import-feedback").add_argument("file")
    resolve = commands.add_parser("resolve-feedback")
    resolve.add_argument("id")
    resolve.add_argument("--note", required=True)
    args = parser.parse_args()
    root = Path(args.project).resolve()
    if args.action == "init":
        initialize(root, args)
        return
    project = Project(root)
    if args.action == "status":
        entries = list(project.status().values())
        if args.json:
            print(encode(entries), end="")
        else:
            for entry in entries:
                reasons = "; ".join(entry["reasons"])
                print(f"{entry['id']:<18} {entry['status']}" + (f"  {reasons}" if reasons else ""))
    elif args.action == "feedback":
        items = project.feedback_items()
        if args.json:
            print(encode(items), end="")
        else:
            for item in items:
                print(f"{item['id']} {item['status']} [{item['phase']}] {item['text']}")
    elif args.action == "import-feedback":
        project.import_feedback(args.file)
    elif args.action == "resolve-feedback":
        record = project.state["feedback"][args.id]
        record.update(status="resolved", resolution=args.note)
        project.write()
    else:
        getattr(project, args.action)(args)


if __name__ == "__main__":
    try:
        cli()
    except (ValueError, KeyError, TypeError, OSError, subprocess.CalledProcessError) as error:
        sys.exit(f"Gadgetforge: {error}")
