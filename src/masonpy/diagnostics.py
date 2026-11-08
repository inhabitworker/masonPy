"""Repeatable Ashlar quality battery: legitimate construction failure is a result.

Run ``python -m masonpy.diagnostics --output /tmp/masonpy-battery``. Only invariant
violations or unexpected errors make this command exit unsuccessfully.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
import csv
import hashlib
import html
import json
import logging
from pathlib import Path
import platform
import statistics
import time
from typing import Any, Sequence
from xml.etree import ElementTree as ET

from masonpy.analysis import wall_report
from masonpy.analysis.report import ANALYSIS_COLOURS
from masonpy.generators.ashlar import AshlarGenerator
from masonpy.generators.errors import ConstructionFailure
from masonpy.models import Wall


@dataclass(frozen=True)
class BatteryCase:
    """One reproducible stock/style situation, not a promise of completion."""

    id: str
    width: int
    height: int
    purpose: str
    parameters: dict[str, int | float] = field(default_factory=dict)
    expectation: str = "exploratory"


def battery_cases(suite: str = "standard") -> tuple[BatteryCase, ...]:
    """Cover ordinary work, refinement, style extremes and incompatible stock."""
    reported = dict(
        min_stone_width=3, max_stone_width=10, min_stone_height=3, max_stone_height=7
    )
    cases = [
        BatteryCase(
            "default",
            52,
            30,
            "Original 52 × 30 reference wall with default stone settings",
            expectation="feasible",
        ),
        BatteryCase(
            "reported",
            104,
            60,
            "User-reported failure; includes seed 4",
            reported,
            "feasible",
        ),
        BatteryCase(
            "refined_2x",
            104,
            60,
            "Doubled wall and ordinary stock",
            dict(
                min_stone_width=6,
                max_stone_width=16,
                min_stone_height=4,
                max_stone_height=10,
            ),
            "feasible",
        ),
        BatteryCase(
            "fixed_ordinary",
            52,
            30,
            "Compatible fixed stock without snecks",
            dict(
                min_stone_width=4,
                max_stone_width=4,
                min_stone_height=3,
                max_stone_height=3,
                allow_snecks=0,
            ),
            "feasible",
        ),
        BatteryCase(
            "small_corner",
            5,
            3,
            "Both-small closing stones are needed",
            dict(
                min_stone_width=4,
                max_stone_width=4,
                min_stone_height=2,
                max_stone_height=2,
            ),
            "feasible",
        ),
        BatteryCase(
            "impossible_width",
            5,
            2,
            "Circumference cannot close with 4-wide stock",
            dict(
                min_stone_width=4,
                max_stone_width=4,
                min_stone_height=2,
                max_stone_height=2,
                allow_snecks=0,
            ),
            "incompatible",
        ),
    ]
    if suite == "quick":
        return tuple(cases)
    cases += [
        BatteryCase(
            "larger_wall",
            104,
            60,
            "Current workbench dimensions with default stone settings",
        ),
        BatteryCase(
            "necessary_snecks",
            104,
            60,
            "Zero preference still permits repairs",
            {**reported, "snecking_factor": 0},
        ),
        BatteryCase(
            "many_snecks",
            104,
            60,
            "Maximum deliberate sneck preference",
            {**reported, "snecking_factor": 1},
        ),
        BatteryCase(
            "uncoursed",
            104,
            60,
            "Discourage horizontal continuity",
            {**reported, "coursing_factor": 0},
        ),
        BatteryCase(
            "coursed",
            104,
            60,
            "Encourage horizontal continuity",
            {**reported, "coursing_factor": 1},
        ),
        BatteryCase(
            "stack_one",
            104,
            60,
            "Stricter bonding changes the construction path",
            {**reported, "max_joint_stack": 1},
        ),
        BatteryCase(
            "stack_three",
            104,
            60,
            "More permissive bonding",
            {**reported, "max_joint_stack": 3},
        ),
        BatteryCase(
            "no_stack_limit",
            104,
            60,
            "Control isolating the bonding constraint",
            {**reported, "enforce_stack": 0},
        ),
        BatteryCase(
            "no_snecks",
            104,
            60,
            "Ordinary stock only; sequence failure is legitimate",
            {**reported, "allow_snecks": 0},
        ),
        BatteryCase(
            "fixed_with_closers",
            52,
            30,
            "Restricted ordinary stock with flexible repairs",
            dict(
                min_stone_width=7,
                max_stone_width=7,
                min_stone_height=4,
                max_stone_height=4,
            ),
        ),
        BatteryCase(
            "minimum_closer_two",
            52,
            30,
            "Exclude unit-size closers",
            dict(min_sneck_size=2),
        ),
        BatteryCase(
            "impossible_height",
            12,
            5,
            "Height cannot close with fixed two-high stock",
            dict(
                min_stone_width=4,
                max_stone_width=4,
                min_stone_height=2,
                max_stone_height=2,
                allow_snecks=0,
            ),
            "incompatible",
        ),
        BatteryCase(
            "unit_joint_conflict",
            24,
            12,
            "Unit-width stock cannot break the required joints",
            dict(
                min_stone_width=1,
                max_stone_width=1,
                min_stone_height=1,
                max_stone_height=1,
            ),
            "incompatible",
        ),
    ]
    if suite == "stress":
        cases += [
            BatteryCase(
                "refined_3x",
                156,
                90,
                "Tripled wall and ordinary stock",
                dict(
                    min_stone_width=9,
                    max_stone_width=24,
                    min_stone_height=6,
                    max_stone_height=15,
                ),
            ),
            BatteryCase(
                "broad_stock",
                104,
                60,
                "Large candidate space exercises bounded sampling",
                dict(
                    min_stone_width=3,
                    max_stone_width=40,
                    min_stone_height=2,
                    max_stone_height=25,
                ),
            ),
            BatteryCase(
                "broad_large_minima",
                104,
                60,
                "Broad stock with larger ordinary minima",
                dict(
                    min_stone_width=8,
                    max_stone_width=60,
                    min_stone_height=6,
                    max_stone_height=30,
                ),
            ),
            BatteryCase(
                "shallow_wall", 37, 3, "Thin top and periodic closure", reported
            ),
            BatteryCase("narrow_wall", 7, 41, "Tall narrow periodic wall", reported),
        ]
    elif suite != "standard":
        raise ValueError(f"Unknown battery suite: {suite}")
    return tuple(cases)


def run_case(case: BatteryCase, seed: int) -> dict[str, Any]:
    """Generate one accepted prefix and independently audit its hard invariants."""
    wall = Wall(case.width, case.height)
    generator = AshlarGenerator(**case.parameters, seed=seed)
    failure = None
    unexpected = None
    events = []
    started = time.perf_counter()
    try:
        for event in generator.generate_incrementally(wall):
            events.append(event)
    except ConstructionFailure as exc:
        failure = exc.to_dict()
    except Exception as exc:
        unexpected = f"{type(exc).__name__}: {exc}"
    elapsed = time.perf_counter() - started
    parameters = {
        name: getattr(generator, name)
        for name in (
            "min_stone_width",
            "max_stone_width",
            "min_stone_height",
            "max_stone_height",
            "allow_snecks",
            "min_sneck_size",
            "snecking_factor",
            "coursing_factor",
            "jitter_start",
            "enforce_stack",
            "max_joint_stack",
        )
    }
    report = wall_report(
        wall,
        "ashlar",
        parameters,
        complete=failure is None and unexpected is None,
        failure=failure,
        events=events,
        unexpected=unexpected,
    )
    return {
        **report,
        "case": case.id,
        "seed": seed,
        "width": wall.width,
        "height": wall.height,
        "parameters": case.parameters,
        "effective_parameters": parameters,
        "failure": failure,
        "seconds": elapsed,
        "wall": wall.to_dict(),
    }


def summarize(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep complete-wall quality distinct from incomplete-prefix measurements."""
    summaries = []
    for name in dict.fromkeys(row["case"] for row in rows):
        group = [r for r in rows if r["case"] == name]
        complete = [r for r in group if r["complete"]]
        summaries.append(
            {
                "case": name,
                "runs": len(group),
                "completed": len(complete),
                "mean_fill": statistics.mean(r["fill"] for r in group),
                "complete_sneck_share": statistics.mean(
                    r["sneck_share"] for r in complete
                )
                if complete
                else None,
                "complete_sneck_area_share": statistics.mean(
                    r["sneck_area_share"] for r in complete
                )
                if complete
                else None,
                "prefix_sneck_area_share": statistics.mean(
                    r["sneck_area_share"] for r in group
                ),
                "max_sneck_aspect": max(r["max_sneck_aspect"] for r in group),
                "median_seconds": statistics.median(r["seconds"] for r in group),
                "max_seconds": max(r["seconds"] for r in group),
                "failure_kinds": dict(
                    Counter(r["failure"]["kind"] for r in group if r["failure"])
                ),
                "invariant_errors": sum(len(r["invariant_errors"]) for r in group),
            }
        )
    return summaries


