import json
import logging
from datetime import UTC, datetime


class JsonFormatter(logging.Formatter):
    """Emit one structured JSON object per log record."""

    _reserved = frozenset(logging.makeLogRecord({}).__dict__)

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in ("request_id", "query_run_id", "job_id", "source", "company_id"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = str(value)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
