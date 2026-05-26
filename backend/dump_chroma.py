from app.utils.chroma_store import chroma_db

collections = ["banking_data", "investment_data", "financial_tips"]

for col_name in collections:
    col = chroma_db._get_or_create_collection(col_name)
    results = col.get(include=["documents", "metadatas"])

    ids       = results["ids"]
    documents = results["documents"]
    metadatas = results["metadatas"]

    print("=" * 70)
    print("COLLECTION: {}  ({} documents)".format(col_name.upper(), len(ids)))
    print("=" * 70)

    for i, (doc_id, text, meta) in enumerate(zip(ids, documents, metadatas)):
        title   = meta.get("title",  "N/A")
        source  = meta.get("source", "N/A")
        ingested = meta.get("ingested_at", "N/A")
        preview = text[:120].strip().replace("\n", " ")
        print("  [{}] Title   : {}".format(i + 1, title))
        print("       Source  : {}".format(source))
        print("       Ingested: {}".format(ingested))
        print("       Preview : {}...".format(preview))
        print()

    print()
