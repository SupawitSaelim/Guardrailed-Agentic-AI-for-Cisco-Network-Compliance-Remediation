"""Command-line entry point for inspecting approval requests."""

import argparse
import json

from app.approval import ApprovalService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Cisco remediation approval CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List approval requests")
    list_parser.set_defaults(handler=_list_approvals)

    get_parser = subparsers.add_parser("get", help="Get one approval request")
    get_parser.add_argument("approval_id")
    get_parser.set_defaults(handler=_get_approval)
    return parser


def _list_approvals(service: ApprovalService, _arguments: argparse.Namespace) -> int:
    print(json.dumps([record.model_dump(mode="json") for record in service.list()], indent=2))
    return 0


def _get_approval(service: ApprovalService, arguments: argparse.Namespace) -> int:
    try:
        record = service.get(arguments.approval_id)
    except KeyError as error:
        print(str(error))
        return 1
    print(json.dumps(record.model_dump(mode="json"), indent=2))
    return 0


def main() -> int:
    arguments = build_parser().parse_args()
    return arguments.handler(ApprovalService(), arguments)


if __name__ == "__main__":
    raise SystemExit(main())