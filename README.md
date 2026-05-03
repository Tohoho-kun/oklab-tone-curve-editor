# Okhsl Tone Curve Editor

A professional-grade image adjustment tool based on the **Okhsl** perceptual color space.

## Features
- **Perceptual Tone Curves**: Adjust Lightness and Saturation with intuitive feedback.
- **Split View Comparison**: Interactive divider to compare with the original image.
- **16-bit Workflow**: Supports high-bit depth TIFF export using `tifffile`.
- **Lightweight Design**: Optimized backend with minimal dependencies.
- **Modern UI**: Clean, responsive interface designed for creative professionals.

## Installation (Local Development)
1. Clone this repository.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Run the application:
   ```bash
   cd backend
   python3 launcher.py
   ```

## Building Standalone App (macOS)
Run the provided build script:
```bash
cd backend
./build_mac.sh
```

## License
MIT
