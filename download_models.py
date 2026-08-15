from huggingface_hub import snapshot_download


for repo, destination in (
    ("typhoon-ai/typhoon-ocr1.5-2b", "models/Typhoon-OCR-1.5-2B"),
    ("baidu/Unlimited-OCR", "models/Unlimited-OCR"),
):
    print(f"Downloading {repo} ...", flush=True)
    snapshot_download(repo_id=repo, local_dir=destination)

