from __future__ import annotations

import time

from .incidents import STATE
from .tracing import get_langfuse_client, observe

CORPUS = {
    "refund": ["Refunds are available within 7 days with proof of purchase."],
    "monitoring": ["Metrics detect incidents, logs identify affected requests, traces localize the root cause."],
    "policy": ["Do not expose PII in logs. Use sanitized summaries only."],
}


@observe(name="retrieval", as_type="retriever", capture_input=False, capture_output=False)
def retrieve(message: str) -> list[str]:
    if STATE["tool_fail"]:
        raise RuntimeError("Vector store timeout")
    if STATE["rag_slow"]:
        time.sleep(2.5)
    lowered = message.lower()
    docs_found = None
    for key, docs in CORPUS.items():
        if key in lowered:
            docs_found = docs
            break
    if docs_found is None:
        docs_found = ["No domain document matched. Use general fallback answer."]

    client = get_langfuse_client()
    if hasattr(client, "update_current_span") and callable(client.update_current_span):
        client.update_current_span(metadata={"doc_count": len(docs_found)})

    return docs_found
