from huggingface_hub import snapshot_download


path = snapshot_download(
    repo_id="twolven/Qwen3.8-27B-abliterated-AWQ-MTP",
    local_dir="/home/yi/models/Qwen3.8-27B-abliterated-AWQ-MTP",
    max_workers=2,
    ignore_patterns=["model.safetensors"],
)
print(f"DOWNLOAD_COMPLETE={path}")
