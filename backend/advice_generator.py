"""Meal advice generator using OpenAI Structured Outputs."""

from pydantic import BaseModel

from backend.llm_client import LLMClientConfig

# JSON Schema for OpenAI Structured Outputs (must have additionalProperties: false)
_MEAL_ADVICE_SCHEMA = {
    "type": "object",
    "properties": {
        "advice": {
            "type": "string",
            "description": "Meal advice text (1-2 sentences)",
        },
    },
    "required": ["advice"],
    "additionalProperties": False,
}


class MealAdviceRequest(BaseModel):
    """Request schema for meal advice."""

    advice: str

    @classmethod
    def model_json_schema(cls) -> dict:
        """Return JSON schema compatible with OpenAI Structured Outputs."""
        return _MEAL_ADVICE_SCHEMA


class AdviceGenerator:
    """Generate meal advice based on remaining intake.

    Uses OpenAI Structured Outputs to generate character-specific advice.
    Supports both OpenAI and Gemini (via OpenAI-compatible endpoint) providers.
    """

    def __init__(
        self, character: str = "うる星やつらのラムちゃん", provider: str = "openai"
    ) -> None:
        """Initialize advice generator.

        Args:
            character: Character name for tone of advice
            provider: Provider to use ("openai" or "gemini")
        """
        self.character = character
        config = LLMClientConfig(provider)
        self.client = config.client
        self.model = config.get_model_for_purpose("advice")

    def generate(
        self, remaining: dict[str, float], consumed: dict[str, float], goal: dict[str, float]
    ) -> str:
        """Generate advice based on current intake status.

        Args:
            remaining: Dict with remaining calorie, protein_g, fat_g, carbs_g
            consumed: Dict with consumed calorie, protein_g, fat_g, carbs_g
            goal: Dict with goal daily_calorie_goal, protein_g, fat_g, carbs_g

        Returns:
            Generated advice text (1-2 sentences)
        """
        remaining_calorie = remaining.get("calorie", 0)
        remaining_protein = remaining.get("protein_g", 0)

        # 状態判定
        if remaining_calorie == 0 and remaining_protein == 0:
            status = "goal_achieved"
        elif remaining_calorie < 500 or remaining_protein < 20:
            status = "running_low"
        elif consumed.get("calorie", 0) > goal.get("daily_calorie_goal", 2000):
            status = "exceeded"
        else:
            status = "on_track"

        # キャラクターに応じたsystem prompt
        character_prompts = {
            "うる星やつらのラムちゃん": (
                "あなたは『うる星やつら』のラムちゃんです。"
                "性格：明るく、おっとりしていて、ちょっと悪戯好き。"
                "一人称：「あたち」"
                "語尾：「〜だっちゃ」「〜なの」「〜ね」"
                "ユーザーを「だっちゃ」と呼び、励ますことが好きです。"
            ),
            "コーチ": (
                "あなたはプロのコーチです。"
                "的確で短い言葉で選手を指導します。"
                "一人称：「私」"
                "ユーザーの目標達成をサポートします。"
            ),
            "標準": (
                "あなたは優しくサポートするAIアシスタントです。ユーザーの健康管理を手伝います。"
            ),
        }

        system_prompt = character_prompts.get(self.character, character_prompts["標準"])

        # 状態に応じた指示
        status_instructions = {
            "goal_achieved": "目標値をぴったり達成しました！素晴らしい成果を褒めてください。",
            "running_low": "残り摂取許容値が少なくなっています。注意を促してください。",
            "exceeded": "目標値を超過しています。次は気をつけるように励ましてください。",
            "on_track": "順調に進んでいます。1-2文の励ましの言葉をかけてください。",
        }

        user_instruction = status_instructions.get(status, "")

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": (
                        f"現在の摂取状況:\n"
                        f"カロリー: {consumed.get('calorie', 0)} / {goal.get('daily_calorie_goal', 2000)} kcal "
                        f"(残り: {remaining_calorie} kcal)\n"
                        f"タンパク質: {consumed.get('protein_g', 0)} / {goal.get('protein_g', 100)} g "
                        f"(残り: {remaining_protein} g)\n\n"
                        f"{user_instruction}\n\n"
                        f"1-2文で、キャラクターの口調でアドバイスを出力してください。"
                    ),
                },
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "meal_advice",
                    "strict": True,
                    "schema": MealAdviceRequest.model_json_schema(),
                },
            },
        )

        content = response.choices[0].message.content
        result = MealAdviceRequest.model_validate_json(content)
        return result.advice
