"""Fixture-only verifier. No real identity or external trust source is accepted."""

import hashlib
import itertools
import json


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _sha(value):
    return hashlib.sha256(value).hexdigest()


# Immutable toy reference, independent of each submitted projection and receipt.
_PARTS = ("H", "D", "W", "S")
_CLASSES = ("parent", "legal_child", "played_position", "opening_root", "group_membership")
_KINDS = ("parent_child", "game_position", "game_opening", "pair_game", "game_group")
_TOKENS = {
    "H": ("hparent", "hchild", "hplayed", "hopen", "hgroup"),
    "D": ("dparent", "dchild", "dplayed", "dopen", "dgroup"),
    "W": ("wparent", "wchild", "wplayed", "wopen", "wgroup"),
    "S": ("sparent", "schild", "splayed", "sopen", "sgroup"),
}
_POS = {token: token for part in _PARTS for token in _TOKENS[part][:4]}
_POS["dchild"] = "hparent"
_GROUP = {"hgroup": "sharedgroup", "dgroup": "sharedgroup", "wgroup": "wgroup", "sgroup": "sgroup"}


def _occurrences(part):
    return [{"id": part + str(i), "source_ref": part + "ref" + str(i), "class": cls, "token": token}
            for i, (cls, token) in enumerate(zip(_CLASSES, _TOKENS[part]))]


def _links(part):
    return [
        {"kind": "parent_child", "from_ref": part + "ref0", "to_ref": part + "ref1", "qualifier": "move"},
        {"kind": "game_position", "from_ref": part + "game1", "to_ref": part + "ref2", "qualifier": "ply0"},
        {"kind": "game_opening", "from_ref": part + "game1", "to_ref": part + "ref3", "qualifier": "open"},
        {"kind": "pair_game", "from_ref": part + "pair", "to_ref": part + "game1", "qualifier": "first"},
        {"kind": "pair_game", "from_ref": part + "pair", "to_ref": part + "game2", "qualifier": "second"},
        {"kind": "game_group", "from_ref": part + "game1", "to_ref": part + "ref4", "qualifier": "member"},
        {"kind": "game_group", "from_ref": part + "game2", "to_ref": part + "ref4", "qualifier": "member"},
    ]


_SPEC = {"profile": "identity-spec.fixture.v1",
         "position_aliases": [{"token": k, "key": v} for k, v in sorted(_POS.items())],
         "group_aliases": [{"token": k, "key": v} for k, v in sorted(_GROUP.items())],
         "vectors": [{"space": "position", "left": "hparent", "right": "dchild", "equal": True},
                     {"space": "position", "left": "hparent", "right": "hchild", "equal": False},
                     {"space": "group", "left": "hgroup", "right": "dgroup", "equal": True},
                     {"space": "group", "left": "hgroup", "right": "wgroup", "equal": False}]}
_REFERENCE = {p: {"occurrences": _occurrences(p), "links": _links(p)} for p in _PARTS}
_REFERENCE_HASH = _sha(_json(_REFERENCE))
_SPEC_HASH = _sha(_json(_SPEC))
_SOURCES = [{"id": p, "partition": p, "attempt": "attempt" + p, "producer_id": "producer" + p,
             "input_manifest_sha256": _sha(("manifest" + p).encode("ascii")),
             "cells": [{"class": c, "requirement": "REQUIRED", "basis_ref": "basis" + p + c} for c in _CLASSES]}
            for p in _PARTS]
_SCOPE = {"profile": "scope.fixture.v1", "reference_sha256": _REFERENCE_HASH,
          "identity_spec_sha256": _SPEC_HASH, "sources": _SOURCES}


class _Reject(Exception):
    pass


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise _Reject("DUPLICATE_KEY")
        result[key] = value
    return result


def _read(raw):
    if type(raw) is not bytes:
        raise _Reject("INPUT_NOT_BYTES")
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                          parse_float=lambda _: (_ for _ in ()).throw(_Reject("INVALID_NUMBER")),
                          parse_constant=lambda _: (_ for _ in ()).throw(_Reject("INVALID_NUMBER")))
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
        raise _Reject("INVALID_JSON") from None


def _object(value, fields, profile=None):
    if type(value) is not dict or set(value) != set(fields):
        raise _Reject("SCHEMA")
    if profile is not None and value.get("profile") != profile:
        raise _Reject("VERSION")


def _list(value):
    if type(value) is not list:
        raise _Reject("SCHEMA")


def _token(value):
    if type(value) is not str or not value or not value.isascii() or not value.isalnum():
        raise _Reject("INVALID_TOKEN")


def _count(value):
    if type(value) is not int or value < 0:
        raise _Reject("INVALID_COUNT")


def _tally(items, field):
    result = {}
    for item in items:
        result[item[field]] = result.get(item[field], 0) + 1
    return result


def _set_info(values):
    keys = sorted(values)
    return {"count": len(keys), "sha256": _sha(_json(keys))}


