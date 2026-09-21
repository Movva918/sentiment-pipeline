"""FinBERT sentiment scoring service for the sentiment pipeline."""

import time
from functools import lru_cache

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch
import torch.nn.functional as F

app = FastAPI(title="FinBERT Scoring Service", version="1.0.0")

LABELS = ["positive", "negative", "neutral"]
CONFIDENCE_THRESHOLD = 0.3


class ScoreRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Article text to score")


class ScoreResponse(BaseModel):
    label: str
    confidence: float
    probabilities: dict[str, float]
    low_confidence: bool
    processing_time_ms: float


@lru_cache(maxsize=1)
def get_model():
    """Load model and tokenizer once, cache in memory."""
    tokenizer = AutoTokenizer.from_pretrained("/app/model")
    model = AutoModelForSequenceClassification.from_pretrained("/app/model")
    model.eval()
    return tokenizer, model


@app.on_event("startup")
def warmup():
    """Load model into memory on startup so first request isn't slow."""
    get_model()


@app.post("/score", response_model=ScoreResponse)
def score_text(request: ScoreRequest):
    """Score a single piece of text for financial sentiment."""
    start = time.time()

    tokenizer, model = get_model()

    # Truncate to 512 tokens as per design spec
    inputs = tokenizer(
        request.text,
        return_tensors="pt",
        truncation=True,
        max_length=512,
        padding=True,
    )

    with torch.no_grad():
        outputs = model(**inputs)

    probabilities = F.softmax(outputs.logits, dim=1).squeeze()
    confidence, predicted = torch.max(probabilities, dim=0)

    label = LABELS[predicted.item()]
    confidence_val = round(confidence.item(), 4)

    processing_time = round((time.time() - start) * 1000, 2)

    return ScoreResponse(
        label=label,
        confidence=confidence_val,
        probabilities={
            LABELS[i]: round(probabilities[i].item(), 4)
            for i in range(len(LABELS))
        },
        low_confidence=confidence_val < CONFIDENCE_THRESHOLD,
        processing_time_ms=processing_time,
    )


@app.get("/health")
def health():
    """Health check endpoint for Cloud Run."""
    try:
        get_model()
        return {"status": "healthy", "model": "ProsusAI/finbert"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))
