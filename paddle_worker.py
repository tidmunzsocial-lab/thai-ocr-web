import json
import sys
from pathlib import Path

import paddle
from paddleocr import PaddleOCR
from PIL import Image, ImageDraw


def create_ocr() -> PaddleOCR:
    return PaddleOCR(
        text_detection_model_name="PP-OCRv5_mobile_det",
        text_recognition_model_name="th_PP-OCRv5_mobile_rec",
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
        device="gpu:0" if paddle.device.is_compiled_with_cuda() else "cpu",
    )


def main() -> None:
    ocr = create_ocr()
    if sys.argv[1:] == ["--download"]:
        print("PaddleOCR models ready", flush=True)
        return
    manifest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    for item in manifest:
        result = list(ocr.predict(item["image"]))[0].json["res"]
        image = Image.open(item["image"]).convert("RGB")
        draw = ImageDraw.Draw(image)
        for polygon in result["rec_polys"]:
            draw.line([tuple(point) for point in polygon] + [tuple(polygon[0])], fill="red", width=4)
        boxed = Path(item["output"])
        boxed.parent.mkdir(parents=True, exist_ok=True)
        image.save(boxed)
        print("@@RESULT@@" + json.dumps({
            "page": item["page"],
            "text": "\n\n".join(result["rec_texts"]),
            "boxed": str(boxed),
        }, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
