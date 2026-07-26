import argparse
import json

from sqlalchemy import select

from app.database import SessionLocal
from app.models import PerformanceRule, User
from app.services.feishu_client import FeishuClient
from app.services.feishu_reverse_sync import import_records


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import one Feishu Base view into a teacher account.",
    )
    parser.add_argument("--username", required=True)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--view-id", required=True)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write changes. Without this flag, only show a dry-run plan.",
    )
    return parser.parse_args()


def main() -> int:
    args = _arguments()
    db = SessionLocal()
    client = FeishuClient()
    try:
        user = db.scalar(
            select(User).where(
                User.username == args.username,
                User.is_active.is_(True),
            )
        )
        if user is None:
            raise SystemExit(f"Active user not found: {args.username}")
        rules = list(
            db.scalars(
                select(PerformanceRule)
                .where(PerformanceRule.is_active.is_(True))
                .order_by(PerformanceRule.sort_order, PerformanceRule.id)
            )
        )
        records = client.list_records(view_id=args.view_id)
        result = import_records(
            db,
            user=user,
            year=args.year,
            rules=rules,
            records=records,
            client=client,
            dry_run=not args.apply,
        )
        print(
            json.dumps(
                {
                    "mode": "apply" if args.apply else "dry-run",
                    "username": args.username,
                    "year": args.year,
                    "created": result.created,
                    "skipped": result.skipped,
                    "failed": result.failed,
                    "items": [
                        {
                            "record_id": item.record_id,
                            "title": item.title,
                            "action": item.action,
                            "category": item.category,
                            "subcategory": item.subcategory,
                            "achievement_id": item.achievement_id,
                            "reason": item.reason,
                        }
                        for item in result.items
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1 if result.failed else 0
    finally:
        client.close()
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
