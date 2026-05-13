import os
import cohere

# 1. Initialize the Cohere Client (automatically picks up COHERE_API_KEY from environment)
co = cohere.ClientV2()

# 2. Simulate the user's question
query = "What is the return policy for sale items?"

# 3. Simulate your Vector DB retrieval output (unordered or weakly ordered chunks)
retrieved_chunks = [
    "Our regular items can be returned within 30 days of purchase with a receipt.",
    "Shipping fees are completely non-refundable for all domestic orders.",
    "Clearance and sale items are final sale and cannot be returned or exchanged.",
    "We offer a 10% discount to all first-time subscribers of our newsletter."
]

try:
    # 4. Execute the Rerank request
    # Use 'rerank-english-v3.0' or 'rerank-multilingual-v3.0' depending on your language
    response = co.rerank(
        model="rerank-english-v3.0",
        query=query,
        documents=retrieved_chunks,
        top_n=2 # Only return the top 2 most relevant chunks to save LLM prompt context space
    )

    # 5. Process and display the re-ordered results
    print(f"User Query: {query}\n")
    print("--- Top Reranked Chunks ---")
    
    for rank, result in enumerate(response.results):
        original_index = result.index
        score = result.relevance_score
        chunk_text = retrieved_chunks[original_index]
        
        print(f"Rank {rank + 1} (Original Index: {original_index}) | Relevance Score: {score:.4f}")
        print(f"Content: {chunk_text}\n")

except Exception as e:
    print(f"An error occurred: {e}")
