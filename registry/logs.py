import hashlib
import json
import os
import re
from datetime import datetime
from pathlib import Path

from django.conf import settings
from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk


LOG_LINE = re.compile(
    r"^(?P<timestamp>\S+) (?P<level>INFO|WARNING|ERROR) "
    r"(?P<logger>\S+) (?P<message>.*)$"
)


class LogQueryError(ValueError):
    pass


class LogSearchUnavailable(Exception):
    pass


def tokenize_log_query(expression):
    tokens = []
    position = 0
    while position < len(expression):
        character = expression[position]
        if character.isspace():
            position += 1
            continue
        if character in "()":
            tokens.append((character, character))
            position += 1
            continue
        if character == '"':
            end = expression.find('"', position + 1)
            if end == -1:
                raise LogQueryError("The quoted phrase is not closed.")
            phrase = expression[position + 1 : end]
            if not phrase:
                raise LogQueryError("A quoted phrase cannot be empty.")
            tokens.append(("PHRASE", phrase))
            position = end + 1
            continue

        end = position
        while (
            end < len(expression)
            and not expression[end].isspace()
            and expression[end] not in '()"'
        ):
            end += 1
        value = expression[position:end]
        operator = value.upper()
        tokens.append(
            (operator, operator)
            if operator in {"AND", "OR", "NOT"}
            else ("TERM", value)
        )
        position = end
    return tokens


class _LogQueryParser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.position = 0

    def parse(self):
        if not self.tokens:
            raise LogQueryError("Enter a search expression.")
        expression = self._or_expression()
        if self.position != len(self.tokens):
            raise LogQueryError(f"Unexpected token '{self.tokens[self.position][1]}'.")
        return expression

    def _or_expression(self):
        expression = self._and_expression()
        while self._accept("OR"):
            expression = ("OR", expression, self._and_expression())
        return expression

    def _and_expression(self):
        expression = self._not_expression()
        while self._accept("AND"):
            expression = ("AND", expression, self._not_expression())
        return expression

    def _not_expression(self):
        if self._accept("NOT"):
            return ("NOT", self._not_expression())
        return self._primary()

    def _primary(self):
        if self._accept("("):
            expression = self._or_expression()
            if not self._accept(")"):
                raise LogQueryError("A closing parenthesis is missing.")
            return expression
        if self.position >= len(self.tokens):
            raise LogQueryError("A search criterion is missing.")

        token_type, value = self.tokens[self.position]
        if token_type == "PHRASE":
            self.position += 1
            return ("phrase", value)
        if token_type == "TERM":
            self.position += 1
            return _criterion(value)
        raise LogQueryError(f"Unexpected token '{value}'.")

    def _accept(self, token_type):
        if (
            self.position < len(self.tokens)
            and self.tokens[self.position][0] == token_type
        ):
            self.position += 1
            return True
        return False


def _criterion(value):
    lowered = value.lower()
    if lowered in {"info", "warning", "error"}:
        return ("level", lowered.upper())
    if ":" not in value:
        return ("word", value)

    field, field_value = value.split(":", 1)
    field = field.lower()
    if field == "word":
        if not field_value:
            raise LogQueryError("word: requires a value.")
        return ("word", field_value)
    if field not in {"before", "after"}:
        raise LogQueryError(f"Unsupported field '{field}'.")
    if not field_value:
        raise LogQueryError(f"{field}: requires a timestamp.")
    try:
        timestamp = datetime.fromisoformat(field_value)
    except ValueError:
        raise LogQueryError(f"{field}: requires a valid ISO-8601 timestamp.") from None
    if "T" not in field_value or timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise LogQueryError(
            f"{field}: requires a timezone-aware ISO-8601 timestamp."
        )
    return (field, timestamp.isoformat())


def parse_log_query(expression):
    return _LogQueryParser(tokenize_log_query(expression)).parse()


def build_elasticsearch_query(expression):
    query, clause_type = _compile(parse_log_query(expression))
    if clause_type == "filter":
        return {"bool": {"filter": [query]}}
    return query


