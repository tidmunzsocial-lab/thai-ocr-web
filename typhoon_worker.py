import json
import sys
from pathlib import Path

import torch
from PIL import Image
from transformers import AutoModelForImageTextToText, AutoProcessor

from ocr_prompt import PROMPT


def resize_image(image: Image.Image, max_size: int = 1800) -> Image.Image:
    if max(image.size) <= max_size:
        return image
    scale = max_size / max(image.size)
    return image.resize(
        (round(image.width * scale), round(image.height * scale)),
        Image.Resampling.LANCZOS,
    )


def main() -> None:
    manifest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    model_path = Path(sys.argv[2])
    max_image_size = int(sys.argv[3])
    if not torch.cuda.is_available():
        raise RuntimeError("ไม่พบ CUDA GPU")

    processor = AutoProcessor.from_pretrained(model_path, local_files_only=True)
    model = AutoModelForImageTextToText.from_pretrained(
        model_path,
        local_files_only=True,
        dtype=torch.bfloat16,
        device_map="cuda",
    ).eval()

    for item in manifest:
        image = resize_image(Image.open(item["image"]).convert("RGB"), max_image_size)
        messages = [{
            "role": "user",
            "content": [
                {"type": "image", "image": image},
                {"type": "text", "text": PROMPT},
            ],
        }]
        inputs = processor.apply_chat_template(
            messages,
            tokenize=True,
            add_generation_prompt=True,
            return_dict=True,
            return_tensors="pt",
        ).to(model.device)
        with torch.inference_mode():
            generated = model.generate(**inputs, max_new_tokens=8192, do_sample=False)
        trimmed = generated[:, inputs.input_ids.shape[-1]:]
        text = processor.batch_decode(
            trimmed,
            skip_special_tokens=True,
            clean_up_tokenization_spaces=False,
        )[0].strip()
        print("@@RESULT@@" + json.dumps({
            "page": item["page"],
            "text": text,
            "boxed": item["image"],
        }, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
