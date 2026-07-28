import argparse
import json

from .config import Settings
from .connectors import WxCliConnector


def main() -> int:
    parser = argparse.ArgumentParser(description="WechatAgent connector diagnostics")
    parser.add_argument("command", choices=["probe"])
    parser.add_argument("--wx-command", default="wx")
    args = parser.parse_args()
    connector = WxCliConnector(args.wx_command)
    probe = connector.probe()
    payload = {
        "status": probe.status,
        "wechat_version": probe.wechat_version,
        "connector_version": probe.connector_version,
        "accounts": [{"id": item.id, "display_name": item.display_name, "selected": item.selected} for item in probe.accounts],
        "reason": probe.reason,
        "requires_elevation": probe.requires_elevation,
        "unknown_shards": probe.unknown_shards,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if probe.status in {"ready", "account_selection_required"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
