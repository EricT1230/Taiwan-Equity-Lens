from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path

from taiwan_stock_analysis.dashboard_ui import page_script


_NODE = shutil.which("node")
_SCRIPT_SOURCE = Path(page_script.__file__).with_name("script.js").read_text(
    encoding="utf-8"
)


def _connection_block() -> str:
    policy_start = _SCRIPT_SOURCE.index("var MARKET_STATUS_POLICY")
    policy_end = _SCRIPT_SOURCE.index("function activateTab", policy_start)
    start = _SCRIPT_SOURCE.index("function liveUpdateConnection")
    end = _SCRIPT_SOURCE.index("function liveUpdateHero", start)
    return _SCRIPT_SOURCE[policy_start:policy_end] + _SCRIPT_SOURCE[start:end]


@unittest.skipUnless(_NODE, "node is unavailable")
class DashboardLiveConnectionStreamTests(unittest.TestCase):
    def test_market_status_policy_defines_every_public_state_once(self) -> None:
        self.assertIn("var MARKET_STATUS_POLICY =", _SCRIPT_SOURCE)
        for status in ("LIVE", "EOD", "DELAYED", "STALE", "UNAVAILABLE"):
            self.assertIn(f"{status}:{{", _SCRIPT_SOURCE)

    def test_connection_detail_exposes_websocket_transport_and_data_status(self) -> None:
        harness = _connection_block() + r"""
function makeNode() {
  return {
    textContent:"",
    className:"",
    title:"",
    classList:{
      remove:function () {},
      add:function () {},
      toggle:function () {}
    }
  };
}
var title = makeNode();
var detail = makeNode();
var bar = makeNode();
bar.querySelector = function (selector) {
  if (selector === '[data-live-connection-title="true"]') { return title; }
  if (selector === '[data-live-connection-detail="true"]') { return detail; }
  return null;
};
var document = {
  querySelector:function (selector) {
    return selector === '[data-live-connection="true"]' ? bar : null;
  }
};
function liveText() {}

function render(overall, transport, streamStatus) {
  liveUpdateConnection({
    status:overall,
    generated_at:"2026-08-28T13:05:00+08:00",
    provider:{label:"Fubon Neo", notice:"REST snapshot"},
    source_status:{quotes:{
      status:overall,
      stream:{transport_status:transport, status:streamStatus}
    }},
    missing_symbols:[],
    errors:[]
  });
  return {title:title.textContent, detail:detail.textContent};
}
process.stdout.write(JSON.stringify([
  render("LIVE", "STREAMING", "LIVE"),
  render("LIVE", "AUTHENTICATED", "UNAVAILABLE"),
  render("LIVE", "DISCONNECTED", "STALE")
]));
"""
        completed = subprocess.run(
            [_NODE or "node"],
            input=harness,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        results = json.loads(completed.stdout)

        self.assertEqual("市場連線中", results[0]["title"])
        self.assertIn("WebSocket STREAMING/LIVE", results[0]["detail"])
        self.assertEqual("市場連線中", results[1]["title"])
        self.assertIn("WebSocket AUTHENTICATED/UNAVAILABLE", results[1]["detail"])
        self.assertEqual("市場連線中", results[2]["title"])
        self.assertIn("WebSocket DISCONNECTED/STALE", results[2]["detail"])


if __name__ == "__main__":
    unittest.main()