def verify_fixture(scope_bytes, spec_bytes, projection_bytes, receipt_bytes):
    """Verify fixed synthetic fixtures only; returns canonical JSON bytes.

    projection_bytes and receipt_bytes are dictionaries keyed by fixed toy IDs.
    This function accepts no paths, caller-defined inventory, or real identities.
    """
    hashes = {}
    report = {"profile": "verification.fixture.v1", "verifier_version": "1", "input_sha256": hashes,
              "status": "FIXTURE_REJECTED", "errors": [], "unions": None, "intersections": None}
    try:
        if type(projection_bytes) is not dict or type(receipt_bytes) is not dict:
            raise _Reject("INPUT_COLLECTION")
        for name, raw in (("scope", scope_bytes), ("identity_spec", spec_bytes)):
            if type(raw) is bytes:
                hashes[name] = _sha(raw)
        for label, collection in (("projection", projection_bytes), ("receipt", receipt_bytes)):
            for key in sorted(collection):
                if type(key) is not str or key not in _PARTS:
                    raise _Reject("SOURCE_SET")
                if type(collection[key]) is bytes:
                    hashes[label + ":" + key] = _sha(collection[key])
        if set(projection_bytes) != set(_PARTS) or set(receipt_bytes) != set(_PARTS):
            raise _Reject("SOURCE_SET")
        scope, spec = _read(scope_bytes), _read(spec_bytes)
        _object(scope, ("profile", "reference_sha256", "identity_spec_sha256", "sources"), "scope.fixture.v1")
        _object(spec, ("profile", "position_aliases", "group_aliases", "vectors"), "identity-spec.fixture.v1")
        if scope != _SCOPE or spec != _SPEC or _sha(spec_bytes) != _SPEC_HASH:
            raise _Reject("REFERENCE_MISMATCH")
        spaces = {p: {"positions": set(), "groups": set()} for p in _PARTS}
        for source in _SOURCES:
            p = source["id"]
            projection, receipt = _read(projection_bytes[p]), _read(receipt_bytes[p])
            _object(projection, ("profile", "source_id", "identity_spec_sha256", "occurrences", "links"), "projection.fixture.v1")
            _object(receipt, ("profile", "source_id", "attempt", "producer_id", "input_manifest_sha256", "reference_sha256", "projection_sha256", "projection_bytes", "occurrence_counts", "link_counts", "omissions"), "coverage_receipt.fixture.v1")
            _list(projection["occurrences"]); _list(projection["links"])
            if projection["source_id"] != p or projection["identity_spec_sha256"] != _SPEC_HASH:
                raise _Reject("PROJECTION_IDENTITY")
            for occurrence in projection["occurrences"]:
                _object(occurrence, ("id", "source_ref", "class", "token"))
                if occurrence["class"] not in _CLASSES: raise _Reject("SCHEMA")
                for key in ("id", "source_ref", "token"): _token(occurrence[key])
            for link in projection["links"]:
                _object(link, ("kind", "from_ref", "to_ref", "qualifier"))
                for value in link.values():
                    if type(value) is not str: raise _Reject("INVALID_TOKEN")
                    _token(value.replace("_", ""))
            for key in ("projection_bytes", "omissions"): _count(receipt[key])
            for key in ("occurrence_counts", "link_counts"):
                if type(receipt[key]) is not dict: raise _Reject("SCHEMA")
                for value in receipt[key].values(): _count(value)
            if (receipt["source_id"] != p or receipt["attempt"] != source["attempt"] or
                receipt["producer_id"] != source["producer_id"] or receipt["input_manifest_sha256"] != source["input_manifest_sha256"] or
                receipt["reference_sha256"] != _REFERENCE_HASH or receipt["projection_sha256"] != _sha(projection_bytes[p]) or
                receipt["projection_bytes"] != len(projection_bytes[p]) or receipt["omissions"] != 0 or
                receipt["occurrence_counts"] != _tally(projection["occurrences"], "class") or
                receipt["link_counts"] != _tally(projection["links"], "kind")):
                raise _Reject("RECEIPT_MISMATCH")
            for field in ("occurrences", "links"):
                actual = [_json(item) for item in projection[field]]
                expected = [_json(item) for item in _REFERENCE[p][field]]
                if len(actual) != len(set(actual)) or sorted(actual) != sorted(expected):
                    raise _Reject("COVERAGE_MISMATCH")
            for occurrence in projection["occurrences"]:
                if occurrence["class"] == "group_membership":
                    spaces[p]["groups"].add(_GROUP[occurrence["token"]])
                else:
                    spaces[p]["positions"].add(_POS[occurrence["token"]])
        unions = {kind: _set_info(set().union(*(spaces[p][kind] for p in _PARTS))) for kind in ("positions", "groups")}
        intersections = {a + ":" + b: {kind: _set_info(spaces[a][kind] & spaces[b][kind])
                                           for kind in ("positions", "groups")}
                         for a, b in itertools.combinations(_PARTS, 2)}
        report.update(status="FIXTURE_CONFORMANT", unions=unions, intersections=intersections)
    except (_Reject, KeyError, TypeError, ValueError) as error:
        report["errors"] = [{"code": str(error) if isinstance(error, _Reject) else "INVALID_INPUT", "reference": "bundle"}]
    return _json(report)

