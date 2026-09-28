"""
Example client for the Laya Local Server.

Shows how to call the /classify endpoint from Python.
Also usable as a reference for implementing the browser extension's
background-script fetch call.
"""

import requests
import sys

SERVER_URL = "http://localhost:8765"


def classify(text: str, question: str = "") -> dict:
    """Send text to the Laya server and get back a probability."""
    resp = requests.post(
        f"{SERVER_URL}/classify",
        json={"text": text, "question": question},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def main():
    print("Laya Local Client — Example")
    print("=" * 50)

    # Check server health
    try:
        health = requests.get(f"{SERVER_URL}/health", timeout=5).json()
        print(f"Server: {health['status']}")
        print(f"Model loaded: {health['model_loaded']}")
        if health['model_loaded']:
            print(f"Providers: {health['model_info'].get('providers', [])}")
            print(f"RAM: {health['process_ram_mb']} MB")
        print()
    except requests.ConnectionError:
        print("ERROR: Cannot connect to Laya server at", SERVER_URL)
        print("Start it with: uvicorn laya_server:app --host 127.0.0.1 --port 8765")
        sys.exit(1)

    # Classify some text
    examples = [
        (
            "Photosynthesis is the process by which green plants use sunlight "
            "to synthesize foods from carbon dioxide and water.",
            "Is this about biology?",
        ),
        (
            "The French Revolution began in 1789 and led to the rise of Napoleon "
            "Bonaparte. It fundamentally changed French political and social structure.",
            "Is this about history?",
        ),
    ]

    for text, question in examples:
        print(f"Q: {question}")
        print(f"Text: {text[:80]}...")
        result = classify(text, question)
        print(f"  P(true): {result['probability']}")
        print(f"  Time:    {result['inference_time_ms']} ms")
        print()

    # Show health again to compare RAM
    health = requests.get(f"{SERVER_URL}/health").json()
    print(f"Final RAM usage: {health['process_ram_mb']} MB")


if __name__ == "__main__":
    main()
