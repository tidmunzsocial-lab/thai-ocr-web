# Thai OCR Web

Local Thai/English OCR web app for JPG, PNG, and multi-page PDF files. Jobs from
all connected devices share one visible queue and run one at a time.

## One-click Windows installation

Download `Install-Thai-OCR-Web.bat` from the latest GitHub Release and double
click it. The installer downloads the app to `%USERPROFILE%\Thai-OCR-Web`,
installs its dependencies and models, creates a desktop shortcut, and opens the
web interface.

Requirements:

- Windows 10/11 64-bit
- NVIDIA GPU with current driver; 16 GB VRAM recommended
- At least 48 GB RAM and 35 GB free disk space
- Internet connection during installation

The first installation is large because it downloads Python, CUDA libraries,
PaddleOCR, Ollama, and the OCR models.

## One-click Mac installation

Download `Install-Thai-OCR-Web-Mac.zip` from the latest GitHub Release, extract
it, then double click `Install-Thai-OCR-Web-Mac.command`. The Mac package is
optimized for Apple Silicon and installs only Typhoon OCR Fast, Python, and
Ollama. It uses the M-series GPU through Metal and does not install CUDA,
PaddleOCR, or the larger Windows-only engines.

Requirements:

- Apple Silicon Mac (M1 or newer)
- macOS 14 Sonoma or newer
- 12 GB free disk space; 16 GB RAM recommended (8 GB works with fewer apps open)
- Internet connection during installation

The application is installed in `~/Thai-OCR-Web`. Double click
`Thai OCR Web.command` on the Desktop to open it again later.

## OCR engines

- **Typhoon OCR Fast** (default): official Ollama Q4 model, Thai/English,
  structured Markdown, tables and forms. It stays warm for two minutes between
  Fast jobs and unloads when another engine is selected.
- **Typhoon OCR normal**: BF16 model for better accuracy on names and numbers.
- **PaddleOCR GPU**: fastest for plain Thai text.
- **Unlimited-OCR**: slower detailed document parser.

Select 1, 5, or 10 pages per batch. Progress and results appear after each page.
Completed jobs are stored locally in `outputs/web/<job-id>/result.md`.

## Privacy

OCR runs locally. Uploaded documents and results stay on the host computer.
The repository and release do not contain model weights, virtual environments,
logs, uploaded documents, or OCR outputs.

## Models and licenses

Models are downloaded from their original publishers during installation:

- [Typhoon OCR 1.5](https://huggingface.co/typhoon-ai/typhoon-ocr1.5-2b)
- [Typhoon OCR Q4 for Ollama](https://ollama.com/scb10x/typhoon-ocr1.5-3b)
- [Unlimited-OCR](https://huggingface.co/baidu/Unlimited-OCR)
- [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR)

Review each model's license and terms before use. This repository's source code
is licensed under the MIT License.
