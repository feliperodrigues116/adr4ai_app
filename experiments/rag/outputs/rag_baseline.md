# ADR4AI RAG Baseline

Requirements → BAAI/bge-small-en-v1.5 → Vector Retrieval Top-15 → BAAI/bge-reranker-base → Top-5

Dataset: data/user_histories_EN.csv  
Systems: 4  
User stories: 12  
Acceptance criteria: 35

Embedding: BAAI/bge-small-en-v1.5  
Vector retrieval: Top-15  
Reranker: BAAI/bge-reranker-base  
Final ranking: Top-5

The user_story_id and acceptance_criterion_id values were explicitly included in the retrieval input in bracketed form for traceability. Requirement text and IDs were preserved as stored in the dataset.

The previous LLM selection was exploratory and is excluded from the retrieval/reranking baseline used in the scientific comparison. This cleanup preserved the existing rankings without rerunning any model.

| user_story_id | top5_ids |
|---|---|
| SYS01-US01 | 002;017;063;016;029 |
| SYS01-US02 | 003;002;017;024;026 |
| SYS01-US03 | 031;003;002;036;024 |
| SYS02-US01 | 002;031;020;017;064 |
| SYS02-US02 | 002;031;033;026;017 |
| SYS02-US03 | 002;036;017;016;033 |
| SYS03-US01 | 010;063;002;025;034 |
| SYS03-US02 | 002;016;030;017;063 |
| SYS03-US03 | 002;038;025;016;010 |
| SYS04-US01 | 002;039;069;041;042 |
| SYS04-US02 | 016;017;015;002;026 |
| SYS04-US03 | 017;049;002;053;048 |
