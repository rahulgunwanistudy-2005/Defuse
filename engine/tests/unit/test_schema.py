from defuse.model.schema import SCHEMA_PATH, ioc_schema_json


def test_committed_schema_matches_the_model() -> None:
    assert SCHEMA_PATH.read_text(encoding="utf-8") == ioc_schema_json(), (
        "run `uv run defuse schema write` and commit engine/defuse/model/ioc.schema.json"
    )
