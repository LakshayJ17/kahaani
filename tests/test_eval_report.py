"""Report builds with no results, and with a few fake ones; notebooks are valid JSON."""

import json
from pathlib import Path

from eval.report import build_report

ROOT = Path(__file__).resolve().parent.parent


def test_report_on_missing_out_dir(tmp_path):
    text = build_report(tmp_path / "nothing_here", charts=True)
    assert "No results yet" in text
    assert (tmp_path / "nothing_here" / "report.md").exists()


def test_report_with_some_results(tmp_path):
    (tmp_path / "consistency_clip.jsonl").write_text(
        json.dumps(
            {
                "setup": "fixed",
                "id": "b01",
                "n_pages": 2,
                "ref_sims": [0.8, 0.9],
                "ref_sim_mean": 0.85,
                "pairwise_mean": 0.9,
            }
        )
        + "\n"
    )
    summary = {
        "llm_run": False,
        "expect_block": 2,
        "expect_allow": 1,
        "blocked": 1,
        "blocked_by_layer": {"rules": 1},
        "missed": ["a2"],
        "false_positives": [],
    }
    (tmp_path / "safety.json").write_text(json.dumps({"summary": summary, "results": []}))
    text = build_report(tmp_path, charts=False)
    assert "| fixed | 1 | 0.85 | 0.9 |" in text
    assert "## Safety suite" in text
    assert "not run" in text


def test_notebooks_are_valid_json():
    for path in ("notebooks/ip_adapter_kaggle.ipynb", "eval/results.ipynb"):
        nb = json.loads((ROOT / path).read_text("utf-8"))
        assert nb["nbformat"] == 4
        assert len(nb["cells"]) > 2
        assert any(cell["cell_type"] == "code" for cell in nb["cells"])
