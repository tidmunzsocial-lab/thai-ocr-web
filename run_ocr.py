import argparse
from pathlib import Path

import torch
from transformers import AutoModel, AutoTokenizer


def main() -> None:
    parser = argparse.ArgumentParser(description="Run baidu/Unlimited-OCR on one image.")
    parser.add_argument("image", help="Path to a JPG/PNG image")
    parser.add_argument("--output", default="outputs/ocr", help="Output directory")
    parser.add_argument("--mode", choices=("gundam", "base"), default="gundam")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    model_path = root / "models" / "Unlimited-OCR"
    image_path = Path(args.image).resolve()
    output_path = Path(args.output).resolve()

    if not image_path.is_file():
        raise FileNotFoundError(f"Image not found: {image_path}")
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA GPU is required, but PyTorch cannot access it.")

    output_path.mkdir(parents=True, exist_ok=True)
    tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
    model = AutoModel.from_pretrained(
        model_path,
        trust_remote_code=True,
        use_safetensors=True,
        torch_dtype=torch.bfloat16,
    ).eval().cuda()

    if args.mode == "gundam":
        image_size, crop_mode = 640, True
    else:
        image_size, crop_mode = 1024, False

    model.infer(
        tokenizer,
        prompt="<image>document parsing.",
        image_file=str(image_path),
        output_path=str(output_path),
        base_size=1024,
        image_size=image_size,
        crop_mode=crop_mode,
        max_length=32768,
        no_repeat_ngram_size=35,
        ngram_window=128,
        save_results=True,
    )
    print(f"Saved OCR results to: {output_path}")


if __name__ == "__main__":
    main()
