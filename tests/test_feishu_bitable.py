from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import feishu_bitable as bitable  # noqa: E402


class TrackTableRoutingTests(unittest.TestCase):
    def test_existing_track_table_is_reused(self) -> None:
        existing = {"table_id": "tbl-existing", "name": "婚姻家事"}
        with patch.object(bitable, "list_tables", return_value=[existing]):
            table, action = bitable.resolve_track_table("token", "app", "婚姻家事", {}, apply=True)
        self.assertEqual(existing, table)
        self.assertEqual("existing", action)

    def test_empty_default_table_is_renamed_for_first_track(self) -> None:
        default = {"table_id": "tbl-default", "name": "数据表"}
        renamed = {"table_id": "tbl-default", "name": "恋爱纠纷法律科普"}
        with (
            patch.object(bitable, "list_tables", return_value=[default]),
            patch.object(bitable, "list_records", return_value=[{"fields": {"选题标题": None}}]),
            patch.object(bitable, "rename_table", return_value=renamed) as rename,
        ):
            table, action = bitable.resolve_track_table(
                "token", "app", "恋爱纠纷法律科普", {}, apply=True
            )
        self.assertEqual(renamed, table)
        self.assertEqual("renamed_default", action)
        rename.assert_called_once_with("token", "app", "tbl-default", "恋爱纠纷法律科普")

    def test_new_track_creates_new_table_when_existing_table_has_content(self) -> None:
        current = {"table_id": "tbl-current", "name": "恋爱纠纷法律科普"}
        created = {"table_id": "tbl-new", "name": "劳动纠纷法律科普"}
        with (
            patch.object(bitable, "list_tables", return_value=[current]),
            patch.object(bitable, "create_table", return_value=created) as create,
        ):
            table, action = bitable.resolve_track_table(
                "token", "app", "劳动纠纷法律科普", {}, apply=True
            )
        self.assertEqual(created, table)
        self.assertEqual("created", action)
        create.assert_called_once_with("token", "app", "劳动纠纷法律科普")

    def test_track_table_name_removes_forbidden_characters(self) -> None:
        self.assertEqual("婚姻-家事", bitable.table_name_for_track(" 婚姻/家事 "))


if __name__ == "__main__":
    unittest.main()
