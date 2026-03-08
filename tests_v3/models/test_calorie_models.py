from datetime import datetime

import pytest

from backend.models import CalorieRecord


class TestCalorieModels:
    def test_calorie_record_crud(self, v3_db_session):
        row = CalorieRecord(
            user_id="U_TEST",
            uploaded_at=datetime(2026, 3, 5, 7, 0, 0),
            food_name="鶏むね肉",
            calorie=320,
            llm_raw_response_json='{"schema_version":"calorie_v1","items":[{"food_name":"鶏むね肉","calorie":320}]}',
            provider="openai",
            model="gpt-4o-mini",
        )
        v3_db_session.add(row)
        v3_db_session.commit()

        loaded = v3_db_session.query(CalorieRecord).filter_by(id=row.id).one()
        assert loaded.user_id == "U_TEST"
        assert loaded.food_name == "鶏むね肉"
        assert loaded.calorie == 320
        assert loaded.provider == "openai"

    def test_calorie_record_provider_check(self, v3_db_session):
        row = CalorieRecord(
            user_id="U_TEST",
            uploaded_at=datetime(2026, 3, 5, 7, 0, 0),
            food_name="不明",
            calorie=0,
            llm_raw_response_json="{}",
            provider="invalid",
            model=None,
        )
        v3_db_session.add(row)
        with pytest.raises(Exception):
            v3_db_session.commit()
        v3_db_session.rollback()
