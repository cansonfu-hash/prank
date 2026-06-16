"""dingtalk_client 的纯逻辑测试（不依赖 dws / 网络 / anthropic）。"""
import unittest
from datetime import date

from dingtalk_summarizer.dingtalk_client import (
    Message,
    _extract_text,
    _iter_message_objects,
    _normalize,
    filter_by_date,
    parse_timestamp,
)


class IterMessageObjectsTest(unittest.TestCase):
    def test_top_level_list(self):
        payload = [{"text": "a"}, {"text": "b"}, "garbage"]
        self.assertEqual(len(_iter_message_objects(payload)), 2)

    def test_messages_key(self):
        payload = {"messages": [{"text": "a"}]}
        self.assertEqual(len(_iter_message_objects(payload)), 1)

    def test_nested_data_list(self):
        payload = {"data": {"list": [{"text": "a"}, {"text": "b"}]}}
        self.assertEqual(len(_iter_message_objects(payload)), 2)

    def test_records_key(self):
        payload = {"records": [{"from": "x"}]}
        self.assertEqual(len(_iter_message_objects(payload)), 1)

    def test_empty(self):
        self.assertEqual(_iter_message_objects({"foo": "bar"}), [])


class ExtractTextTest(unittest.TestCase):
    def test_direct_text(self):
        self.assertEqual(_extract_text({"text": "hello"}), "hello")

    def test_nested_text_content(self):
        self.assertEqual(_extract_text({"text": {"content": "hi"}}), "hi")

    def test_content_field(self):
        self.assertEqual(_extract_text({"content": "yo"}), "yo")

    def test_markdown(self):
        self.assertEqual(_extract_text({"markdown": {"text": "**md**"}}), "**md**")

    def test_non_text_fallback(self):
        self.assertEqual(_extract_text({"msgtype": "picture"}), "<picture>")

    def test_unknown_fallback(self):
        self.assertEqual(_extract_text({}), "<非文本消息>")


class NormalizeTest(unittest.TestCase):
    def test_full_message(self):
        msg = _normalize(
            {"senderNick": "张三", "text": {"content": "上线 v2"}, "createTime": "10:00"}
        )
        self.assertEqual(msg.sender, "张三")
        self.assertEqual(msg.text, "上线 v2")
        self.assertEqual(msg.timestamp, "10:00")
        self.assertEqual(msg.as_line(), "[10:00] 张三: 上线 v2")

    def test_missing_sender_defaults(self):
        msg = _normalize({"text": "x"})
        self.assertEqual(msg.sender, "未知成员")

    def test_as_line_without_timestamp(self):
        self.assertEqual(Message(sender="李四", text="hi").as_line(), "李四: hi")


class ParseTimestampTest(unittest.TestCase):
    def test_string_datetime(self):
        dt = parse_timestamp("2026-06-16 10:30:00")
        self.assertEqual((dt.year, dt.month, dt.day, dt.hour), (2026, 6, 16, 10))

    def test_string_date_minute(self):
        dt = parse_timestamp("2026-06-16 09:05")
        self.assertEqual(dt.date(), date(2026, 6, 16))

    def test_iso_format(self):
        dt = parse_timestamp("2026-06-16T08:00:00")
        self.assertEqual(dt.date(), date(2026, 6, 16))

    def test_epoch_millis(self):
        from datetime import datetime, timedelta, timezone

        # 用 +08:00 的已知时刻构造毫秒 epoch，避免硬编码出错
        inst = datetime(2026, 6, 16, 12, 0, tzinfo=timezone(timedelta(hours=8)))
        epoch_ms = int(inst.timestamp() * 1000)
        dt = parse_timestamp(str(epoch_ms))
        self.assertEqual(dt.date(), date(2026, 6, 16))

    def test_epoch_seconds(self):
        from datetime import datetime, timedelta, timezone

        inst = datetime(2026, 6, 16, 12, 0, tzinfo=timezone(timedelta(hours=8)))
        dt = parse_timestamp(str(int(inst.timestamp())))
        self.assertEqual(dt.date(), date(2026, 6, 16))

    def test_unparseable(self):
        self.assertIsNone(parse_timestamp("not-a-time"))
        self.assertIsNone(parse_timestamp(""))


class FilterByDateTest(unittest.TestCase):
    def test_keeps_only_target_date(self):
        msgs = [
            Message("A", "今天1", "2026-06-16 09:00"),
            Message("B", "昨天", "2026-06-15 23:00"),
            Message("C", "今天2", "2026-06-16 18:30"),
        ]
        kept, unparsed = filter_by_date(msgs, target=date(2026, 6, 16))
        self.assertEqual([m.text for m in kept], ["今天1", "今天2"])
        self.assertEqual(unparsed, 0)

    def test_counts_unparseable(self):
        msgs = [
            Message("A", "ok", "2026-06-16 09:00"),
            Message("B", "无时间", ""),
            Message("C", "坏时间", "garbage"),
        ]
        kept, unparsed = filter_by_date(msgs, target=date(2026, 6, 16))
        self.assertEqual([m.text for m in kept], ["ok"])
        self.assertEqual(unparsed, 2)


if __name__ == "__main__":
    unittest.main()
