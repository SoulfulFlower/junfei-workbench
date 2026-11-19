# Automatic garment selection

`u2net_cloth_seg.onnx` is the four-class U2Net clothes model distributed by
[rembg](https://github.com/danielgatis/rembg/blob/main/rembg/sessions/u2net_cloth_seg.py).
Classes: background, upper garment, lower garment, full-body garment.
The clothing model comes from
[Levin Dabhi's cloth-segmentation](https://github.com/levindabhi/cloth-segmentation)
(MIT); the U2Net architecture is Apache-2.0. Original notices are kept beside
the model. This folder contains no LinkFox code or service credentials.

The release URL, upstream MD5 and pinned SHA256 are in `manifest.json`.
Install a missing model with `python install_colour_models.py` from the app
directory. Installation verifies its SHA256 before replacing the target file.
Normal inference never downloads anything or submits images to a provider.

The app uses the rembg ONNX preprocessing: RGB, LANCZOS resize to 768 square,
divide by the image's maximum channel, ImageNet mean/std, float32 NCHW.
Scores are resized before argmax; class IDs are never interpolated.
Model predictions generate all prompts for local SAM and pixel-based boundary
refinement. No human foreground/background points are required.