def compare_runs(
    rows: Sequence[dict[str, Any]], previous: dict[str, Any]
) -> dict[str, Any]:
    """Pair identical requested configurations/seeds across saved battery snapshots."""
    earlier = {(r["case"], r["seed"]): r for r in previous["runs"]}
    pairs = []
    for row in rows:
        old = earlier.get((row["case"], row["seed"]))
        if old and all(
            old.get(k) == row.get(k) for k in ("width", "height", "parameters")
        ):
            pairs.append((old, row))
    return {
        "matched_runs": len(pairs),
        "new_completions": sum(not a["complete"] and b["complete"] for a, b in pairs),
        "lost_completions": sum(a["complete"] and not b["complete"] for a, b in pairs),
        "mean_fill_delta": statistics.mean(b["fill"] - a["fill"] for a, b in pairs)
        if pairs
        else None,
        "mean_sneck_area_delta_both_complete": statistics.mean(
            b["sneck_area_share"] - a["sneck_area_share"]
            for a, b in pairs
            if a["complete"] and b["complete"]
        )
        if any(a["complete"] and b["complete"] for a, b in pairs)
        else None,
    }


def _gallery_svg(row: dict[str, Any]) -> str:
    """Colour whole periodic stones: grey ordinary, blue repairs, purple deliberate."""
    w, h = row["width"], row["height"]
    root = ET.Element("svg", xmlns="http://www.w3.org/2000/svg", viewBox=f"0 0 {w} {h}")
    ET.SubElement(root, "rect", x="0", y="0", width=str(w), height=str(h), fill="#fff")
    for stone in row["wall"]["stones"]:
        traits = stone["traits"]
        colour = ANALYSIS_COLOURS["ordinary"]
        if stone["id"] in row["sneck_ids"]:
            colour = ANALYSIS_COLOURS[
                "deliberate" if traits.get("sneck_deliberate") else "fallback"
            ]
        for x in (stone["x"], stone["x"] - w):
            rect = ET.SubElement(
                root,
                "rect",
                x=str(x),
                y=str(h - stone["y"] - stone["height"]),
                width=str(stone["width"]),
                height=str(stone["height"]),
                fill=colour,
                stroke="white",
                **{"stroke-width": "0.12"},
            )
            ET.SubElement(
                rect, "title"
            ).text = f"Stone {stone['id']}: {stone['width']} × {stone['height']}"
    return ET.tostring(root, encoding="unicode")


