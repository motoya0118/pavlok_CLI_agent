import argparse
import os

import requests
from dotenv import load_dotenv

load_dotenv()


def _stimulus_value(value: str) -> int:
    parsed_value = int(value)
    if 1 <= parsed_value <= 100:
        return parsed_value
    raise argparse.ArgumentTypeError("stimulus_value must be between 1 and 100 (inclusive).")


def call(stimulus_type: str, stimulus_value: int):
    url = "https://api.pavlok.com/api/v5/stimulus/send"
    api_key = os.getenv("PAVLOK_API_KEY")
    if not api_key:
        raise SystemExit("PAVLOK_API_KEY is not set. Add it to .env or the environment.")

    payload = {
        "stimulus": {
            "stimulusType": stimulus_type,
            "stimulusValue": stimulus_value,
        }
    }
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    response = requests.post(url, json=payload, headers=headers)
    print(response.text)


def main():
    parser = argparse.ArgumentParser(
        description="Send a Pavlok stimulus via the API.",
    )
    parser.add_argument(
        "stimulus_type",
        choices=["vibe", "beep", "zap"],
        help="Type of stimulus to send (vibe, beep, or zap).",
    )
    parser.add_argument(
        "stimulus_value",
        type=_stimulus_value,
        help="Stimulus value as an integer between 1 and 100.",
        metavar="stimulus_value",
    )
    args = parser.parse_args()

    call(args.stimulus_type, args.stimulus_value)


if __name__ == "__main__":
    main()
