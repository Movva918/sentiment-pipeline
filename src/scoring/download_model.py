"""Download ProsusAI/finbert at build time so it's baked into the image."""

from transformers import AutoTokenizer, AutoModelForSequenceClassification

MODEL_NAME = "ProsusAI/finbert"
SAVE_PATH = "/app/model"

print(f"Downloading {MODEL_NAME}...")
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
model = AutoModelForSequenceClassification.from_pretrained(MODEL_NAME)

tokenizer.save_pretrained(SAVE_PATH)
model.save_pretrained(SAVE_PATH)
print(f"Model saved to {SAVE_PATH}")