def write_reports(
    output: Path,
    cases: Sequence[BatteryCase],
    rows: Sequence[dict[str, Any]],
    comparison: dict[str, Any] | None = None,
) -> None:
    """Write machine-readable runs, a compact CSV and a browsable SVG gallery."""
    output.mkdir(parents=True, exist_ok=True)
    summaries = summarize(rows)
    source = Path(__file__).parent / "generators"
    digest = hashlib.sha256(
        b"".join(
            source.joinpath(p).read_bytes() for p in ("ashlar.py", "ashlar_rules.py")
        )
    ).hexdigest()
    payload = {
        "version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(),
        "generator_sha256": digest,
        "analysis_sha256": hashlib.sha256(
            Path(__file__).with_name("analysis").joinpath("report.py").read_bytes()
        ).hexdigest(),
        "cases": [
            dict(
                id=c.id,
                width=c.width,
                height=c.height,
                purpose=c.purpose,
                expectation=c.expectation,
                parameters=c.parameters,
            )
            for c in cases
        ],
        "summaries": summaries,
        "comparison": comparison,
        "runs": rows,
    }
    (output / "report.json").write_text(json.dumps(payload, indent=2))
    with (output / "summary.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(summaries[0]))
        writer.writeheader()
        writer.writerows(summaries)
    body = []
    for case, summary in zip(cases, summaries):
        group = [r for r in rows if r["case"] == case.id]
        examples = list(
            dict.fromkeys(
                [
                    next((r["seed"] for r in group if r["complete"]), group[0]["seed"]),
                    next(
                        (r["seed"] for r in group if not r["complete"]),
                        group[0]["seed"],
                    ),
                    max(group, key=lambda r: r["max_sneck_aspect"])["seed"],
                ]
            )
        )
        if (
            case.id == "reported"
            and any(r["seed"] == 4 for r in group)
            and 4 not in examples
        ):
            examples.append(4)
        cards = []
        for seed in examples:
            row = next(r for r in group if r["seed"] == seed)
            filename = f"{case.id}-{seed}.svg"
            (output / filename).write_text(_gallery_svg(row))
            specimen_name = f"{case.id}-{seed}.config.json"
            (output / specimen_name).write_text(
                json.dumps(
                    dict(
                        generator="ashlar",
                        width=row["width"],
                        height=row["height"],
                        parameters={
                            **{
                                key: int(value) if isinstance(value, bool) else value
                                for key, value in row["effective_parameters"].items()
                            },
                            "seed": seed,
                        },
                    ),
                    indent=2,
                )
            )
            failure = (
                "; ".join(row["invariant_errors"])
                if row["invariant_errors"]
                else row["failure"]["message"]
                if row["failure"]
                else "Complete"
            )
            cards.append(
                f'<figure><a href="{filename}"><img src="{filename}" alt="{case.id}, seed {seed}"></a><figcaption>Seed {seed} · {row["fill"]:.0%} filled · {row["sneck_area_share"]:.1%} sneck area · <a href="{specimen_name}" download>Config JSON</a><p>{html.escape(failure)}</p></figcaption></figure>'
            )
        area = summary["complete_sneck_area_share"]
        body.append(
            f'<section id="{case.id}"><h2>{html.escape(case.id)} <small>{summary["completed"]}/{summary["runs"]} complete</small></h2><p>{html.escape(case.purpose)}. Expectation: {case.expectation}.</p><p>Wall {case.width} × {case.height}; complete-wall sneck area {format(area, ".1%") if area is not None else "—"}; worst accepted sneck aspect {summary["max_sneck_aspect"]:g}:1; median {summary["median_seconds"]:.3f}s; invariant errors {summary["invariant_errors"]}.</p><details><summary>Settings and failure categories</summary><pre>{html.escape(json.dumps(dict(parameters=group[0]["effective_parameters"], failure_kinds=summary["failure_kinds"]), indent=2))}</pre></details><div class="gallery">{"".join(cards)}</div></section>'
        )
    overview = '<div style="overflow:auto"><table><tr><th>Case</th><th>Complete</th><th>Mean fill</th><th>Sneck area*</th><th>Worst aspect</th><th>Median seconds</th><th>Defects</th></tr>'
    for summary in summaries:
        area = summary["complete_sneck_area_share"]
        overview += f'<tr><td><a href="#{summary["case"]}">{summary["case"]}</a></td><td>{summary["completed"]}/{summary["runs"]}</td><td>{summary["mean_fill"]:.0%}</td><td>{format(area, ".1%") if area is not None else "—"}</td><td>{summary["max_sneck_aspect"]:g}:1</td><td>{summary["median_seconds"]:.3f}</td><td>{summary["invariant_errors"]}</td></tr>'
    overview += "</table></div><p><small>*Completed walls only. Worst aspect also includes accepted failed prefixes. Timings are local observations, not benchmark guarantees.</small></p>"
    comparison_html = (
        f"<h2>Snapshot comparison</h2><pre>{html.escape(json.dumps(comparison, indent=2))}</pre>"
        if comparison
        else ""
    )
    document = """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>MasonPy Ashlar battery</title><style>body{font:15px/1.5 system-ui;margin:32px auto;padding:0 20px;max-width:1200px;color:#252525;background:#f7f6f3}h1,h2{line-height:1.2}h2 small{font-size:16px;font-weight:400;margin-left:16px}section{border-top:1px solid #ccc;margin-top:32px;padding-top:16px}.gallery{display:flex;flex-wrap:wrap;gap:20px}figure{margin:20px 0;flex:1 1 300px;max-width:600px}img{width:100%;max-height:400px;background:white;border:1px solid #ddd}figcaption{font-size:13px}pre{white-space:pre-wrap;font-size:12px}a{color:#176486}</style><h1>Ashlar diagnostic battery</h1><p>Grey: ordinary stones. Blue: fallback snecks. Purple: deliberate snecks. White space: unfilled. Click a drawing for its SVG; hover a stone there for its ID and dimensions.</p><p>Completion is a diagnostic, not an assertion. Incompatible configurations should fail. Sneck area in case summaries uses completed walls only; JSON also records accepted incomplete prefixes. Aspect is long side ÷ short side. These face-pattern metrics do not constitute a structural masonry assessment. Gallery: a complete example, a failed example and the worst sneck aspect, where distinct.</p><p><a href="report.json">Full JSON, including every wall and failure</a> · <a href="summary.csv">Summary CSV</a></p>"""
    document = document.replace(
        "</style>",
        "table{border-collapse:collapse;width:100%}th,td{text-align:left;padding:6px 12px;border-bottom:1px solid #ddd;white-space:nowrap}th{background:#ebe9e3}</style>",
    )
    (output / "report.html").write_text(
        document + overview + comparison_html + "".join(body) + "</html>"
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Return nonzero for defects, while keeping ordinary construction failures reportable."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--suite", choices=("quick", "standard", "stress"), default="standard"
    )
    parser.add_argument(
        "--seeds",
        type=int,
        default=12,
        help="Number of sequential seeds per case (default 12)",
    )
    parser.add_argument("--seed-start", type=int, default=0)
    parser.add_argument("--output", type=Path, default=Path("/tmp/masonpy-battery"))
    parser.add_argument(
        "--compare",
        type=Path,
        help="Previous report.json with matching requested settings/seeds",
    )
    args = parser.parse_args(argv)
    if args.seeds < 1 or args.seed_start < 0:
        parser.error("seeds must be positive and seed-start non-negative")
    logging.getLogger("masonpy.generators.ashlar").setLevel(logging.ERROR)
    cases = battery_cases(args.suite)
    rows = []
    for case in cases:
        group = [
            run_case(case, seed)
            for seed in range(args.seed_start, args.seed_start + args.seeds)
        ]
        rows.extend(group)
        print(
            f"{case.id:24} {sum(r['complete'] for r in group):2}/{len(group)} complete · {sum(bool(r['invariant_errors']) for r in group)} defects",
            flush=True,
        )
    comparison = (
        compare_runs(rows, json.loads(args.compare.read_text()))
        if args.compare
        else None
    )
    write_reports(args.output, cases, rows, comparison)
    print(f"Report: {args.output.resolve() / 'report.html'}")
    return int(any(r["invariant_errors"] for r in rows))


if __name__ == "__main__":
    raise SystemExit(main())
