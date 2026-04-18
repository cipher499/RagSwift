# specs/generation.md — Phase 1

> Generation step. Reads `CLAUDE.md` §7 (Model: `gpt-4o-mini`), §10 (Failure Philosophy).

## 1. Entry Point

```python
async def generate(
    question: str,
    semantic_hits: list[Hit],          # from specs/retrieval.md; may be empty
    chat_history: list[Message],       # last 6 messages, oldest first, EXCLUDING current
) -> AsyncIterator[str]: ...            # yields answer tokens
```

Behavior:

| Condition | Behavior |
|---|---|
| `semantic_hits` non-empty | LLM call with full context; see §3–4. |
| `semantic_hits` empty | Yield canned "cannot answer" message. No LLM call. |

Phase 1 has no router, so no `refuse` or `direct_answer` branches.

## 2. Canned Message (verbatim)

```
I cannot answer this question from your uploaded documents.
```

Emit as a single `token` event containing the full string.

## 3. Context Assembly

Semantic hits come in order (best first). Build context as:

```
[1] filename=handbook.pdf · p.12
<chunk text>

[2] filename=policy.md
<chunk text>

... (up to 10 entries in Phase 1) ...
```

Rules:
- Markers `[1]` through `[N]` are 1-indexed, matching `semantic_hits[0]` through `[N-1]`.
- Header line per passage: `filename=<filename>` then `· p.<source_page>` if present.
- Blank line between header and chunk text; blank line between passages.
- Do NOT truncate chunk text.

## 4. Prompt

Load `prompts/generation.txt` once at startup. Format:

```python
prompt_text = GENERATION_TEMPLATE.format(
    context=context_block,
    history=format_history(chat_history),
    question=question,
)
```

`format_history` renders the 6-turn window as:

```
User: <content>
Assistant: <content>
...
```

Skip any assistant turn whose `content` starts with the canned "cannot answer" string (match exactly).

### 4.1 LLM Call

```python
from openai import AsyncOpenAI

stream = await AsyncOpenAI().chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": prompt_text}],
    stream=True,
    temperature=0.2,
    max_tokens=1024,
)
```

Use OpenAI SDK directly (per `CLAUDE.md` §8). Do NOT use LlamaIndex LLM wrappers.

## 5. Citation Format

The prompt instructs the model to cite with `[1]`, `[2]`, ..., `[N]` inline. Rules:

- Valid indices in Phase 1: 1 to `len(semantic_hits)` (up to 10).
- Do NOT post-process, strip, or validate citations at generation time.
- If the model cites `[N]` where `N > len(semantic_hits)`, let it render as plain text. Log `citation_out_of_range=True` in the trace.
- Zero citations in answer is allowed. Record `citations_present=False`.

## 6. Streaming

Yield each delta string from the OpenAI stream as it arrives. The API layer wraps each yielded string in an SSE `token` event (per `specs/api.md`).

Rules:
- Do NOT yield empty strings.
- Do NOT buffer deltas.
- On mid-stream exception: yield `\n\n[Generation interrupted]`, log ERROR, terminate cleanly. Persist whatever partial answer was produced.

## 7. Persistence

After stream ends (successfully or with interruption marker), the API layer persists:

- `Message` row: `role="assistant"`, `content=<full streamed text>`, `trace_id=<uuid>`.
- `Trace` row: `original_query`, `rewritten_query`, `semantic_hits_json`, `final_answer`, `latency_ms`, `langsmith_run_url`, `flags` (dict of bools).

Store hit list as JSON: `json.dumps([hit.model_dump() for hit in semantic_hits])`.

## 8. LangSmith Span

```
generate
├── model=gpt-4o-mini
├── num_context_chunks=<len(semantic_hits)>
├── history_turns=<len(chat_history)>
├── prompt_tokens (from usage)
├── completion_tokens (from usage)
├── citations_present (bool)
```

If branch was "cannot answer" (empty hits), still open a `generate` span with `skipped=True, reason="no_hits"`.

## 9. Success Criteria (Phase 1)

- Time-to-first-token ≤ 2s from start of `generate` span on a typical question.
- Every assistant message has exactly one `Trace` row.
- Canned message appears verbatim — never paraphrased.
- The LLM is never called with empty `question` or when `semantic_hits` is empty.

## 10. Edge Cases

| Case | Behavior |
|---|---|
| `question` is whitespace only | Reject at API layer with 400. Generation never runs. |
| A hit has empty `text` | Skip when building context. If all empty, treat as empty hits → canned message. |
| Chat history contains the canned "cannot answer" as assistant content | Skip that turn in `format_history`. |
| OpenAI 5xx | One retry after 2s. Second failure: yield `\n\n[Generation interrupted]`. |
| Client disconnects mid-stream | Continue server-side until stream ends; persist message; client refetches on reconnect. |

## 11. What Phase 1 Does NOT Include

- No refusal branch.
- No direct-answer branch.
- No reranked context (uses raw semantic top-10).
- No citation validation or repair.
- No answer caching.