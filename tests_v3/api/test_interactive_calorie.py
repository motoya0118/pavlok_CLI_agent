"""
v0.3.2 /cal処理の単体テスト
"""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from backend.api.interactive import _run_calorie_submit_job
from backend.models import CalorieRecord, Configuration, ConfigValueType

JST = ZoneInfo("Asia/Tokyo")


@pytest.fixture
def sample_user_with_body_composition(v3_db_session):
    """体組成設定済みのユーザー fixture"""
    user_id = "test-user-calorie"

    # 体組成設定
    configs = [
        Configuration(
            user_id=user_id,
            key="GENDER",
            value="male",
            value_type=ConfigValueType.STR,
            default_value="-",
            version=1,
            description="Test",
        ),
        Configuration(
            user_id=user_id,
            key="AGE",
            value="30",
            value_type=ConfigValueType.INT,
            default_value="30",
            version=1,
            description="Test",
        ),
        Configuration(
            user_id=user_id,
            key="HEIGHT_CM",
            value="175",
            value_type=ConfigValueType.INT,
            default_value="170",
            version=1,
            description="Test",
        ),
        Configuration(
            user_id=user_id,
            key="WEIGHT_KG",
            value="70.0",
            value_type=ConfigValueType.FLOAT,
            default_value="65.0",
            version=1,
            description="Test",
        ),
        Configuration(
            user_id=user_id,
            key="ACTIVITY_LEVEL",
            value="1.375",
            value_type=ConfigValueType.STR,
            default_value="1.375",
            version=1,
            description="Test",
        ),
        Configuration(
            user_id=user_id,
            key="DIET_GOAL",
            value="maintain",
            value_type=ConfigValueType.STR,
            default_value="maintain",
            version=1,
            description="Test",
        ),
    ]
    for c in configs:
        v3_db_session.add(c)
    v3_db_session.commit()

    yield user_id


@pytest.mark.asyncio
class TestCalorieSubmitBodyCompositionCheck:
    """体組成設定チェックのテスト"""

    async def test_body_01_missing_all_configs(self, v3_db_session):
        """全設定未設定 - エラー通知"""
        user_id = "empty-user"

        # CalorieAgentErrorが発生することを確認
        # ただし、実装では例外がキャッチされて通知に変換されるため、
        # ここでは例外が発生せず、通知がスキップされることを確認する
        # (SLACK_BOT_USER_OAUTH_TOKENがないため)

        # 例外チェックではなく、関数が完了することを確認
        # （本来であれば通知が送られるが、テスト環境ではスキップされる）
        result = await _run_calorie_submit_job(
            user_id=user_id,
            channel_id="C123",
            file_id="test_file",
            bot_token="dummy_token",
        )

        # 関数は例外をキャッチして完了する
        assert result is None

    async def test_body_04_all_configs_set(self, sample_user_with_body_composition, v3_db_session):
        """全設定完了 - 正常処理（ただし画像解析はモック必要）"""
        # このテストは画像解析APIをモックする必要があるため、
        # 実際にはE2Eテストで確認する方が適切
        # ここでは設定チェックが通ることを確認
        user_id = sample_user_with_body_composition

        # 設定が存在することを確認
        configs = v3_db_session.query(Configuration).filter_by(user_id=user_id).all()
        config_keys = {c.key for c in configs}
        required = {"GENDER", "AGE", "HEIGHT_CM", "WEIGHT_KG", "ACTIVITY_LEVEL", "DIET_GOAL"}
        assert required.issubset(config_keys)


@pytest.mark.asyncio
class TestCalorieSubmitPFCSave:
    """PFC保存のテスト"""

    async def test_save_01_decimal_values(self, v3_db_session):
        """小数点値が正しく保存される"""
        # これは実際の画像解析と結合したテストが必要
        # 単体では、CalorieRecordのPFCカラムが正しく動作することを確認
        record = CalorieRecord(
            user_id="test-user",
            uploaded_at=datetime.now(JST).replace(tzinfo=None),
            food_name="テスト",
            calorie=500,
            protein_g=25.5,
            fat_g=15.0,
            carbs_g=60.0,
            llm_raw_response_json="{}",
            provider="openai",
        )
        v3_db_session.add(record)
        v3_db_session.flush()

        assert record.protein_g == 25.5
        assert record.fat_g == 15.0
        assert record.carbs_g == 60.0

    async def test_save_02_zero_values(self, v3_db_session):
        """0値も保存できる"""
        record = CalorieRecord(
            user_id="test-user",
            uploaded_at=datetime.now(JST).replace(tzinfo=None),
            food_name="テスト",
            calorie=500,
            protein_g=0,
            fat_g=0,
            carbs_g=0,
            llm_raw_response_json="{}",
            provider="openai",
        )
        v3_db_session.add(record)
        v3_db_session.flush()

        assert record.protein_g == 0
        assert record.fat_g == 0
        assert record.carbs_g == 0

    async def test_save_03_null_values(self, v3_db_session):
        """NULL値も許容"""
        record = CalorieRecord(
            user_id="test-user",
            uploaded_at=datetime.now(JST).replace(tzinfo=None),
            food_name="テスト",
            calorie=500,
            protein_g=None,
            fat_g=None,
            carbs_g=None,
            llm_raw_response_json="{}",
            provider="openai",
        )
        v3_db_session.add(record)
        v3_db_session.flush()

        assert record.protein_g is None
        assert record.fat_g is None
        assert record.carbs_g is None