def _compile(expression):
    kind = expression[0]
    if kind == "word":
        return {"match": {"message": expression[1]}}, "query"
    if kind == "phrase":
        return {"match_phrase": {"message": expression[1]}}, "query"
    if kind == "level":
        return {"term": {"level": expression[1]}}, "filter"
    if kind in {"before", "after"}:
        operator = "lt" if kind == "before" else "gt"
        return {"range": {"timestamp": {operator: expression[1]}}}, "filter"
    if kind == "NOT":
        child, _clause_type = _compile(expression[1])
        return {"bool": {"must_not": [child]}}, "filter"

    left, left_type = _compile(expression[1])
    right, right_type = _compile(expression[2])
    if kind == "AND":
        boolean = {}
        for query, clause_type in ((left, left_type), (right, right_type)):
            key = "filter" if clause_type == "filter" else "must"
            boolean.setdefault(key, []).append(query)
        result_type = "query" if "must" in boolean else "filter"
        return {"bool": boolean}, result_type

    should = []
    for query, clause_type in ((left, left_type), (right, right_type)):
        should.append(
            {"bool": {"filter": [query]}} if clause_type == "filter" else query
        )
    result_type = "query" if "query" in {left_type, right_type} else "filter"
    return {"bool": {"should": should, "minimum_should_match": 1}}, result_type


def get_elasticsearch_client():
    return Elasticsearch(settings.ELASTICSEARCH_URL)


def search_logs(query):
    try:
        response = get_elasticsearch_client().search(
            index=settings.ELASTICSEARCH_LOG_INDEX,
            query=query,
            size=100,
            sort=[
                {"_score": {"order": "desc"}},
                {"timestamp": {"order": "desc", "unmapped_type": "date"}},
            ],
        )
        results = []
        for hit in response["hits"]["hits"]:
            result = dict(hit.get("_source", {}))
            result["score"] = hit.get("_score")
            results.append(result)
        return results
    except Exception:
        raise LogSearchUnavailable from None


def parse_log_line(line):
    match = LOG_LINE.fullmatch(line)
    if not match:
        raise ValueError("Invalid application log line.")
    try:
        timestamp = datetime.strptime(match["timestamp"], "%Y-%m-%dT%H:%M:%S%z")
    except ValueError:
        raise ValueError("Invalid application log timestamp.") from None
    return {
        "timestamp": timestamp.isoformat(),
        "level": match["level"],
        "logger": match["logger"],
        "message": match["message"],
    }


def _read_checkpoint(path):
    try:
        checkpoint = json.loads(path.read_text(encoding="utf-8"))
        return {
            "device": int(checkpoint["device"]),
            "inode": int(checkpoint["inode"]),
            "offset": int(checkpoint["offset"]),
        }
    except FileNotFoundError:
        return None
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        raise ValueError("Invalid log checkpoint.") from None


def _write_checkpoint(path, checkpoint):
    temporary = path.with_name(f"{path.name}.tmp.checkpoint")
    temporary.write_text(json.dumps(checkpoint), encoding="utf-8")
    os.replace(temporary, path)


def _ensure_log_index(client):
    if not client.indices.exists(index=settings.ELASTICSEARCH_LOG_INDEX):
        client.indices.create(
            index=settings.ELASTICSEARCH_LOG_INDEX,
            mappings={
                "properties": {
                    "timestamp": {"type": "date"},
                    "level": {"type": "keyword"},
                    "logger": {"type": "keyword"},
                    "message": {"type": "text"},
                }
            },
        )


def ship_log_batch(log_path, checkpoint_path, client=None, bulk_function=None):
    log_path = Path(log_path)
    checkpoint_path = Path(checkpoint_path)
    checkpoint = _read_checkpoint(checkpoint_path)

    try:
        log_file = log_path.open("rb")
    except FileNotFoundError:
        return 0

    with log_file:
        stat = os.fstat(log_file.fileno())
        identity = (stat.st_dev, stat.st_ino)
        offset = 0
        if (
            checkpoint
            and (checkpoint["device"], checkpoint["inode"]) == identity
            and checkpoint["offset"] <= stat.st_size
        ):
            offset = checkpoint["offset"]
        log_file.seek(offset)

        actions = []
        successful_offset = offset
        while True:
            line_offset = log_file.tell()
            raw_line = log_file.readline()
            if not raw_line or not raw_line.endswith(b"\n"):
                break
            line = raw_line[:-1].removesuffix(b"\r").decode("utf-8")
            document = parse_log_line(line)
            document_id = hashlib.sha256(
                f"{identity[0]}:{identity[1]}:{line_offset}:".encode() + raw_line
            ).hexdigest()
            actions.append(
                {
                    "_index": settings.ELASTICSEARCH_LOG_INDEX,
                    "_id": document_id,
                    "_source": document,
                }
            )
            successful_offset = log_file.tell()

    if not actions:
        return 0

    client = client or get_elasticsearch_client()
    _ensure_log_index(client)
    (bulk_function or bulk)(client, actions)
    _write_checkpoint(
        checkpoint_path,
        {"device": identity[0], "inode": identity[1], "offset": successful_offset},
    )
    return len(actions)
