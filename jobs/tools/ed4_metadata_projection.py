"""Schema-directed JSON reader; excluded values are validated but never decoded."""
import json
import re

STRING = re.compile(r'"(?:[^"\\\x00-\x1f]|\\(?:["\\/bfnrt]|u[0-9a-fA-F]{4}))*"')
ATOM = re.compile(r'(?:-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?|true|false|null)')


def project(raw, schema, decode_leaf=json.loads):
    """None skips a subtree; dict/list select structure; tuples select scalar types.

    Only object keys and scalar leaves explicitly named by the schema are
    decoded. Unknown strings/numbers/booleans are scanned as raw JSON tokens.
    ``decode_leaf`` allows tests to detect any forbidden semantic decoding.
    """
    text = raw.decode('utf-8') if isinstance(raw, bytes) else raw
    position = 0

    def require(ok):
        if not ok:
            raise ValueError('invalid_or_unexpected_metadata_json')

    def whitespace():
        nonlocal position
        while position < len(text) and text[position] in ' \t\r\n':
            position += 1

    def peek():
        whitespace()
        require(position < len(text))
        return text[position]

    def token(pattern):
        nonlocal position
        match = pattern.match(text, position)
        require(match is not None)
        start = position
        position = match.end()
        return start, position

    def value(selected, depth=0):
        nonlocal position
        require(depth < 100)
        character = peek()
        if character == '{':
            require(selected is None or isinstance(selected, dict))
            position += 1
            result = {} if selected is not None else None
            keys = set()
            if peek() == '}':
                position += 1
                return result
            while True:
                require(peek() == '"')
                start, end = token(STRING)
                key = json.loads(text[start:end])
                require(key not in keys)
                keys.add(key)
                require(peek() == ':')
                position += 1
                child = selected.get(key) if selected is not None else None
                parsed = value(child, depth + 1)
                if child is not None:
                    result[key] = parsed
                character = peek()
                position += 1
                if character == '}':
                    return result
                require(character == ',')
        if character == '[':
            require(selected is None or (isinstance(selected, list) and len(selected) == 1))
            position += 1
            result = [] if selected is not None else None
            if peek() == ']':
                position += 1
                return result
            while True:
                parsed = value(selected[0] if selected is not None else None, depth + 1)
                if selected is not None:
                    result.append(parsed)
                character = peek()
                position += 1
                if character == ']':
                    return result
                require(character == ',')
        require(selected is None or isinstance(selected, tuple))
        start, end = token(STRING if character == '"' else ATOM)
        if selected is None:
            return None
        parsed = decode_leaf(text[start:end])
        require(type(parsed) in selected)
        return parsed

    result = value(schema)
    whitespace()
    require(position == len(text))
    return result


IDENTITY = {
    'job_id': (str,), 'attempt_id': (str, type(None)),
    'code_sha': (str, type(None)), 'state': (str,),
    'exit_code': (int, type(None)), 'host': (str,),
}
STATUS = dict(IDENTITY, result_uri=(str, type(None)))
INVENTORY = {'files': [{
    'path': (str,), 'size_bytes': (int,), 'sha256': (str,),
    'declared_cardinality': (int, type(None)),
}]}
